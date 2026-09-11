export function PlaceholderNotice({ what }: { what: string }) {
  return (
    <p className="mb-4 rounded-control border border-status-review-border bg-status-review-bg px-3 py-2 text-2xs text-status-review">
      Skeleton build: {what} below is static placeholder data. The EMM-105 data-wiring pass replaces
      it with live <span className="font-mono">/v1</span> calls.
    </p>
  );
}
