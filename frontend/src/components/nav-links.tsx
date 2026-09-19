"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { route } from "@/lib/routes";

const LINKS = [
  { href: "/batches", label: "Batches" },
  { href: "/reconciliation", label: "Reconciliation" },
  { href: "/exceptions", label: "Exceptions" },
  { href: "/reports", label: "Reports" },
] satisfies { href: string; label: string }[];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex items-center gap-1">
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={route(link.href)}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "rounded-control bg-surface-sunken px-2 py-1 text-2xs font-medium text-ink no-underline"
                : "rounded-control px-2 py-1 text-2xs text-ink-muted no-underline hover:bg-surface-sunken hover:text-ink hover:no-underline"
            }
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
