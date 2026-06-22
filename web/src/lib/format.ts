// 표시용 포맷 유틸. 숫자는 DB에서 string(numeric)으로 오므로 안전 변환.

const PYEONG_PER_SQM = 0.3025;

export function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** 평당 임대료(원) → "19만원" 같은 한국식 축약. */
export function formatRentManwon(v: string | number | null): string {
  const n = toNum(v);
  if (n === null || n <= 0) return "-";
  const man = n / 10000;
  if (man >= 100) return `${Math.round(man).toLocaleString()}만원`;
  // 소수 첫째자리까지
  return `${(Math.round(man * 10) / 10).toLocaleString()}만원`;
}

/** 원 단위 그대로 콤마 표시: 190000 → "190,000원". */
export function formatWon(v: string | number | null): string {
  const n = toNum(v);
  if (n === null) return "-";
  return `${n.toLocaleString()}원`;
}

/** 면적: 평 우선 표시. "128.4평". */
export function formatPyeong(v: string | number | null): string {
  const n = toNum(v);
  if (n === null) return "-";
  return `${(Math.round(n * 10) / 10).toLocaleString()}평`;
}

/** ㎡ 표시. "424.5㎡". */
export function formatSqm(v: string | number | null): string {
  const n = toNum(v);
  if (n === null) return "-";
  return `${(Math.round(n * 10) / 10).toLocaleString()}㎡`;
}

/** ㎡ → 평 환산(0.3025). */
export function sqmToPyeong(sqm: number): number {
  return sqm * PYEONG_PER_SQM;
}

/** 층수: 지상/지하 합성. "B3 / 20F". */
export function formatFloors(above: number | null, below: number | null): string {
  const parts: string[] = [];
  if (below) parts.push(`B${below}`);
  if (above) parts.push(`${above}F`);
  return parts.length ? parts.join(" / ") : "-";
}

/** 비율(%) 표시. "59.4%". */
export function formatPercent(v: string | number | null): string {
  const n = toNum(v);
  if (n === null) return "-";
  return `${Math.round(n * 100) / 100}%`;
}

/** ISO 시각 → 한국어 상대 시간. "방금/N분 전/N시간 전/N일 전", 7일 초과 시 날짜 표시. */
export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "";
  const published = new Date(iso);
  if (isNaN(published.getTime())) return "";
  const diffMs = Date.now() - published.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "방금";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) {
    return new Intl.RelativeTimeFormat("ko", { numeric: "always" }).format(
      -diffMin,
      "minute",
    );
  }
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) {
    return new Intl.RelativeTimeFormat("ko", { numeric: "always" }).format(
      -diffHour,
      "hour",
    );
  }
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay <= 7) {
    return new Intl.RelativeTimeFormat("ko", { numeric: "always" }).format(
      -diffDay,
      "day",
    );
  }
  return published.toLocaleDateString("ko-KR");
}
