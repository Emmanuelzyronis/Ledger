import Link from "next/link";
import type { ReactNode } from "react";

import { NavLinks } from "./nav-links";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-12 w-full max-w-[1200px] items-center justify-between gap-6 px-4">
          <div className="flex items-center gap-6">
            <Link
              href="/"
              className="text-2xs font-semibold uppercase tracking-[0.16em] text-ink no-underline hover:no-underline"
            >
              Ledger
            </Link>
            <NavLinks />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-[1200px] px-4 py-3 text-2xs text-ink-subtle">
          Transaction reconciliation — resolution is the only write operation.
        </div>
      </footer>
    </div>
  );
}
