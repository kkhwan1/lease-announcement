"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-hairline-soft bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Link href="/" className="flex items-center">
          <span className="text-ink-deep font-bold">오피스 임대매물</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1 text-sm">
          <Link
            href="/"
            className={
              pathname === "/"
                ? "rounded px-3 py-1.5 text-ink-deep font-bold"
                : "rounded px-3 py-1.5 text-steel"
            }
          >
            매물 검색
          </Link>
          <Link
            href="/about"
            className={
              pathname === "/about"
                ? "rounded px-3 py-1.5 text-ink-deep font-bold"
                : "rounded px-3 py-1.5 text-steel"
            }
          >
            서비스 소개
          </Link>
          <Link
            href="/news"
            className={
              pathname === "/news"
                ? "rounded px-3 py-1.5 text-ink-deep font-bold"
                : "rounded px-3 py-1.5 text-steel"
            }
          >
            뉴스 소식
          </Link>
        </nav>
      </div>
    </header>
  );
}
