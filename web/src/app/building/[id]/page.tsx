// 건물 상세 페이지. 서버 컴포넌트에서 병렬 페치 후 섹션 조립.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  fetchBuildingDetail,
  fetchFloorVacancies,
  fetchRentTrend,
  fetchBuildingImages,
} from "@/lib/queries";
import { PhotoGallery } from "@/components/PhotoGallery";
import { BuildingOverview } from "@/components/BuildingOverview";
import { FloorTable } from "@/components/FloorTable";
import { RentTrendChart } from "@/components/RentTrendChart";

export default async function BuildingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const detail = await fetchBuildingDetail(id);
  if (!detail) notFound();

  const [floors, trend, images] = await Promise.all([
    fetchFloorVacancies(id),
    fetchRentTrend(id),
    fetchBuildingImages(id),
  ]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <Link
        href="/"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-foreground"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
        목록으로
      </Link>

      <h1 className="mb-1 text-2xl font-bold">{detail.name}</h1>
      {detail.address_road && (
        <p className="mb-4 text-muted">{detail.address_road}</p>
      )}

      <section className="mb-6">
        <PhotoGallery images={images} />
      </section>

      <section className="mb-6">
        <BuildingOverview detail={detail} />
      </section>

      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold">층별 공실 현황</h2>
        <FloorTable floors={floors} />
      </section>

      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold">임대료 추이</h2>
        <RentTrendChart data={trend} />
      </section>

      <section className="border-t border-border pt-4 text-xs text-muted">
        데이터 출처: 중개사 임대안내문 및 국토교통부 건축물대장. 실제 계약 조건은
        별도 확인이 필요합니다.
      </section>
    </div>
  );
}
