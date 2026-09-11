import type { Metadata } from "next";
import Link from "next/link";

import { BatchLookupForm } from "@/components/batch-lookup-form";
import { ContractCalls } from "@/components/contract-calls";
import { DataError } from "@/components/data-error";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { DISCREPANCY_STATES } from "@/lib/contract/enums";
import { DISCREPANCY_STATE_TONE } from "@/lib/contract/status";
import { loadData } from "@/lib/api/server";
import { formatCount, humanizeEnum } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Discrepancies — LEDGER" };

const CONTRACT_OPERATIONS = [
  "listDiscrepancies",
  "getDiscrepancy",
  "getReconciliation",
  "getAuditTrail",
  "resolveDiscrepancy",
] as const;

const TITLE = "Discrepancies";
const DESCRIPTION =
  "Every reconciliation that did not resolve automatically. A discrepancy is a recorded fact, not a failure: it stays open until an authorized operator resolves it, and the resolution never replaces the original decision.";

type SortKey = "discrepancy_id" | "state";

function parseSort(value: string | undefined): SortKey {
  return value === "state" ? "state" : "discrepancy_id";
}

export default async function DiscrepanciesPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string; sort?: string; dir?: string; batch_id?: string }>;
}) {
  const params = await searchParams;
  const batchId = params.batch_id;
  const stateFilter =
    params.state && (DISCREPANCY_STATES as readonly string[]).includes(params.state)
      ? params.state
      : undefined;
  const sortKey = parseSort(params.sort);
  const direction = params.dir === "desc" ? "desc" : "asc";

  const discrepancies = await loadData("listDiscrepancies", {
    query: batchId ? { batch_id: batchId } : {},
  });

  if (!discrepancies.ok) {
    return (
      <DataError
        title={TITLE}
        description={DESCRIPTION}
        error={discrepancies.error}
        operations={CONTRACT_OPERATIONS}
      />
    );
  }

  const counts = DISCREPANCY_STATES.map((state) => ({
    state,
    count: discrepancies.data.filter((row) => row.state === state).length,
  }));

  const rows = discrepancies.data
    .filter((row) => !stateFilter || row.state === stateFilter)
    .sort((a, b) => {
      const cmp = a[sortKey].localeCompare(b[sortKey]);
      return direction === "desc" ? -cmp : cmp;
    });

  const stats: readonly Stat[] = [
    { label: "Discrepancies in scope", value: formatCount(discrepancies.data.length) },
    ...counts.map((entry) => ({
      label: humanizeEnum(entry.state),
      value: formatCount(entry.count),
    })),
  ];

  const search = new URLSearchParams();
  if (batchId) search.set("batch_id", batchId);

  const sortHref = (key: SortKey) => {
    const next = new URLSearchParams(search);
    next.set("sort", key);
    next.set("dir", sortKey === key && direction === "asc" ? "desc" : "asc");
    if (stateFilter) next.set("state", stateFilter);
    return route(`/discrepancies?${next.toString()}`);
  };

  const filterHref = (state?: string) => {
    const next = new URLSearchParams(search);
    if (state) next.set("state", state);
    const query = next.toString();
    return query ? route(`/discrepancies?${query}`) : route("/discrepancies");
  };

  return (
    <>
      <PageHeader title={TITLE} description={DESCRIPTION} />

      <BatchLookupForm action="/discrepancies" defaultBatchId={batchId} />
      <p className="mb-4 text-2xs text-ink-subtle">
        {batchId ? (
          <>
            Filtered to batch <span className="font-mono">{batchId}</span>.{" "}
            <Link href={route("/discrepancies")}>Show all batches</Link>
          </>
        ) : (
          "Showing every batch. Filter by a batch id returned from the ingest screen."
        )}
      </p>

      <SummaryBand stats={stats} columns={5} />

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-2xs">
        <span className="uppercase tracking-wide text-ink-muted">Status</span>
        <Link
          href={filterHref()}
          className={stateFilter ? "font-mono" : "font-mono font-semibold text-ink no-underline"}
        >
          all
        </Link>
        {DISCREPANCY_STATES.map((state) => (
          <Link
            key={state}
            href={filterHref(state)}
            className={
              stateFilter === state ? "font-mono font-semibold text-ink no-underline" : "font-mono"
            }
          >
            {state}
          </Link>
        ))}
      </div>

      <Table caption="Discrepancy queue">
        <THead>
          <Tr>
            <Th>
              <Link href={sortHref("discrepancy_id")} className="no-underline">
                Discrepancy {sortKey === "discrepancy_id" ? (direction === "asc" ? "↑" : "↓") : ""}
              </Link>
            </Th>
            <Th>Reconciliation</Th>
            <Th>Reason</Th>
            <Th>
              <Link href={sortHref("state")} className="no-underline">
                Status {sortKey === "state" ? (direction === "asc" ? "↑" : "↓") : ""}
              </Link>
            </Th>
            <Th>Action</Th>
          </Tr>
        </THead>
        <TBody>
          {rows.length === 0 ? (
            <Tr>
              <Td colSpan={5} className="py-6 text-center text-sm text-ink-muted">
                No discrepancies in this scope.
              </Td>
            </Tr>
          ) : (
            rows.map((row) => (
              <Tr key={row.discrepancy_id} accent={DISCREPANCY_STATE_TONE[row.state]}>
                <Td className="whitespace-nowrap">
                  <Link
                    href={route(`/discrepancies/${encodeURIComponent(row.discrepancy_id)}`)}
                    className="font-mono text-2xs"
                  >
                    {row.discrepancy_id}
                  </Link>
                </Td>
                <Td className="whitespace-nowrap">
                  <Link
                    href={route(`/reconciliation?batch_id=${encodeURIComponent(batchId ?? "")}`)}
                    className="font-mono text-2xs"
                  >
                    {row.reconciliation_id}
                  </Link>
                </Td>
                <Td className="max-w-[460px] text-2xs text-ink-muted">{row.reason}</Td>
                <Td>
                  <StatusPill tone={DISCREPANCY_STATE_TONE[row.state]}>
                    {humanizeEnum(row.state)}
                  </StatusPill>
                </Td>
                <Td className="whitespace-nowrap text-2xs">
                  {row.state === "OPEN" ? (
                    <Link href={route(`/discrepancies/${encodeURIComponent(row.discrepancy_id)}`)}>
                      Resolve
                    </Link>
                  ) : (
                    <Link href={route(`/discrepancies/${encodeURIComponent(row.discrepancy_id)}`)}>
                      View
                    </Link>
                  )}
                </Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
