// @SPEC DESIGN.md — button-pill-tab / button-pill-tab-active
// 카테고리 네비/토글 pill. 활성 시 ink-deep 다크필이 테두리를 대체
import type { ButtonHTMLAttributes } from "react";
import { cn } from "./cn";

interface PillTabProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

export function PillTab({ active = false, className, children, ...props }: PillTabProps) {
  return (
    <button
      type="button"
      className={cn(
        "rounded-full px-4 py-2 text-body-sm font-bold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        active
          ? "bg-ink-deep text-canvas"
          : "bg-canvas text-ink border border-hairline",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
