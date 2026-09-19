"use client";

import { useState } from "react";

interface IdChipProps {
  id: string | null | undefined;
  /** Visible prefix length after the last ":" separator. Default 8 chars of the hex part. */
  hexLen?: number;
}

/**
 * Renders a LEDGER composite ID (e.g. "reconciliation:9317fcec73ec52664e6e2b92554b...")
 * as a short chip: "reconciliation:9317fcec" with the full ID available on hover (title).
 * Click copies the full ID to the clipboard.
 */
export function IdChip({ id, hexLen = 8 }: IdChipProps) {
  const [copied, setCopied] = useState(false);

  if (!id) return <span className="text-ink-subtle">—</span>;

  const colonIdx = id.lastIndexOf(":");
  const prefix = colonIdx >= 0 ? id.slice(0, colonIdx + 1) : "";
  const hex = colonIdx >= 0 ? id.slice(colonIdx + 1) : id;
  const short = hex.slice(0, hexLen);
  const truncated = hex.length > hexLen;

  async function copy() {
    try {
      await navigator.clipboard.writeText(id!);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard not available
    }
  }

  return (
    <button
      type="button"
      title={id}
      data-id={id}
      onClick={copy}
      className="group inline-flex cursor-pointer items-center gap-1 rounded-sm px-0 font-mono text-2xs text-ink hover:text-accent focus:outline-none"
    >
      <span>
        {prefix}
        {short}
        {truncated && (
          <span className="text-ink-subtle">…</span>
        )}
      </span>
      <span className="opacity-0 text-ink-subtle group-hover:opacity-100 text-[10px]">
        {copied ? "✓" : "⎘"}
      </span>
    </button>
  );
}
