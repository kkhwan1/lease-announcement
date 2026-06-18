// 사진 갤러리. 현재 이미지가 Storage에 미업로드 상태이므로 placeholder 위주.
// 후속 이미지 업로드 시 storage_path로 실제 이미지 표시하도록 확장 예정.
import { Building2 } from "lucide-react";
import type { BuildingImage } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  exterior: "외관",
  lobby: "로비",
  interior: "내부",
  floor_plan: "평면도",
  location_map: "위치도",
  other: "기타",
};

interface PhotoGalleryProps {
  images: BuildingImage[];
}

export function PhotoGallery({ images }: PhotoGalleryProps) {
  // 현재는 실제 이미지 파일이 없으므로 종류별 placeholder만 표시.
  const kinds = images.length
    ? Array.from(new Set(images.map((i) => i.kind)))
    : ["exterior"];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {kinds.slice(0, 6).map((kind) => (
        <div
          key={kind}
          className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded border border-border bg-surface text-muted"
        >
          <Building2 className="h-8 w-8" aria-hidden />
          <span className="text-xs">{KIND_LABELS[kind] ?? kind}</span>
        </div>
      ))}
    </div>
  );
}
