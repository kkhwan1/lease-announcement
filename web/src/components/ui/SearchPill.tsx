// @SPEC DESIGN.md — search-pill (탑-네비 검색 필드)
"use client";

import { Search } from "lucide-react";
import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

interface SearchPillProps extends InputHTMLAttributes<HTMLInputElement> {
  className?: string;
}

export function SearchPill({ className, ...props }: SearchPillProps) {
  return (
    <div className={cn("relative flex items-center", className)}>
      <Search
        className="pointer-events-none absolute left-3 text-steel"
        size={15}
        strokeWidth={2}
        aria-hidden
      />
      <input
        type="text"
        className="h-10 w-full rounded-full bg-surface-soft pl-9 pr-4 text-body-sm text-ink placeholder:text-steel focus:outline-none focus:ring-2 focus:ring-primary/30"
        {...props}
      />
    </div>
  );
}
