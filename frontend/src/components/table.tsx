import type { ReactNode } from "react";

export function Table({ children, caption }: { children: ReactNode; caption?: string }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-line bg-surface-muted text-2xs uppercase tracking-wide text-ink-muted">
      {children}
    </thead>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>;
}

export function Tr({
  children,
  accent,
}: {
  children: ReactNode;
  accent?: "matched" | "review" | "discrepancy" | "pending";
}) {
  const accentClass = accent ? ROW_ACCENT[accent] : "border-l-2 border-l-transparent";
  return <tr className={`${accentClass} align-top`}>{children}</tr>;
}

const ROW_ACCENT: Record<"matched" | "review" | "discrepancy" | "pending", string> = {
  matched: "border-l-2 border-l-status-matched",
  review: "border-l-2 border-l-status-review",
  discrepancy: "border-l-2 border-l-status-discrepancy",
  pending: "border-l-2 border-l-status-pending",
};

export function Th({
  children,
  align = "left",
  className = "",
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={`whitespace-nowrap px-3 py-2 font-medium ${align === "right" ? "text-right" : "text-left"} ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className = "",
  colSpan,
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={`px-3 py-2 ${align === "right" ? "text-right" : "text-left"} ${className}`}
    >
      {children}
    </td>
  );
}

export function TableMessage({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-6 text-center text-sm text-ink-muted">
        {children}
      </td>
    </tr>
  );
}
