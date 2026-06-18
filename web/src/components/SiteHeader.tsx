import Link from "next/link";
import { Building2 } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Building2 className="h-5 w-5 text-accent" aria-hidden />
          <span>오피스 임대매물</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1 text-sm">
          <Link
            href="/"
            className="rounded px-3 py-1.5 text-muted hover:bg-surface hover:text-foreground"
          >
            매물 검색
          </Link>
          <Link
            href="/about"
            className="rounded px-3 py-1.5 text-muted hover:bg-surface hover:text-foreground"
          >
            서비스 소개
          </Link>
        </nav>
      </div>
    </header>
  );
}
