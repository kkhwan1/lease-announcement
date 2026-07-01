"use client";

// @TASK news - 뉴스 소식 페이지 (2단 탭 + 검색·정렬·기간·열토글·더보기)
// @SPEC web/src/lib/queries.ts (fetchNews, NewsFilter)
// 클라이언트 컴포넌트: 홈(page.tsx) 디바운스 패턴 복제. 필터는 클라 상태로 관리.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Columns2,
  Columns3,
  ArrowDownWideNarrow,
  ArrowUpWideNarrow,
  ChevronDown,
} from "lucide-react";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { SearchPill } from "@/components/ui/SearchPill";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { NewsCard } from "@/components/NewsCard";
import { fetchNews } from "@/lib/queries";
import { dedupeByTitle } from "@/lib/newsDedup";
import type { NewsArticle } from "@/lib/types";
import { NEWS_SECTOR_LABELS, NEWS_SUB_LABELS } from "@/lib/types";

const PAGE_SIZE = 60;

const SECTOR_TABS: { code: string; label: string }[] = [
  { code: "all", label: "전체" },
  ...Object.entries(NEWS_SECTOR_LABELS).map(([code, label]) => ({ code, label })),
];

const SUB_TABS: { code: string; label: string }[] = [
  { code: "all", label: "전체" },
  ...Object.entries(NEWS_SUB_LABELS).map(([code, label]) => ({ code, label })),
];

const PERIOD_TABS: { code: string; label: string }[] = [
  { code: "all", label: "전체기간" },
  { code: "day", label: "오늘" },
  { code: "week", label: "최근 1주" },
  { code: "month", label: "최근 1개월" },
];

