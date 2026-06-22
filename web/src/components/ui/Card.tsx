// @SPEC DESIGN.md — card-product-feature / card-feature-photo / card-icon-feature / 일반 섹션 카드
import type { ElementType, ReactNode } from "react";
import { cn } from "./cn";

type Variant = "feature" | "photo" | "icon" | "flat";

const VARIANT: Record<Variant, string> = {
  // 사진+카피 피처 카드: 32px 라운드, 큰 패딩, hairline 테두리 (flat)
  feature: "rounded-xxxl p-8 border border-hairline-soft bg-canvas",
  // 풀블리드 사진 쇼케이스: chrome 없음
  photo: "rounded-xxxl bg-canvas overflow-hidden",
  // 아이콘 피처 타일: 16px 라운드, 작은 패딩
  icon: "rounded-xl p-6 border border-hairline-soft bg-canvas",
  // 상세 섹션 일반 카드
  flat: "rounded-xl p-6 border border-hairline-soft bg-canvas",
};

interface CardProps {
  variant?: Variant;
  as?: ElementType;
  className?: string;
  children: ReactNode;
}

export function Card({ variant = "flat", as, className, children }: CardProps) {
  const Comp = as ?? "div";
  return <Comp className={cn(VARIANT[variant], className)}>{children}</Comp>;
}
