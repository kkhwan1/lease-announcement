// 사진 갤러리. building-images(public 버킷)의 실제 이미지를 표시한다.
// kind=other는 노이즈/오분류 가능성이 있어 숨긴다. 이미지가 없으면 placeholder.
"use client";

import { useState, useEffect, useCallback } from "react";
import { Building2, X, ChevronLeft, ChevronRight } from "lucide-react";
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
function GalleryImage({
  image,
  hero = false,
  onClick,
}: {
  image: BuildingImage;
  hero?: boolean;
  onClick?: () => void;
}) {
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
        onClick ? "cursor-pointer" : "",
      ].join(" ")}
      onClick={onClick}
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

/** 라이트박스 오버레이 — 클릭된 이미지를 전체화면 모달로 표시. ESC/배경/X 버튼으로 닫힘. */
function Lightbox({
  images,
  initialIndex,
  onClose,
}: {
  images: BuildingImage[];
  initialIndex: number;
  onClose: () => void;
}) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const current = images[currentIndex];
  const [failed, setFailed] = useState(false);
  const label = KIND_LABELS[current.kind] ?? current.kind;

  // 인덱스가 바뀌면 실패 상태 초기화
  useEffect(() => {
    setFailed(false);
  }, [currentIndex]);

  const goPrev = useCallback(() => {
    setCurrentIndex((i) => (i - 1 + images.length) % images.length);
  }, [images.length]);

  const goNext = useCallback(() => {
    setCurrentIndex((i) => (i + 1) % images.length);
  }, [images.length]);

  // ESC 키 닫기, 화살표 키 이동
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, goPrev, goNext]);

  // 라이트박스 열릴 때 body 스크롤 잠금
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="사진 크게 보기"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      {/* 모달 컨텐츠 — 배경 클릭 이벤트 전파 차단 */}
      <div
        className="relative flex max-h-[90vh] max-w-[90vw] flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 닫기 버튼 */}
        <button
          type="button"
          aria-label="닫기"
          onClick={onClose}
          className="absolute -top-10 right-0 flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-white transition-colors hover:bg-white/35"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>

        {/* 이미지 영역 */}
        <div className="relative flex items-center justify-center">
          {/* 이전 버튼 */}
          {images.length > 1 && (
            <button
              type="button"
              aria-label="이전 사진"
              onClick={goPrev}
              className="absolute -left-12 flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-white transition-colors hover:bg-white/35"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </button>
          )}

          {/* 메인 이미지 */}
          {failed ? (
            <div className="flex h-64 w-96 flex-col items-center justify-center gap-2 rounded-xl bg-surface-soft text-stone">
              <Building2 className="h-10 w-10" aria-hidden />
              <span className="text-caption text-steel">{label}</span>
            </div>
          ) : (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={buildingImageUrl(current.storage_path)}
              alt={label}
              className="max-h-[80vh] max-w-[80vw] rounded-xl object-contain"
              onError={() => setFailed(true)}
            />
          )}

          {/* 다음 버튼 */}
          {images.length > 1 && (
            <button
              type="button"
              aria-label="다음 사진"
              onClick={goNext}
              className="absolute -right-12 flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-white transition-colors hover:bg-white/35"
            >
              <ChevronRight className="h-5 w-5" aria-hidden />
            </button>
          )}
        </div>

        {/* 이미지 정보 + 카운터 */}
        <div className="mt-3 flex items-center gap-3 text-white">
          <span className="rounded bg-black/55 px-2 py-0.5 text-caption font-medium">
            {label}
          </span>
          {images.length > 1 && (
            <span className="text-caption text-white/70">
              {currentIndex + 1} / {images.length}
            </span>
          )}
        </div>
      </div>
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

  // 라이트박스 열린 이미지 인덱스 (null이면 닫힘)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

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
    <>
      <div className="flex flex-col gap-3">
        {/* 첫 번째 이미지: 히어로 타일 (16/9 대형, card-feature-photo 스타일) */}
        <GalleryImage image={hero} hero onClick={() => setLightboxIndex(0)} />

        {/* 나머지 이미지: 썸네일 그리드 (4/3) */}
        {rest.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {rest.map((img, i) => (
              <GalleryImage
                key={img.storage_path}
                image={img}
                onClick={() => setLightboxIndex(i + 1)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 라이트박스 오버레이 */}
      {lightboxIndex !== null && (
        <Lightbox
          images={visible}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </>
  );
}