export default function NewsPage() {
  // 필터 상태
  const [sector, setSector] = useState("all");
  const [sub, setSub] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [period, setPeriod] = useState("all");
  const [sortAsc, setSortAsc] = useState(false);

  // 보기 상태 (localStorage 유지). 기본 3열.
  const [cols, setCols] = useState<2 | 3>(3);

  // 데이터 상태
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // dedup 전 원본 누적 배열(offset 계산 + 전체 재-dedup용). 화면엔 dedup 결과만 노출.
  const rawRef = useRef<NewsArticle[]>([]);

  // 열 토글 — hydration mismatch 회피 위해 마운트 후 localStorage 읽기 (기본 3열)
  useEffect(() => {
    const saved = window.localStorage.getItem("news:cols");
    if (saved === "2") setCols(2);
  }, []);

  const setColsPersist = useCallback((next: 2 | 3) => {
    setCols(next);
    window.localStorage.setItem("news:cols", String(next));
  }, []);

  // 필터 변경 시 재조회 (디바운스 250ms, offset 0으로 교체)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      fetchNews({ sector, sub, q: keyword, period, sortAsc, limit: PAGE_SIZE, offset: 0 })
        .then((rows) => {
          if (cancelled) return;
          rawRef.current = rows;
          setArticles(dedupeByTitle(rows));
          setHasMore(rows.length === PAGE_SIZE);
          setError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          console.error(e);
          setError("뉴스를 불러오지 못했습니다.");
        })
        .finally(() => !cancelled && setLoading(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [sector, sub, keyword, period, sortAsc]);

  // 더보기 — 원본 누적 개수를 offset으로 다음 페이지 가져와, 전체를 다시 dedup.
  const loadMore = useCallback(() => {
    setLoadingMore(true);
    fetchNews({
      sector,
      sub,
      q: keyword,
      period,
      sortAsc,
      limit: PAGE_SIZE,
      offset: rawRef.current.length,
    })
      .then((rows) => {
        rawRef.current = [...rawRef.current, ...rows];
        setArticles(dedupeByTitle(rawRef.current));
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => {
        console.error(e);
        setError("더 불러오지 못했습니다.");
      })
      .finally(() => setLoadingMore(false));
  }, [sector, sub, keyword, period, sortAsc]);

  // 섹터 변경 시 서브는 전체로 리셋
  const onSectorChange = (code: string) => {
    setSector(code);
    setSub("all");
  };

  return (
    <div
      className={cn(
        "mx-auto px-4 py-8",
        cols === 3 ? "max-w-screen-2xl" : "max-w-5xl",
      )}
    >
      {/* 헤딩 + 보기 컨트롤 */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <SectionHeading level={1} eyebrow="부동산 시장">
          뉴스 소식
        </SectionHeading>

        {/* 우상단: 정렬 + 열 토글 */}
        <div className="flex shrink-0 items-center gap-2 pt-1">
          <button
            type="button"
            onClick={() => setSortAsc((v) => !v)}
            title={sortAsc ? "오래된순" : "최신순"}
            className="flex h-9 items-center gap-1 rounded-full border border-hairline bg-canvas px-3 text-caption font-bold text-ink transition-colors hover:border-primary"
          >
            {sortAsc ? (
              <ArrowUpWideNarrow className="h-4 w-4" aria-hidden />
            ) : (
              <ArrowDownWideNarrow className="h-4 w-4" aria-hidden />
            )}
            {sortAsc ? "오래된순" : "최신순"}
          </button>

          <div className="flex items-center rounded-full border border-hairline bg-canvas p-0.5">
            <button
              type="button"
              onClick={() => setColsPersist(2)}
              title="2열 보기"
              aria-pressed={cols === 2}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                cols === 2 ? "bg-ink-deep text-canvas" : "text-steel",
              )}
            >
              <Columns2 className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => setColsPersist(3)}
              title="3열 보기"
              aria-pressed={cols === 3}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                cols === 3 ? "bg-ink-deep text-canvas" : "text-steel",
              )}
            >
              <Columns3 className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </div>

      {/* 검색 */}
      <div className="mb-4 max-w-md">
        <SearchPill
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="제목·내용 검색 (예: 여의도, 매각)"
        />
      </div>

      {/* 1단: 섹터 탭 */}
      <div className="mb-3 flex flex-wrap gap-2">
        {SECTOR_TABS.map(({ code, label }) => {
          const isActive = sector === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => onSectorChange(code)}
              className={cn(
                "rounded-full px-4 py-2 text-body-sm font-bold transition-colors",
                isActive
                  ? "bg-ink-deep text-canvas"
                  : "border border-hairline bg-canvas text-ink",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* 2단: 서브카테고리 탭 */}
      <div className="mb-3 flex flex-wrap gap-2">
        {SUB_TABS.map(({ code, label }) => {
          const isActive = sub === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => setSub(code)}
              className={cn(
                "rounded-full px-3 py-1.5 text-caption font-bold transition-colors",
                isActive
                  ? "bg-primary text-canvas"
                  : "border border-hairline bg-canvas text-steel",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* 3단: 기간 필터 */}
      <div className="mb-6 flex flex-wrap gap-2">
        {PERIOD_TABS.map(({ code, label }) => {
          const isActive = period === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => setPeriod(code)}
              className={cn(
                "rounded-full px-3 py-1.5 text-caption font-bold transition-colors",
                isActive
                  ? "bg-charcoal text-canvas"
                  : "border border-hairline bg-canvas text-steel",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* 목록 */}
      {error ? (
        <p className="py-16 text-center text-body-md text-critical">{error}</p>
      ) : loading ? (
        <p className="py-16 text-center text-body-md text-steel">불러오는 중…</p>
      ) : articles.length === 0 ? (
        // 필터가 초기 상태(전체)인지 여부로 안내 메시지 분기.
        // 초기 상태에서 빈 배열 → 뉴스 데이터 자체가 없는 경우(DB 준비중).
        // 필터 적용 상태에서 빈 배열 → 조건에 맞는 결과 없음.
        sector === "all" && sub === "all" && keyword === "" && period === "all" ? (
          <div className="py-16 text-center">
            <p className="text-body-md text-steel">뉴스 준비중입니다.</p>
            <p className="mt-2 text-body-sm text-stone">곧 업데이트될 예정입니다.</p>
          </div>
        ) : (
          <p className="py-16 text-center text-body-md text-steel">
            해당 조건의 뉴스가 없습니다.
          </p>
        )
      ) : (
        <>
          <div
            className={cn(
              "grid grid-cols-1 gap-4",
              cols === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : "md:grid-cols-2",
            )}
          >
            {articles.map((article) => (
              <NewsCard
                key={article.id}
                article={article}
                layout={cols === 3 ? "grid" : "row"}
              />
            ))}
          </div>

          {hasMore && (
            <div className="mt-8 flex justify-center">
              <Button
                variant="secondary"
                size="sm"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore ? "불러오는 중…" : "더보기"}
                {!loadingMore && <ChevronDown className="ml-1 inline h-4 w-4" aria-hidden />}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
