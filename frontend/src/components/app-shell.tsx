import Link from "next/link";
import type { ReactNode } from "react";

import { CONTRACT_VERSION } from "@/lib/api/operations.generated";

import { NavLinks } from "./nav-links";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-12 w-full max-w-[1200px] items-center justify-between gap-6 px-4">
          <div className="flex items-center gap-6">
            <Link
              href="/ingest"
              className="text-2xs font-semibold uppercase tracking-[0.16em] text-ink no-underline hover:no-underline"
            >
              Ledger
            </Link>
            <NavLinks />
          </div>
          <div className="flex items-center gap-3 text-2xs text-ink-subtle">
            <span className="font-mono">contract v{CONTRACT_VERSION}</span>
            <span className="hidden border-l border-line pl-3 sm:inline">
              generated from docs/openapi/ledger.v1.json
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-[1200px] px-4 py-3 text-2xs text-ink-subtle">
          Skeleton build. Screens render placeholder data until the EMM-105 data-wiring pass; no
          live
          <span className="font-mono"> /v1 </span> calls are made yet.
        </div>
      </footer>
    </div>
  );
}
