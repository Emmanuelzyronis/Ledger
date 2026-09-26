"use client";

import Link from "next/link";
import { useActionState } from "react";

import { ActionFeedback } from "@/components/action-feedback";
import { createBatchAction, ingestRecordAction, registerSourceAction } from "@/lib/api/actions";
import { route } from "@/lib/routes";

const INPUT =
  "mt-1 w-full rounded-control border border-line bg-surface px-2 py-1 text-sm text-ink placeholder:text-ink-subtle disabled:bg-surface-sunken disabled:text-ink-subtle";
const BUTTON =
  "mt-2 rounded-control border border-accent bg-accent px-3 py-1 text-2xs font-medium text-white disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-sunken disabled:text-ink-subtle";
const LABEL = "block text-2xs uppercase tracking-wide text-ink-muted";

function Field({
  id,
  label,
  name,
  placeholder,
  defaultValue,
  required = true,
}: {
  id: string;
  label: string;
  name: string;
  placeholder?: string;
  defaultValue?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        name={name}
        placeholder={placeholder}
        defaultValue={defaultValue}
        required={required}
        className={INPUT}
      />
    </div>
  );
}

function Panel({
  title,
  operation,
  children,
}: {
  title: string;
  operation: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-panel border border-line bg-surface">
      <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        {title} — <span className="font-mono">{operation}</span>
      </h2>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

export function IngestWorkflow({ batchId }: { batchId?: string }) {
  const [sourceState, sourceSubmit, sourcePending] = useActionState(registerSourceAction, null);
  const [batchState, batchSubmit, batchPending] = useActionState(createBatchAction, null);
  const [recordState, recordSubmit, recordPending] = useActionState(ingestRecordAction, null);

  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
      <Panel title="Register source" operation="POST /v1/sources">
        <form action={sourceSubmit}>
          <Field id="source_id" label="source_id" name="source_id" placeholder="source-a" />
          <div className="mt-3">
            <Field id="name" label="name" name="name" placeholder="Source A" />
          </div>
          <div className="mt-3">
            <Field
              id="schema_versions"
              label="schema_versions (comma separated)"
              name="schema_versions"
              placeholder="source_a.v1"
            />
          </div>
          <button type="submit" disabled={sourcePending} className={BUTTON}>
            {sourcePending ? "Registering…" : "Register source"}
          </button>
        </form>
        <ActionFeedback result={sourceState}>
          {(source) => (
            <p>
              <span className="font-mono">{source.source_id}</span> — {source.name},{" "}
              {source.schema_versions.join(", ")}
            </p>
          )}
        </ActionFeedback>
      </Panel>

      <Panel title="Create batch" operation="POST /v1/batches">
        <form action={batchSubmit}>
          <Field id="batch_source_id" label="source_id" name="source_id" placeholder="source-a" />
          <div className="mt-3">
            <Field
              id="external_batch_id"
              label="external_batch_id"
              name="external_batch_id"
              placeholder="A-2026-09-11-settlement"
            />
          </div>
          <div className="mt-3">
            <Field
              id="schema_version"
              label="schema_version"
              name="schema_version"
              placeholder="source_a.v1"
            />
          </div>
          <button type="submit" disabled={batchPending} className={BUTTON}>
            {batchPending ? "Creating…" : "Create batch"}
          </button>
        </form>
        <ActionFeedback result={batchState}>
          {(batch) => (
            <p>
              <span className="font-mono">{batch.batch_id}</span> is{" "}
              <span className="font-mono">{batch.state}</span>.{" "}
              <Link href={route(`/batches?batch_id=${encodeURIComponent(batch.batch_id)}`)}>
                Show its counters
              </Link>
            </p>
          )}
        </ActionFeedback>
      </Panel>

      <Panel title="Ingest record" operation="POST /v1/batches/{batch_id}/records">
        <form action={recordSubmit}>
          <Field
            id="record_batch_id"
            label="batch_id"
            name="batch_id"
            placeholder="batch-…"
            defaultValue={batchId}
          />
          <div className="mt-3">
            <label htmlFor="payload" className={LABEL}>
              payload (source-native JSON)
            </label>
            <textarea
              id="payload"
              name="payload"
              rows={5}
              required
              placeholder='{"record_id":"A100","occurred_at":"2026-09-11","amount":"100.00","currency":"USD","direction":"CREDIT","transaction_reference":"TX-1"}'
              className={`${INPUT} font-mono text-2xs`}
            />
          </div>
          <div className="mt-3">
            <Field
              id="idempotency_key"
              label="idempotency_key (optional)"
              name="idempotency_key"
              required={false}
            />
          </div>
          <button type="submit" disabled={recordPending} className={BUTTON}>
            {recordPending ? "Ingesting…" : "Ingest record"}
          </button>
        </form>
        <ActionFeedback result={recordState}>
          {(record) => (
            <p>
              <span className="font-mono">{record.status}</span> —{" "}
              <span className="font-mono">{record.raw_record_id ?? "no raw record"}</span>
              {record.duplicate_submission ? " (duplicate submission reused)" : ""}
              {record.invalid_reason ? ` — ${record.invalid_reason}` : ""}
            </p>
          )}
        </ActionFeedback>
      </Panel>
    </div>
  );
}
