// @SPEC DESIGN.md — 헤딩 위계 (display-lg / heading-lg / heading-sm) + 300웨이트 에디토리얼 eyebrow
import type { ReactNode } from "react";
import { cn } from "./cn";

type Level = 1 | 2 | 3;

const LEVEL: Record<Level, string> = {
  1: "text-display-lg text-ink-deep",
  2: "text-heading-lg text-ink-deep",
  3: "text-heading-sm text-ink-deep",
};

interface SectionHeadingProps {
  level?: Level;
  /** 300웨이트 에디토리얼 윗머리 (Meta 시그니처 리듬) */
  eyebrow?: string;
  className?: string;
  children: ReactNode;
}

export function SectionHeading({
  level = 2,
  eyebrow,
  className,
  children,
}: SectionHeadingProps) {
  const Tag = (`h${level}` as const) as "h1" | "h2" | "h3";
  return (
    <div className={className}>
      {eyebrow && (
        <p className="text-heading-md text-slate mb-1">{eyebrow}</p>
      )}
      <Tag className={cn(LEVEL[level])}>{children}</Tag>
    </div>
  );
}
