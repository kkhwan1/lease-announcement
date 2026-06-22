// 뉴스 소식 페이지 로딩 스켈레톤
export default function NewsLoading() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* 헤딩 스켈레톤 */}
      <div className="mb-6 space-y-2">
        <div className="h-4 w-24 animate-pulse rounded-full bg-surface-soft" />
        <div className="h-8 w-40 animate-pulse rounded-full bg-surface-soft" />
      </div>

      {/* 탭 스켈레톤 */}
      <div className="mb-6 flex gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-9 w-16 animate-pulse rounded-full bg-surface-soft"
          />
        ))}
      </div>

      {/* 카드 스켈레톤 */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-xxxl bg-surface-soft"
          />
        ))}
      </div>
    </div>
  );
}
