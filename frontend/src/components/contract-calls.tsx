import { GENERATED_OPERATIONS, type GeneratedOperationId } from "@/lib/api/operations.generated";

/**
 * Every screen states the contract operations it is responsible for. The
 * method/path pair is read from the generated contract index, so this list
 * cannot drift from docs/openapi/ledger.v1.json.
 */
export function ContractCalls({ operations }: { operations: readonly GeneratedOperationId[] }) {
  return (
    <section className="mt-6 rounded-panel border border-line bg-surface">
      <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Contract operations used by this screen
      </h2>
      <ul className="divide-y divide-line">
        {operations.map((operationId) => {
          const operation = GENERATED_OPERATIONS[operationId];
          return (
            <li key={operationId} className="flex items-baseline gap-3 px-4 py-2 text-2xs">
              <span className="w-12 shrink-0 font-mono uppercase text-ink-subtle">
                {operation.method}
              </span>
              <span className="font-mono text-ink">{operation.path}</span>
              <span className="text-ink-subtle">{operation.tag}</span>
              {operation.isPublic ? <span className="text-ink-subtle">public</span> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
