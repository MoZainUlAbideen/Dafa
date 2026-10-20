"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function SiteHeader() {
  const path = usePathname();
  return (
    <header className="site-header">
      <Link href="/" className="brand" aria-label="Dafa home">
        <span className="brand-latin">Dafa</span>
        <span className="brand-urdu" lang="ur">دفعہ</span>
      </Link>
      <nav className="site-nav" aria-label="Main">
        <Link href="/ask" aria-current={path === "/ask" ? "page" : undefined}>Ask</Link>
        <Link href="/read/constitution/1" aria-current={path.startsWith("/read/constitution") ? "page" : undefined}>Constitution</Link>
        <Link href="/read/ppc/1" aria-current={path.startsWith("/read/ppc") ? "page" : undefined}>Penal Code</Link>
      </nav>
    </header>
  );
}
