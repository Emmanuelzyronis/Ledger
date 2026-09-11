"""EPIC 4 contract tests: the published OpenAPI document must match the real service.

Three layers of verification:

1. Document integrity — the artifact is valid OpenAPI 3.1, every ``$ref``
   resolves, operation ids are unique, and the versioning policy agrees with the
   implementation.
2. Coverage — the documented operations are exactly the operations implemented
   by ``LedgerAPI``/``LedgerService``, and the documented error codes are exactly
   the codes the service can return.
3. Behavioral conformance — every documented operation is driven against the
   real ``LedgerService`` over a real SQLite database, and every response is
   validated against the schema published for that status code. Request
   examples in the document are validated against their request schemas.

No third-party JSON Schema dependency is used; ``schema_errors`` implements the
subset of JSON Schema 2020-12 used by the artifact.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ledger.ingestion import RawIngestion  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from ledger.service import LedgerASGI, LedgerService, ServiceSettings  # noqa: E402
from product_proof import dataset  # noqa: E402
from product_proof.pipeline import register_sources, run_standard_pipeline, seed_records  # noqa: E402

DOCUMENT_PATH = REPO_ROOT / "docs" / "openapi" / "ledger.v1.json"
DOCUMENT = json.loads(DOCUMENT_PATH.read_text(encoding="utf-8"))

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
ALL_OUTCOMES = {"MATCHED", "MISMATCHED", "UNMATCHED_A", "UNMATCHED_B", "AMBIGUOUS", "DUPLICATE", "INVALID"}

# Operations implemented by LedgerAPI._dispatch through the versioned service.
IMPLEMENTED_OPERATIONS = {
    ("GET", "/v1/health"),
    ("GET", "/v1/ready"),
    ("GET", "/v1/reports"),
    ("GET", "/v1/export"),
    ("POST", "/v1/sources"),
    ("POST", "/v1/batches"),
    ("GET", "/v1/batches"),
    ("POST", "/v1/batches/{batch_id}/records"),
    ("GET", "/v1/batches/{batch_id}"),
    ("GET", "/v1/reconciliations"),
    ("GET", "/v1/reconciliations/{reconciliation_id}"),
    ("GET", "/v1/discrepancies"),
    ("GET", "/v1/discrepancies/{discrepancy_id}"),
    ("GET", "/v1/audit/{entity_type}/{entity_id}"),
    ("POST", "/v1/discrepancies/{discrepancy_id}/resolve"),
}

CONTRACT_PAYLOAD = {
    "record_id": "CONTRACT-1",
    "occurred_at": "2026-09-01",
    "amount": "12.50",
    "currency": "USD",
    "direction": "CREDIT",
}


# --------------------------------------------------------------------------
# Minimal JSON Schema validation (subset used by the artifact)
# --------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def resolve_ref(document, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise AssertionError(f"only local $ref values are supported, got {ref!r}")
    node = document
    for token in ref[2:].split("/"):
        node = node[token.replace("~1", "/").replace("~0", "~")]
    return node


def schema_errors(instance, schema, document, path="$"):
    errors: list[str] = []
    _validate(instance, schema, document, path, errors)
    return errors


def _validate(instance, schema, document, path, errors):
    if "$ref" in schema:
        _validate(instance, resolve_ref(document, schema["$ref"]), document, path, errors)
        return
    declared = schema.get("type")
    if declared is not None:
        allowed = [declared] if isinstance(declared, str) else list(declared)
        if not any(_TYPE_CHECKS[item](instance) for item in allowed):
            errors.append(f"{path}: expected type {declared}, got {type(instance).__name__}")
            return
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], document, f"{path}.{key}", errors)
            elif additional is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                _validate(value, additional, document, f"{path}.{key}", errors)
        if "propertyNames" in schema:
            for key in instance:
                _validate(key, schema["propertyNames"], document, f"{path}.<key>", errors)
    elif isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        items = schema.get("items")
        if items is not None:
            for index, value in enumerate(instance):
                _validate(value, items, document, f"{path}[{index}]", errors)
    elif isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    elif isinstance(instance, bool):
        pass
    elif isinstance(instance, (int, float)):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is below minimum {schema['minimum']}")
    return errors


def iter_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)


def operations(document):
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield method.upper(), path, operation


def paths_match(template, path):
    template_parts = template.strip("/").split("/")
    path_parts = path.strip("/").split("/")
    if len(template_parts) != len(path_parts):
        return False
    for template_part, path_part in zip(template_parts, path_parts):
        if template_part.startswith("{") and template_part.endswith("}"):
            continue
        if template_part != path_part:
            return False
    return True


def operation_for(document, method, path):
    concrete = path.split("?", 1)[0]
    for candidate_method, candidate_path, operation in operations(document):
        if candidate_method == method.upper() and paths_match(candidate_path, concrete):
            return operation
    raise AssertionError(f"{method} {path} is not documented")


def response_schema(document, operation, status):
    entry = operation["responses"][str(status)]
    if "$ref" in entry:
        entry = resolve_ref(document, entry["$ref"])
    return entry["content"]["application/json"]["schema"]


# --------------------------------------------------------------------------
# Document integrity and coverage
# --------------------------------------------------------------------------

class OpenAPIDocumentTests(unittest.TestCase):
    def test_document_is_openapi_31(self):
        self.assertEqual(DOCUMENT["openapi"], "3.1.0")
        self.assertEqual(DOCUMENT["jsonSchemaDialect"], "https://json-schema.org/draft/2020-12/schema")
        self.assertTrue(DOCUMENT["info"]["title"])
        self.assertTrue(DOCUMENT["info"]["version"])
        self.assertTrue(DOCUMENT["servers"])
        self.assertIn("bearerAuth", DOCUMENT["components"]["securitySchemes"])

    def test_versioning_policy_matches_the_service(self):
        policy = DOCUMENT["x-ledger-versioning"]
        self.assertEqual(policy["current"], "v1")
        self.assertEqual(policy["supported"], ["v1"])
        self.assertEqual(policy["unknown_version_status"], 404)
        self.assertEqual(policy["unversioned_alias_in_contract"], False)
        for path in DOCUMENT["paths"]:
            self.assertTrue(path.startswith("/v1/"), path)

    def test_every_reference_resolves(self):
        for ref in iter_refs(DOCUMENT):
            resolve_ref(DOCUMENT, ref)

    def test_operation_ids_are_unique_and_operations_are_complete(self):
        seen = set()
        for method, path, operation in operations(DOCUMENT):
            operation_id = operation["operationId"]
            self.assertNotIn(operation_id, seen, operation_id)
            seen.add(operation_id)
            self.assertTrue(operation.get("summary"), operation_id)
            self.assertIn("responses", operation)
            for status, entry in operation["responses"].items():
                self.assertTrue(status.isdigit(), (operation_id, status))
                if "$ref" in entry:
                    entry = resolve_ref(DOCUMENT, entry["$ref"])
                self.assertIn("application/json", entry["content"])
            if method == "POST":
                self.assertIn("requestBody", operation, operation_id)

    def test_request_examples_validate_against_request_schemas(self):
        checked = 0
        for _, _, operation in operations(DOCUMENT):
            request_body = operation.get("requestBody")
            if request_body is None:
                continue
            content = request_body["content"]["application/json"]
            if "example" not in content:
                continue
            schema = resolve_ref(DOCUMENT, content["schema"]["$ref"]) if "$ref" in content["schema"] else content["schema"]
            self.assertEqual(schema_errors(content["example"], schema, DOCUMENT), [])
            checked += 1
        self.assertEqual(checked, 4)

    def test_response_examples_validate_against_response_schemas(self):
        checked = 0
        for _, _, operation in operations(DOCUMENT):
            for status, entry in operation["responses"].items():
                resolved = resolve_ref(DOCUMENT, entry["$ref"]) if "$ref" in entry else entry
                content = resolved["content"]["application/json"]
                if "example" not in content:
                    continue
                schema = resolve_ref(DOCUMENT, content["schema"]["$ref"]) if "$ref" in content["schema"] else content["schema"]
                self.assertEqual(schema_errors(content["example"], schema, DOCUMENT), [])
                checked += 1
        self.assertGreaterEqual(checked, 4)

    def test_error_code_extension_matches_the_error_schema(self):
        documented = DOCUMENT["x-ledger-error-codes"]
        enum = DOCUMENT["components"]["schemas"]["ErrorDetail"]["properties"]["code"]["enum"]
        self.assertEqual(sorted(documented), sorted(enum))
        self.assertEqual(len(documented), len(set(documented)))

    def test_documented_operations_equal_implemented_operations(self):
        documented = {(method, path) for method, path, _ in operations(DOCUMENT)}
        self.assertEqual(documented, IMPLEMENTED_OPERATIONS)


# --------------------------------------------------------------------------
# Real-service conformance
# --------------------------------------------------------------------------

def verifier(token):
    principals = {
        "operator": {"role": "reconciliation_operator", "roles": ("reconciliation_operator",), "source_ids": None},
        "reader-a": {"role": "reader", "roles": ("reader",), "source_ids": ("source-a",)},
        "reader-z": {"role": "reader", "roles": ("reader",), "source_ids": ("source-z",)},
    }
    return principals.get(token)


def build_service(**overrides):
    directory = tempfile.mkdtemp(prefix="ledger-contract-")
    path = str(Path(directory) / "ledger.sqlite3")
    database = LedgerDatabase(path)
    ingestion = RawIngestion(database)
    register_sources(ingestion)
    batch_a, _ = seed_records(database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                              batch_id="contract-batch-a", external_batch_id="contract-ext-a",
                              idempotency_prefix="contract-a")
    batch_b, _ = seed_records(database, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                              batch_id="contract-batch-b", external_batch_id="contract-ext-b",
                              idempotency_prefix="contract-b")
    run_standard_pipeline(database, [batch_a, batch_b], reconcile_invalid=True)
    database.close()
    values = {"database_path": path, "port": 0, "require_tls": False}
    values.update(overrides)
    service = LedgerService(ServiceSettings(**values), token_verifier=verifier)
    service.start()
    return service, directory, {"batch_a": batch_a, "batch_b": batch_b}


def asgi_call(app, method, path, raw_body=b"", headers=None):
    scope = {"type": "http", "method": method, "path": path, "query_string": b"",
             "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]}
    messages = [{"type": "http.request", "body": raw_body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = next(message for message in sent if message["type"] == "http.response.body")
    return start["status"], json.loads(body["body"])


class ContractConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service, cls.directory, cls.fixture = build_service()

    @classmethod
    def tearDownClass(cls):
        cls.service.stop()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def call(self, method, path, body=None, token="operator", headers=None, scheme="http"):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        return self.service.handle(method, path, body, request_headers, scheme=scheme)

    def assert_conforms(self, method, path, body=None, token="operator", headers=None, status=200):
        actual_status, payload = self.call(method, path, body, token=token, headers=headers)
        self.assertEqual(actual_status, status, (method, path, payload))
        operation = operation_for(DOCUMENT, method, path)
        self.assertIn(str(actual_status), operation["responses"], (method, path, actual_status))
        errors = schema_errors(payload, response_schema(DOCUMENT, operation, actual_status), DOCUMENT)
        self.assertEqual(errors, [], (method, path, errors, payload))
        if actual_status == 200:
            self.assertIn("data", payload)
            self.assertIn("correlation_id", payload)
        return actual_status, payload

    def test_every_documented_operation_conforms(self):
        self.assert_conforms("GET", "/v1/health", token=None)
        self.assert_conforms("GET", "/v1/ready", token=None)

        self.assert_conforms("POST", "/v1/sources", body={
            "source_id": "contract-source", "name": "Contract Source", "schema_versions": ["source_a.v1"]})
        _, batch = self.assert_conforms("POST", "/v1/batches", body={
            "source_id": "contract-source", "external_batch_id": "contract-external", "schema_version": "source_a.v1"})
        contract_batch = batch["data"]["batch_id"]

        _, first = self.assert_conforms("POST", f"/v1/batches/{contract_batch}/records", body={
            "payload": CONTRACT_PAYLOAD, "idempotency_key": "contract-1"})
        self.assertFalse(first["data"]["duplicate_submission"])
        _, replay = self.assert_conforms("POST", f"/v1/batches/{contract_batch}/records", body={
            "payload": CONTRACT_PAYLOAD, "idempotency_key": "contract-1"})
        self.assertTrue(replay["data"]["duplicate_submission"])

        self.assert_conforms("GET", f"/v1/batches/{contract_batch}")
        self.assert_conforms("GET", "/v1/batches")
        self.assert_conforms("GET", "/v1/batches?source_id=contract-source")
        self.assert_conforms("GET", "/v1/reports")
        self.assert_conforms("GET", f"/v1/reports?batch_id={self.fixture['batch_a']}")
        self.assert_conforms("GET", "/v1/export")
        self.assert_conforms("GET", "/v1/reconciliations")
        _, reconciliations = self.assert_conforms("GET", "/v1/reconciliations")
        reconciliation_id = reconciliations["data"][0]["reconciliation_id"]
        self.assert_conforms("GET", f"/v1/reconciliations/{reconciliation_id}")
        _, discrepancies = self.assert_conforms("GET", "/v1/discrepancies")
        discrepancy_id = discrepancies["data"][0]["discrepancy_id"]
        self.assert_conforms("GET", f"/v1/discrepancies/{discrepancy_id}")
        self.assert_conforms("GET", f"/v1/audit/batch/{self.fixture['batch_a']}")
        self.assert_conforms("GET", f"/v1/audit/reconciliation/{reconciliation_id}")
        self.assert_conforms("POST", f"/v1/discrepancies/{discrepancy_id}/resolve", body={
            "resolution_type": "MANUAL_APPROVED", "reason": "Verified against the September statement.",
            "evidence": {"reference": "stmt-2026-09"}})

    def test_report_exposes_all_seven_outcomes(self):
        status, payload = self.call("GET", "/v1/reports")
        self.assertEqual(status, 200)
        self.assertEqual(set(payload["data"]["outcomes"]), ALL_OUTCOMES)
        self.assertEqual(set(payload["data"]["current_outcomes"]), ALL_OUTCOMES)

    def test_resolve_is_idempotent_and_preserves_history(self):
        _, discrepancies = self.call("GET", "/v1/discrepancies")
        open_discrepancy = next(row["discrepancy_id"] for row in discrepancies["data"] if row["state"] == "OPEN")
        body = {"resolution_type": "MANUAL_APPROVED", "reason": "Replay check"}
        _, first = self.assert_conforms("POST", f"/v1/discrepancies/{open_discrepancy}/resolve", body=body)
        _, second = self.assert_conforms("POST", f"/v1/discrepancies/{open_discrepancy}/resolve", body=body)
        self.assertEqual(first["data"]["resolution"]["resolution_id"],
                         second["data"]["resolution"]["resolution_id"])
        self.assertEqual(second["data"]["discrepancy"]["state"], "RESOLVED")
        self.assertIsNotNone(second["data"]["reconciliation"]["supersedes_reconciliation_id"])

    def test_export_redacts_sensitive_keys(self):
        status, payload = self.call("GET", "/v1/export")
        self.assertEqual(status, 200)
        text = json.dumps(payload["data"])
        for term in ("payload", "payload_json", "secret", "credential"):
            self.assertNotIn(term, text.casefold().replace("[redacted]", ""))

    def test_versioned_alias_and_unknown_version(self):
        self.assertEqual(self.call("POST", "/sources", {"source_id": "alias-source", "name": "Alias",
                                                        "schema_versions": ["source_a.v1"]})[0], 200)
        status, payload = self.call("GET", "/v2/reports")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "unsupported_api_version")
        status, payload = self.call("GET", "/v1/not-a-real-endpoint")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(payload["error"]["message"], "endpoint does not exist")


class ErrorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service, cls.directory, cls.fixture = build_service()
        cls.app = LedgerASGI(cls.service)

    @classmethod
    def tearDownClass(cls):
        cls.service.stop()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def call(self, method, path, body=None, token="operator", headers=None, scheme="http"):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        return self.service.handle(method, path, body, request_headers, scheme=scheme)

    def expect_error(self, status, code, method, path, **kwargs):
        actual_status, payload = self.call(method, path, **kwargs)
        self.assertEqual(actual_status, status, (method, path, payload))
        self.assertEqual(payload["error"]["code"], code, (method, path, payload))
        errors = schema_errors(payload, DOCUMENT["components"]["schemas"]["Error"], DOCUMENT)
        self.assertEqual(errors, [], (method, path, errors, payload))
        self.assertIn("correlation_id", payload)
        return code

    def test_documented_error_contract_is_reachable(self):
        observed = {
            self.expect_error(401, "authentication_required", "GET", "/v1/reports", token=None),
            self.expect_error(401, "invalid_token", "GET", "/v1/reports", token="wrong"),
            self.expect_error(403, "forbidden", "GET", f"/v1/batches/{self.fixture['batch_a']}", token="reader-z"),
            self.expect_error(403, "origin_not_allowed", "GET", "/v1/reports",
                              headers={"Origin": "https://evil.example.test"}),
            self.expect_error(415, "unsupported_media_type", "POST", "/v1/sources",
                              body={"source_id": "x", "name": "x", "schema_versions": ["v"]},
                              headers={"Content-Type": "text/plain"}),
            self.expect_error(400, "missing_field", "POST", "/v1/sources", body={}),
            self.expect_error(400, "invalid_json", "POST", "/v1/sources", body=["not", "an", "object"]),
            self.expect_error(404, "not_found", "GET", "/v1/batches/does-not-exist"),
            self.expect_error(404, "unsupported_api_version", "GET", "/v2/reports"),
        }
        # The invalid_request case needs a real discrepancy row.
        _, discrepancies = self.call("GET", "/v1/discrepancies")
        discrepancy_id = discrepancies["data"][0]["discrepancy_id"]
        observed.add(self.expect_error(400, "invalid_request", "POST",
                                       f"/v1/discrepancies/{discrepancy_id}/resolve",
                                       body={"resolution_type": "NOT_A_RESOLUTION", "reason": "x"}))

        # Environment-configured limits: TLS, rate limiting, body size, depth.
        tls_service, tls_directory, _ = build_service(require_tls=True)
        try:
            status, payload = tls_service.handle("GET", "/v1/reports", None,
                                                 {"Authorization": "Bearer operator"}, scheme="http")
            self.assertEqual((status, payload["error"]["code"]), (400, "tls_required"))
            observed.add(payload["error"]["code"])
        finally:
            tls_service.stop()
            shutil.rmtree(tls_directory, ignore_errors=True)

        limited, limited_directory, _ = build_service(rate_limit_per_minute=1)
        try:
            first = limited.handle("GET", "/v1/reports", None, {"Authorization": "Bearer operator"})
            second = limited.handle("GET", "/v1/reports", None, {"Authorization": "Bearer operator"})
            self.assertEqual(first[0], 200)
            self.assertEqual((second[0], second[1]["error"]["code"]), (429, "rate_limited"))
            observed.add(second[1]["error"]["code"])
        finally:
            limited.stop()
            shutil.rmtree(limited_directory, ignore_errors=True)

        strict, strict_directory, _ = build_service(max_body_bytes=200, max_json_depth=3)
        try:
            status, payload = strict.handle(
                "POST", "/v1/sources",
                {"a": {"b": {"c": {"d": 1}}}, "source_id": "x", "name": "x", "schema_versions": ["v"]},
                {"Authorization": "Bearer operator", "Content-Type": "application/json"})
            self.assertEqual((status, payload["error"]["code"]), (400, "payload_too_deep"))
            observed.add(payload["error"]["code"])

            status, payload = asgi_call(LedgerASGI(strict), "POST", "/v1/sources", raw_body=b"x" * 400,
                                        headers={"Authorization": "Bearer operator", "Content-Type": "application/json"})
            self.assertEqual((status, payload["error"]["code"]), (413, "payload_too_large"))
            observed.add(payload["error"]["code"])
        finally:
            strict.stop()
            shutil.rmtree(strict_directory, ignore_errors=True)

        status, payload = asgi_call(self.app, "POST", "/v1/sources", raw_body=b"{not json",
                                    headers={"Authorization": "Bearer operator", "Content-Type": "application/json"})
        self.assertEqual((status, payload["error"]["code"]), (400, "invalid_json"))
        observed.add(payload["error"]["code"])

        def exploding_verifier(token):
            raise RuntimeError("verifier exploded with a secret token")

        broken = LedgerService(ServiceSettings(database_path=":memory:", port=0, require_tls=False),
                               token_verifier=exploding_verifier)
        broken.start()
        try:
            status, payload = asgi_call(LedgerASGI(broken), "GET", "/v1/reports",
                                        headers={"Authorization": "Bearer operator"})
            self.assertEqual((status, payload["error"]["code"]), (500, "internal_error"))
            self.assertNotIn("exploded", payload["error"]["message"])
            observed.add(payload["error"]["code"])
        finally:
            broken.stop()

        self.assertEqual(observed, set(DOCUMENT["x-ledger-error-codes"]))

    def test_degraded_readiness_is_health_data_not_an_error_envelope(self):
        degraded, directory, _ = build_service()
        try:
            degraded.database.close()
            status, payload = degraded.handle("GET", "/v1/ready")
            self.assertEqual(status, 503)
            self.assertEqual(payload["data"]["database"], "unavailable")
            self.assertNotIn("error", payload)
            operation = operation_for(DOCUMENT, "GET", "/v1/ready")
            self.assertEqual(schema_errors(payload, response_schema(DOCUMENT, operation, 503), DOCUMENT), [])
        finally:
            degraded.stop()
            shutil.rmtree(directory, ignore_errors=True)


class ScopedReadTests(unittest.TestCase):
    """A source-scoped reader sees exactly its own discrepancies and audit trails.

    Regression coverage for three defects found while wiring the dashboard:
    percent-encoded identifiers 404'd, ``GET /v1/discrepancies`` returned an
    empty list for every scoped principal, and the audit trail was not scoped to
    the discrepancy's source.
    """

    @classmethod
    def setUpClass(cls):
        cls.service, cls.directory, cls.fixture = build_service()
        cls.operator = {"Authorization": "Bearer operator"}
        _, payload = cls.service.handle("GET", "/v1/discrepancies", None, cls.operator)
        cls.discrepancies = payload["data"]
        batches = {}
        for row in cls.discrepancies:
            _, reconciliation = cls.service.handle(
                "GET", f"/v1/reconciliations/{row['reconciliation_id']}", None, cls.operator)
            batch_id = reconciliation["data"]["batch_id"]
            if batch_id not in batches:
                _, batch = cls.service.handle("GET", f"/v1/batches/{batch_id}", None, cls.operator)
                batches[batch_id] = batch["data"]["source_id"]
            row["_source_id"] = batches[batch_id]

    @classmethod
    def tearDownClass(cls):
        cls.service.stop()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_scoped_list_returns_only_in_scope_discrepancies(self):
        status, payload = self.service.handle(
            "GET", "/v1/discrepancies", None, {"Authorization": "Bearer reader-a"})
        self.assertEqual(status, 200)
        expected = {row["discrepancy_id"] for row in self.discrepancies if row["_source_id"] == "source-a"}
        actual = {row["discrepancy_id"] for row in payload["data"]}
        self.assertTrue(expected, "the fixtures must produce a source-a discrepancy")
        self.assertTrue(expected - {row["discrepancy_id"] for row in self.discrepancies if row["_source_id"] == "source-b"})
        self.assertEqual(actual, expected)

    def test_scoped_reader_cannot_read_another_source(self):
        foreign = next(row for row in self.discrepancies if row["_source_id"] == "source-b")
        for path in (f"/v1/discrepancies/{foreign['discrepancy_id']}",
                     f"/v1/audit/discrepancy/{foreign['discrepancy_id']}"):
            status, _ = self.service.handle(
                "GET", path, None, {"Authorization": "Bearer reader-a"})
            self.assertEqual(status, 403, path)

    def test_scoped_batch_list_returns_only_in_scope_batches(self):
        operator = {"Authorization": "Bearer operator"}
        status, payload = self.service.handle("GET", "/v1/batches", None, operator)
        self.assertEqual(status, 200)
        by_source = {row["source_id"] for row in payload["data"]}
        self.assertEqual(by_source, {"source-a", "source-b"})

        scoped = {"Authorization": "Bearer reader-a"}
        status, scoped_payload = self.service.handle("GET", "/v1/batches", None, scoped)
        self.assertEqual(status, 200)
        self.assertEqual({row["source_id"] for row in scoped_payload["data"]}, {"source-a"})
        self.assertTrue(all(row["source_id"] == "source-a" for row in scoped_payload["data"]))

        status, filtered = self.service.handle("GET", "/v1/batches?source_id=source-a", None, scoped)
        self.assertEqual(status, 200)
        self.assertEqual(len(filtered["data"]), len(scoped_payload["data"]))

    def test_scoped_reader_cannot_list_a_foreign_source(self):
        status, _ = self.service.handle(
            "GET", "/v1/batches?source_id=source-z", None, {"Authorization": "Bearer reader-a"})
        self.assertEqual(status, 403)

    def test_percent_encoded_identifiers_resolve(self):
        target = self.discrepancies[0]["discrepancy_id"]
        status, payload = self.service.handle(
            "GET", f"/v1/discrepancies/{quote(target, safe='')}", None, self.operator)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["data"]["discrepancy_id"], target)


if __name__ == "__main__":
    unittest.main()
