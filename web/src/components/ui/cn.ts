// className 합성 헬퍼 — falsy 값 제거 후 join (clsx 미도입, 의존성 0)
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
