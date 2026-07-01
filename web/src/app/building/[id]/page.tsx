// 건물 상세 페이지. 서버 컴포넌트에서 병렬 페치 후 섹션 조립.
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { getBuildingDetailBundle } from "@/lib/buildingDetail";
import {
  fetchBuildingImages,
  fetchCommercialArea,
} from "@/lib/queries";
import { PhotoGallery } from "@/components/PhotoGallery";
import { BuildingOverview } from "@/components/BuildingOverview";
import { BuildingLocationMap } from "@/components/BuildingLocationMap";
import { CommercialAreaSection } from "@/components/CommercialAreaSection";
import { FloorTable } from "@/components/FloorTable";
import { RentTrendChart } from "@/components/RentTrendChart";
import { Button } from "@/components/ui/Button";
import { SectionHeading } from "@/components/ui/SectionHeading";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { detail } = getBuildingDetailBundle(id);
  if (!detail) return { title: "건물을 찾을 수 없음" };
  return {
    title: detail.name,
    description: `${detail.name} - ${detail.address_road ?? ""} 오피스 임대 정보, 층별 공실과 임대료를 확인하세요.`,
  };
}

export default async function BuildingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // 상세 번들(detail+floors+rents)은 서버에서 SQLite 직접 조회(self-fetch 없음).
  // 이미지·상권은 현재 빈값이지만 시그니처 유지 위해 그대로 병렬 호출.
  const [{ detail, floors, rents: trend }, images, commercial] =
    await Promise.all([
      Promise.resolve(getBuildingDetailBundle(id)),
      fetchBuildingImages(id),
      fetchCommercialArea(id),
    ]);
  if (!detail) notFound();

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      {/* 목록으로 back link */}
      <div className="mb-6">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/">
            <ChevronLeft className="h-4 w-4" aria-hidden />
            목록으로
          </Link>
        </Button>
      </div>

      {/* 건물명 + 주소 */}
      <div className="mb-8">
        <SectionHeading level={1} className="text-heading-lg md:text-display-lg mb-1">
          {detail.name}
        </SectionHeading>
        {detail.address_road && (
          <p className="text-subtitle-md text-steel">{detail.address_road}</p>
        )}
        {/* 데이터 기준월 — trend 최신 snapshot_month 기준. 비었으면 생략. */}
        {trend.length > 0 && (() => {
          // snapshot_month는 YYYY-MM-DD. 사전순 최대값이 곧 최신월.
          const latest = trend.reduce((a, b) =>
            a.snapshot_month > b.snapshot_month ? a : b
          ).snapshot_month;
          // YYYY-MM-DD → YYYY.MM
          const label = latest.slice(0, 7).replace("-", ".");
          return (
            <p className="mt-1 text-caption text-stone">{label} 기준</p>
          );
        })()}
      </div>

      {/* 상단 2단 — 왼쪽 사진(7) / 오른쪽 건물개요(5). 모바일은 1단 세로. */}
      <section className="mb-12 grid grid-cols-1 gap-6 md:grid-cols-12">
        <div className="md:col-span-7">
          <PhotoGallery images={images} />
        </div>
        <div className="md:col-span-5">
          <BuildingOverview detail={detail} section="info" />
        </div>
      </section>

      {/* 위치 — 사진 바로 아래. 카카오 지도로 건물 1개 표시 */}
      <section className="mb-12">
        <SectionHeading level={3} className="mb-4">위치</SectionHeading>
        <BuildingLocationMap
          latitude={detail.latitude}
          longitude={detail.longitude}
          name={detail.name}
        />
        {detail.address_road && (
          <p className="mt-3 text-body-sm text-steel">{detail.address_road}</p>
        )}
      </section>

      {/* 건물 특장점 — 전폭 (있을 때만 섹션 렌더, 빈 여백 방지) */}
      {detail.features_raw && detail.features_raw.trim() !== "" && (
        <section className="mb-12">
          <BuildingOverview detail={detail} section="features" />
        </section>
      )}

      <section className="mb-12">
        <SectionHeading level={3} className="mb-4">층별 공실 현황</SectionHeading>
        <FloorTable floors={floors} />
      </section>

      <section className="mb-12">
        <SectionHeading level={3} className="mb-4">임대료 추이</SectionHeading>
        <RentTrendChart data={trend} />
      </section>

      {/* 발달상권/거주인구 등 지역 통계 — 맨 하단. 데이터 없으면 컴포넌트가 null 반환 */}
      <CommercialAreaSection data={commercial} />

      <section className="border-t border-hairline-soft pt-6 text-caption text-stone">
        데이터 출처: 중개사 임대안내문 및 국토교통부 건축물대장. 실제 계약 조건은
        별도 확인이 필요합니다.
      </section>
    </div>
  );
}
