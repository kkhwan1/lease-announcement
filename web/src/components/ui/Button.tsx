// @SPEC DESIGN.md — button-primary / button-buy-cta(accent) / button-secondary / button-ghost
// Meta 시그니처: 모든 버튼 rounded-full pill, text-body-sm font-bold
import {
  cloneElement,
  isValidElement,
  type ButtonHTMLAttributes,
  type ReactElement,
} from "react";
import { cn } from "./cn";

type Variant = "primary" | "accent" | "secondary" | "ghost";
type Size = "md" | "sm";

const VARIANT: Record<Variant, string> = {
  // 흑색 pill — 마케팅 surface 1차 CTA
  primary: "bg-ink-button text-on-ink-button",
  // 코발트 pill — 임대매물 맥락의 단일 강조 액션
  accent: "bg-primary text-on-ink-button",
  // 2px ink-deep 아웃라인 ghost
  secondary: "bg-transparent text-ink-deep border-2 border-ink-deep",
  // 조용한 아웃라인 ghost (3차 CTA)
  ghost: "bg-transparent text-ink-deep border-2 border-hairline",
};

const SIZE: Record<Size, string> = {
  md: "px-[30px] py-3.5",
  sm: "px-4 py-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** true면 단일 자식 엘리먼트(예: Link)에 버튼 스타일을 입힘 */
  asChild?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  asChild = false,
  className,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(
    "inline-flex items-center justify-center gap-1.5 rounded-full text-body-sm font-bold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    VARIANT[variant],
    SIZE[size],
    className,
  );

  if (asChild && isValidElement(children)) {
    const child = children as ReactElement<{ className?: string }>;
    return cloneElement(child, {
      className: cn(classes, child.props.className),
    });
  }

  return (
    <button className={classes} {...props}>
      {children}
    </button>
  );
}
