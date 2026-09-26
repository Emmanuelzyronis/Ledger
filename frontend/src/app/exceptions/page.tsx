import type { Metadata } from "next";
import Link from "next/link";

import { DataError } from "@/components/data-error";
import { IdChip } from "@/components/id-chip";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { DISCREPANCY_STATES } from "@/lib/contract/enums";
import { DISCREPANCY_STATE_TONE } from "@/lib/contract/status";
import { loadData } from "@/lib/api/server";
import { formatCount, humanizeEnum } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Exceptions — LEDGER" };

const TITLE = "Exceptions";
const DESCRIPTION =
  "Reconciliation decisions that require operator review. An exception stays open until resolved; the resolution creates a new decision version and the original is preserved.";

type SortKey = "discrepancy_id" | "state";

function parseSort(value: string | undefined): SortKey {
  return value === "state" ? "state" : "discrepancy_id";
}


export default async function ExceptionsPage({
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
    return <DataError title={TITLE} description={DESCRIPTION} error={discrepancies.error} />;
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

  const openCount = counts.find((c) => c.state === "OPEN")?.count ?? 0;
  const stats: readonly Stat[] = [
    { label: "Total exceptions", value: formatCount(discrepancies.data.length) },
    { label: "Open", value: formatCount(openCount), detail: "need action" },
    ...counts
      .filter((c) => c.state !== "OPEN")
      .map((entry) => ({
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
    return route(`/exceptions?${next.toString()}`);
  };

  const filterHref = (state?: string) => {
    const next = new URLSearchParams(search);
    if (state) next.set("state", state);
    const query = next.toString();
    return query ? route(`/exceptions?${query}`) : route("/exceptions");
  };

  return (
    <>
      <PageHeader title={TITLE} description={DESCRIPTION} />

      {batchId ? (
        <p className="mb-4 text-2xs text-ink-subtle">
          Filtered to batch <span className="font-mono">{batchId}</span>.{" "}
          <Link href={route("/exceptions")}>Show all</Link>
        </p>
      ) : null}

      <SummaryBand stats={stats} columns={5} />

      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs">
        <span className="uppercase tracking-wide text-ink-muted">Filter</span>
        <Link
          href={filterHref()}
          className={
            !stateFilter
              ? "rounded-control bg-surface-sunken px-2 py-0.5 font-medium text-ink no-underline"
              : "px-2 py-0.5 text-ink-muted"
          }
        >
          All
        </Link>
        {DISCREPANCY_STATES.map((state) => (
          <Link
            key={state}
            href={filterHref(state)}
            className={
              stateFilter === state
                ? "rounded-control bg-surface-sunken px-2 py-0.5 font-medium text-ink no-underline"
                : "px-2 py-0.5 text-ink-muted"
            }
          >
            {humanizeEnum(state)}
          </Link>
        ))}
      </div>

      <Table caption="Exception queue">
        <THead>
          <Tr>
            <Th>
              <Link href={sortHref("discrepancy_id")} className="no-underline">
                Exception {sortKey === "discrepancy_id" ? (direction === "asc" ? "↑" : "↓") : ""}
              </Link>
            </Th>
            <Th>Batch</Th>
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
                {stateFilter
                  ? `No ${humanizeEnum(stateFilter).toLowerCase()} exceptions.`
                  : "No exceptions in this scope."}
              </Td>
            </Tr>
          ) : (
            rows.map((row) => (
              <Tr key={row.discrepancy_id} accent={DISCREPANCY_STATE_TONE[row.state]}>
                <Td className="whitespace-nowrap">
                  <Link
                    href={route(`/exceptions/${encodeURIComponent(row.discrepancy_id)}`)}
                    className="text-2xs text-accent"
                  >
                    <IdChip id={row.discrepancy_id} />
                  </Link>
                </Td>
                <Td className="whitespace-nowrap">
                  <IdChip id={row.reconciliation_id} />
                </Td>
                <Td className="max-w-[400px] text-2xs text-ink-muted">{row.reason}</Td>
                <Td>
                  <StatusPill tone={DISCREPANCY_STATE_TONE[row.state]}>
                    {humanizeEnum(row.state)}
                  </StatusPill>
                </Td>
                <Td className="whitespace-nowrap text-2xs">
                  <Link
                    href={route(`/exceptions/${encodeURIComponent(row.discrepancy_id)}`)}
                    className={row.state === "OPEN" ? "font-medium text-accent" : "text-ink-muted"}
                  >
                    {row.state === "OPEN" ? "Resolve →" : "View"}
                  </Link>
                </Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>
    </>
  );
}
