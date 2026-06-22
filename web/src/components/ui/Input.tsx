// @SPEC DESIGN.md — text-input / text-input-focused / text-input-error
import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function Input({ invalid = false, className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "h-11 rounded-lg border bg-canvas px-3 text-body-sm text-ink placeholder:text-steel focus:outline-none",
        invalid
          ? "border-critical-strong focus:border-critical-strong"
          : "border-hairline focus:border-2 focus:border-primary",
        className,
      )}
      aria-invalid={invalid || undefined}
      {...props}
    />
  );
}
