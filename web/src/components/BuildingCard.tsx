// @TASK T2 - BuildingCard 컴포넌트
// @SPEC web/src/lib/types.ts (BuildingSummary, District, DISTRICT_LABELS)
// @SPEC web/src/lib/format.ts (formatRentManwon)
"use client";

import { useState } from "react";
import Link from "next/link";
import { Building2 } from "lucide-react";
import { BuildingSummary, DISTRICT_LABELS } from "@/lib/types";
import { formatRentManwon } from "@/lib/format";
import { buildingImageUrl } from "@/lib/supabase";
import { Badge } from "@/components/ui/Badge";

/** 카드 썸네일 — 이미지 있으면 표시, 없거나 로드 실패 시 아이콘 placeholder. */
function CardThumbnail({ path, name }: { path: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  const showImage = path && !failed;

  return (
    <div className="flex h-20 w-28 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-surface-soft to-primary-soft">
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={buildingImageUrl(path)}
          alt={`${name} 외관`}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <Building2 className="h-10 w-10 text-stone" aria-hidden />
      )}
    </div>
  );
}

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
        "flex items-center gap-3 rounded-xxxl border bg-canvas p-4 transition-shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        selected
          ? "border-primary shadow-elev1"
          : "border-hairline-soft hover:border-primary hover:shadow-elev1",
      ].join(" ")}
      onMouseEnter={() => onHover?.(building.building_id)}
      onMouseLeave={() => onHover?.(null)}
    >
      {/* 썸네일 — thumbnail_path 있으면 실제 외관 사진, 없으면 아이콘 */}
      <CardThumbnail path={building.thumbnail_path} name={building.name} />

      {/* 오른쪽 텍스트 칼럼 — min-w-0로 line-clamp 말줄임 정상 동작 */}
      <div className="min-w-0 flex-1">
      {/* 건물명 + 권역 배지 */}
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className="line-clamp-1 text-body-md font-bold text-ink-deep">
          {building.name}
        </span>
        {districtLabel !== null && (
          <Badge tone="district" className="shrink-0">
            {districtLabel}
          </Badge>
        )}
      </div>

      {/* 주소 */}
      {building.address_road !== null && (
        <p className="mb-2 line-clamp-1 text-body-sm text-steel">
          {building.address_road}
        </p>
      )}

      {/* 공실수 · 최저 평당임대료 */}
      <div className="flex items-center justify-between text-body-sm">
        <span className="text-ink">
          공실 {building.vacancy_count}개
        </span>
        <span
          className={
            rentDisplay === "임대료 문의" ? "text-steel" : "font-bold text-primary"
          }
        >
          {rentDisplay}
        </span>
      </div>
      </div>
    </Link>
  );
}
