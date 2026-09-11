import { GENERATED_OPERATIONS, type GeneratedOperationId } from "@/lib/api/operations.generated";

/** Renders "GET /v1/export" from the generated contract index, never from a literal. */
export function OperationLabel({ operation }: { operation: GeneratedOperationId }) {
  const { method, path } = GENERATED_OPERATIONS[operation];
  return (
    <span className="font-mono">
      {method.toUpperCase()} {path}
    </span>
  );
}
