// @SPEC DESIGN.md — badge-promo-yellow / badge-attention / badge-success / badge-critical
// rounded-full pill 배지. district/neutral은 임대매물 권역 칩용 추가 톤
import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone =
  | "success"
  | "attention"
  | "warning"
  | "critical"
  | "district"
  | "neutral";

const TONE: Record<Tone, string> = {
  success: "bg-success text-canvas",
  attention: "bg-attention text-canvas",
  warning: "bg-warning text-ink-deep",
  critical: "bg-critical text-canvas",
  district: "bg-surface-soft text-steel",
  neutral: "bg-surface-soft text-steel",
};

interface BadgeProps {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-caption font-bold",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
