import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-panel border border-line bg-surface px-4 py-6">
      <h1 className="text-base font-semibold text-ink">Page not found</h1>
      <p className="mt-1 text-sm text-ink-muted">
        The dashboard has four sections: Ingest Status, Reconciliation, Discrepancies, and Reports.
      </p>
      <p className="mt-3 text-sm">
        <Link href="/ingest">Go to Ingest Status</Link>
      </p>
    </div>
  );
}
