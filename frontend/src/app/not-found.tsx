import Link from "next/link";
import { route } from "@/lib/routes";

export default function NotFound() {
  return (
    <div className="rounded-panel border border-line bg-surface px-4 py-6">
      <h1 className="text-base font-semibold text-ink">Page not found</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Use the navigation above to go to Overview, Batches, Reconciliation, Exceptions, or Reports.
      </p>
      <p className="mt-3 text-sm">
        <Link href={route("/")}>Go to Overview</Link>
      </p>
    </div>
  );
}
