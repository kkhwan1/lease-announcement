// 사진 갤러리. building-images(public 버킷)의 실제 이미지를 표시한다.
// kind=other는 노이즈/오분류 가능성이 있어 숨긴다. 이미지가 없으면 placeholder.
"use client";

import { useState } from "react";
import { Building2 } from "lucide-react";
import type { BuildingImage } from "@/lib/types";
import { buildingImageUrl } from "@/lib/supabase";

const KIND_LABELS: Record<string, string> = {
  exterior: "외관",
  lobby: "로비",
  interior: "내부",
  floor_plan: "평면도",
  location_map: "위치도",
};

// 갤러리에 노출할 종류 (other 제외) + 표시 우선순위.
const KIND_ORDER: Record<string, number> = {
  exterior: 0,
  lobby: 1,
  interior: 2,
  floor_plan: 3,
  location_map: 4,
};

interface PhotoGalleryProps {
  images: BuildingImage[];
}

/** 이미지 1장 — 로드 실패 시 자기 자신을 placeholder로 교체. */
function GalleryImage({ image, hero = false }: { image: BuildingImage; hero?: boolean }) {
  const [failed, setFailed] = useState(false);
  const label = KIND_LABELS[image.kind] ?? image.kind;

  if (failed) {
    return (
      <div
        className={[
          "flex flex-col items-center justify-center gap-2",
          "bg-gradient-to-br from-surface-soft to-primary-soft text-stone",
          hero ? "rounded-xxxl aspect-[16/9]" : "rounded-xl aspect-[4/3]",
        ].join(" ")}
      >
        <Building2 className="h-8 w-8" aria-hidden />
        <span className="text-caption text-steel">{label}</span>
      </div>
    );
  }

  return (
    <div
      className={[
        "relative overflow-hidden",
        hero ? "rounded-xxxl aspect-[16/9]" : "rounded-xl aspect-[4/3]",
      ].join(" ")}
    >
      {/* public 버킷이라 일반 img 사용 (next/image 도메인 설정 불필요) */}
      {/* TODO: storage_path가 채워지면 아래 img src가 자동으로 실제 이미지를 표시함 */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={buildingImageUrl(image.storage_path)}
        alt={label}
        loading="lazy"
        className="h-full w-full object-cover"
        onError={() => setFailed(true)}
      />
      <span className="absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-caption font-medium text-white">
        {label}
      </span>
    </div>
  );
}

export function PhotoGallery({ images }: PhotoGalleryProps) {
  // other 제외 + 위치도(location_map)는 별도 지도로 대체하므로 갤러리에서 제외.
  // 우선순위 정렬, 최대 6장.
  const visible = images
    .filter(
      (img) =>
        img.kind !== "other" &&
        img.kind !== "location_map" &&
        img.storage_path,
    )
    .sort(
      (a, b) =>
        (KIND_ORDER[a.kind] ?? 99) - (KIND_ORDER[b.kind] ?? 99) ||
        (a.page_number ?? 0) - (b.page_number ?? 0),
    )
    .slice(0, 6);

  // 표시할 실제 이미지가 없으면 히어로 placeholder.
  if (visible.length === 0) {
    return (
      <div className="flex aspect-[16/9] flex-col items-center justify-center gap-2 rounded-xxxl bg-gradient-to-br from-surface-soft to-primary-soft text-stone">
        <Building2 className="h-10 w-10" aria-hidden />
        <span className="text-caption text-steel">사진 준비 중</span>
      </div>
    );
  }

  const [hero, ...rest] = visible;

  return (
    <div className="flex flex-col gap-3">
      {/* 첫 번째 이미지: 히어로 타일 (16/9 대형, card-feature-photo 스타일) */}
      <GalleryImage image={hero} hero />

      {/* 나머지 이미지: 썸네일 그리드 (4/3) */}
      {rest.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {rest.map((img) => (
            <GalleryImage key={img.storage_path} image={img} />
          ))}
        </div>
      )}
    </div>
  );
}
