// @TASK news - NewsCard 컴포넌트 (섹터 배지 + 서브카테고리 배지)
// @SPEC web/src/lib/types.ts (NewsArticle, NEWS_SECTOR_LABELS, NEWS_SUB_LABELS)
// @SPEC web/src/lib/format.ts (formatRelativeTime)
"use client";

import { useState } from "react";
import { Newspaper } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import type { NewsArticle } from "@/lib/types";
import { NEWS_SECTOR_LABELS, NEWS_SUB_LABELS } from "@/lib/types";
import { formatRelativeTime } from "@/lib/format";

/** 썸네일 — 이미지 있으면 표시, 로드 실패 시 Newspaper 아이콘 placeholder.
 *  variant: row(가로형, 좌측 고정 크기) / grid(세로형, 상단 풀폭). */
function NewsThumbnail({
  url,
  title,
  variant,
}: {
  url: string | null;
  title: string;
  variant: "row" | "grid";
}) {
  const [failed, setFailed] = useState(false);
  const showImage = url && !failed;

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-xl bg-surface-soft",
        variant === "row" ? "h-20 w-28" : "aspect-video w-full",
      )}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={title}
          loading="lazy"
          referrerPolicy="no-referrer"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <Newspaper className="h-8 w-8 text-stone" aria-hidden />
      )}
    </div>
  );
}

interface NewsCardProps {
  article: NewsArticle;
  /** row=가로형(2열용, 기본), grid=세로형(3열용) */
  layout?: "row" | "grid";
}

export function NewsCard({ article, layout = "row" }: NewsCardProps) {
  // general은 배지 생략 — 정보 밀도 확보
  const subLabel =
    article.subcategory && article.subcategory !== "general"
      ? NEWS_SUB_LABELS[article.subcategory]
      : null;

  return (
    <a
      href={article.display_link}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "rounded-xl border border-hairline-soft bg-canvas p-4 transition-colors",
        "hover:border-primary",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        layout === "row" ? "flex items-start gap-3" : "flex flex-col gap-3",
      )}
    >
      {/* 썸네일 */}
      <NewsThumbnail
        url={article.thumbnail_url}
        title={article.title}
        variant={layout}
      />

      {/* 텍스트 칼럼 (row=우측, grid=하단) */}
      <div className="min-w-0 flex-1">
        {/* 배지 행: 섹터 + 서브카테고리 + 언론사 + 시간 */}
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <Badge tone="district">
            {NEWS_SECTOR_LABELS[article.sector]}
          </Badge>
          {subLabel && (
            <Badge tone="neutral">{subLabel}</Badge>
          )}
          {article.press && (
            <span className="text-caption text-steel">{article.press}</span>
          )}
          {article.published_at && (
            <span className="text-caption text-steel">
              {formatRelativeTime(article.published_at)}
            </span>
          )}
        </div>

        {/* 제목 */}
        <p className="mb-1 line-clamp-2 text-body-md font-bold text-ink-deep">
          {article.title}
        </p>

        {/* 설명 */}
        {article.description && (
          <p className="line-clamp-2 text-body-sm text-ink">
            {article.description}
          </p>
        )}
      </div>
    </a>
  );
}
