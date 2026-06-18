// 공개 데이터 조회 함수. Supabase 뷰를 anon 키로 직접 SELECT.
import { supabase } from "./supabase";
import type {
  BuildingSummary,
  BuildingMapPin,
  BuildingDetail,
  FloorVacancy,
  RentTrendPoint,
  BuildingImage,
} from "./types";

export interface BuildingFilter {
  district?: string;
  minRent?: number; // 평당 원
  maxRent?: number;
  immediateOnly?: boolean;
  keyword?: string;
}

/** 홈/검색 카드 리스트. 필터 적용. */
export async function fetchBuildingSummaries(
  filter: BuildingFilter = {},
): Promise<BuildingSummary[]> {
  let q = supabase.from("v_buildings_summary").select("*");

  if (filter.district && filter.district !== "ALL") {
    q = q.eq("district", filter.district);
  }
  if (filter.keyword) {
    q = q.or(
      `name.ilike.%${filter.keyword}%,address_road.ilike.%${filter.keyword}%`,
    );
  }
  if (filter.minRent !== undefined) {
    q = q.gte("min_rent_per_pyeong", filter.minRent);
  }
  if (filter.maxRent !== undefined) {
    q = q.lte("min_rent_per_pyeong", filter.maxRent);
  }

  const { data, error } = await q.order("vacancy_count", { ascending: false });
  if (error) throw error;
  return (data ?? []) as BuildingSummary[];
}

/** 지도 핀(좌표 보유 건물만). */
export async function fetchMapPins(): Promise<BuildingMapPin[]> {
  const { data, error } = await supabase.from("v_buildings_map").select("*");
  if (error) throw error;
  return (data ?? []) as BuildingMapPin[];
}

/** 건물 상세 1건. */
export async function fetchBuildingDetail(
  id: string,
): Promise<BuildingDetail | null> {
  const { data, error } = await supabase
    .from("v_building_detail")
    .select("*")
    .eq("building_id", id)
    .maybeSingle();
  if (error) throw error;
  return (data as BuildingDetail) ?? null;
}

/** 건물 층별 공실(최신 스냅샷). */
export async function fetchFloorVacancies(
  buildingId: string,
): Promise<FloorVacancy[]> {
  const { data, error } = await supabase
    .from("v_current_vacancies")
    .select(
      "floor_label, floor_number, exclusive_area_pyeong, lease_area_pyeong, exclusive_area_sqm, lease_area_sqm, availability_kind, availability_raw, rent_per_pyeong, maintenance_per_pyeong, deposit_per_pyeong",
    )
    .eq("building_id", buildingId)
    .eq("is_total_row", false)
    .order("floor_number", { ascending: false, nullsFirst: false });
  if (error) throw error;
  return (data ?? []) as FloorVacancy[];
}

/** 건물 임대료 추이(전체 월). */
export async function fetchRentTrend(
  buildingId: string,
): Promise<RentTrendPoint[]> {
  const { data, error } = await supabase
    .from("v_rent_trend")
    .select("*")
    .eq("building_id", buildingId)
    .order("snapshot_month", { ascending: true });
  if (error) throw error;
  return (data ?? []) as RentTrendPoint[];
}

/** 건물 이미지 목록. */
export async function fetchBuildingImages(
  buildingId: string,
): Promise<BuildingImage[]> {
  const { data, error } = await supabase
    .from("building_images")
    .select("storage_path, kind, page_number")
    .eq("building_id", buildingId)
    .order("page_number", { ascending: true, nullsFirst: false });
  if (error) throw error;
  return (data ?? []) as BuildingImage[];
}
