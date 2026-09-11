/**
 * A plain GET form. The contract publishes no "list batches" operation, so a
 * batch is addressed by the id returned from `createBatch` and looked up
 * directly; there is no endpoint to enumerate them and none is invented.
 */
export function BatchLookupForm({
  action,
  defaultBatchId,
  label = "Batch id",
}: {
  action: string;
  defaultBatchId?: string;
  label?: string;
}) {
  return (
    <form action={action} method="get" className="mb-4 flex flex-wrap items-end gap-2">
      <div>
        <label
          htmlFor={`${action}-batch-id`}
          className="block text-2xs uppercase tracking-wide text-ink-muted"
        >
          {label}
        </label>
        <input
          id={`${action}-batch-id`}
          name="batch_id"
          defaultValue={defaultBatchId ?? ""}
          placeholder="batch-…"
          className="mt-1 w-72 rounded-control border border-line bg-surface px-2 py-1 font-mono text-2xs text-ink placeholder:text-ink-subtle"
        />
      </div>
      <button
        type="submit"
        className="rounded-control border border-line bg-surface-muted px-3 py-1 text-2xs font-medium text-ink"
      >
        Look up
      </button>
    </form>
  );
}
