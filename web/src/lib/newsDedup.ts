// 제목 유사도 기반 뉴스 중복 제거.
// 같은 사건을 여러 언론사가 보도하면 URL(link_hash)은 달라 DB엔 다 남는다.
// 화면에서는 제목의 단어 겹침(자카드 유사도)으로 묶어 대표 1건만 노출한다.
// 기준: 사용자 요구 — "제목에서 동일한 단어들이 많으면 중복으로 간주".
import type { NewsArticle } from "./types";

// 식별력 낮은 흔한 단어 — 겹쳐도 "같은 사건" 신호가 약하므로 핵심어 카운트에서 제외.
const STOPWORDS = new Set([
  "규모", "완료", "성사", "성료", "추진", "발표", "결정", "예정", "전망",
  "오피스", "부동산", "빌딩", "건물", "시장", "투자", "매각", "임대", "거래",
  "한국", "서울", "국내", "최대", "최고", "이상", "이하", "관련", "위한",
]);

/** 숫자+단위 표기 흔들림 정규화: 7천억→7000억, 7000억원→7000억 등. */
function normalizeToken(w: string): string {
  return w
    .replace(/(\d+)천억/g, (_, n) => `${n}000억`)
    .replace(/억원/g, "억")
    .replace(/원$/, "");
}

/** 제목을 정규화해 2글자 이상 토큰 집합으로. 조사/기호 분리 + 숫자단위 정규화. */
function titleTokens(title: string): Set<string> {
  const cleaned = title
    .toLowerCase()
    .replace(/[^가-힣a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const tokens = cleaned
    .split(" ")
    .map((w) => w.replace(/(은|는|이|가|을|를|의|에|와|과|도|로|으로)$/, ""))
    .map(normalizeToken)
    .filter((w) => w.length >= 2);
  return new Set(tokens);
}

/** 두 토큰 집합의 자카드 유사도(교집합/합집합). 0~1. */
function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  const union = a.size + b.size - inter;
  return union === 0 ? 0 : inter / union;
}

/** 식별력 있는(불용어 제외) 공통 토큰 수. 고유명사·숫자 위주. */
function keyOverlap(a: Set<string>, b: Set<string>): number {
  let n = 0;
  for (const t of a) if (b.has(t) && !STOPWORDS.has(t)) n++;
  return n;
}

/**
 * 같은 사건을 다룬 기사를 묶어 첫 1건만 남긴다(입력은 보통 최신순 → 먼저 나온 게 대표).
 * 중복 판정: (a) 자카드 유사도 ≥ jaccardThreshold  OR
 *            (b) 식별력 있는 공통 핵심어 ≥ keyThreshold (예: "지타워"+"7000억").
 * 언론사마다 수식어가 달라 자카드가 희석되는 경우를 (b)가 잡는다.
 */
export function dedupeByTitle(
  articles: NewsArticle[],
  jaccardThreshold = 0.4,
  keyThreshold = 2,
): NewsArticle[] {
  const kept: NewsArticle[] = [];
  const keptTokens: Set<string>[] = [];

  for (const article of articles) {
    const tokens = titleTokens(article.title);
    const isDup = keptTokens.some(
      (t) =>
        jaccard(tokens, t) >= jaccardThreshold ||
        keyOverlap(tokens, t) >= keyThreshold,
    );
    if (!isDup) {
      kept.push(article);
      keptTokens.push(tokens);
    }
  }
  return kept;
}
