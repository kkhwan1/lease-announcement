// @TASK T2 - BuildingCard 컴포넌트
// @SPEC web/src/lib/types.ts (BuildingSummary, District, DISTRICT_LABELS)
// @SPEC web/src/lib/format.ts (formatRentManwon)

import Link from "next/link";
import { Building2 } from "lucide-react";
import { BuildingSummary, DISTRICT_LABELS } from "@/lib/types";
import { formatRentManwon } from "@/lib/format";

interface BuildingCardProps {
  building: BuildingSummary;
  selected?: boolean;
  onHover?: (id: string | null) => void;
}

export function BuildingCard({ building, selected, onHover }: BuildingCardProps) {
  const districtLabel =
    building.district !== null ? DISTRICT_LABELS[building.district] : null;

  const rentDisplay =
    building.min_rent_per_pyeong !== null &&
    formatRentManwon(building.min_rent_per_pyeong) !== "-"
      ? `${formatRentManwon(building.min_rent_per_pyeong)}/평`
      : "임대료 문의";

  return (
    <Link
      href={`/building/${building.building_id}`}
      className={[
        "block rounded border bg-white p-3 transition-shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        selected
          ? "border-accent shadow-md"
          : "border-border hover:border-accent hover:shadow-sm",
      ].join(" ")}
      onMouseEnter={() => onHover?.(building.building_id)}
      onMouseLeave={() => onHover?.(null)}
    >
      {/* 썸네일 영역 — 이미지 미업로드 상태이므로 회색 placeholder */}
      <div className="mb-3 flex h-28 items-center justify-center rounded bg-surface">
        <Building2
          className="h-10 w-10 text-muted"
          aria-hidden
        />
      </div>

      {/* 건물명 + 권역 배지 */}
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className="line-clamp-1 text-sm font-semibold text-foreground">
          {building.name}
        </span>
        {districtLabel !== null && (
          <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
            {districtLabel}
          </span>
        )}
      </div>

      {/* 주소 */}
      {building.address_road !== null && (
        <p className="mb-2 line-clamp-1 text-xs text-muted">
          {building.address_road}
        </p>
      )}

      {/* 공실수 · 최저 평당임대료 */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-foreground">
          공실 {building.vacancy_count}개
        </span>
        <span
          className={
            rentDisplay === "임대료 문의" ? "text-muted" : "font-medium text-accent"
          }
        >
          {rentDisplay}
        </span>
      </div>
    </Link>
  );
}
