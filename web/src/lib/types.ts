// DB 뷰/테이블에 대응하는 타입. Supabase 뷰 컬럼명과 1:1.

export type District = "GBD" | "CBD" | "YBD" | "BBD" | "ETC";

export const DISTRICT_LABELS: Record<District, string> = {
  GBD: "강남권역",
  CBD: "도심권역",
  YBD: "여의도권역",
  BBD: "분당권역",
  ETC: "기타",
};

// v_buildings_summary — 홈/검색 카드 리스트
export interface BuildingSummary {
  building_id: string;
  name: string;
  district: District | null;
  address_road: string | null;
  latitude: number | null;
  longitude: number | null;
  completed_year: number | null;
  floors_above: number | null;
  floors_below: number | null;
  vacancy_count: number;
  min_rent_per_pyeong: string | null; // numeric → string (supabase-js)
  thumbnail_path: string | null;
}

// v_buildings_map — 지도 핀(경량)
export interface BuildingMapPin {
  building_id: string;
  name: string;
  district: District | null;
  latitude: number;
  longitude: number;
  vacancy_count: number;
  min_rent_per_pyeong: string | null;
}

// v_building_detail — 상세 한 방 조회
export interface BuildingDetail {
  building_id: string;
  name: string;
  name_raw: string | null;
  district: District | null;
  address_road: string | null;
  address_raw: string | null;
  station_area: string | null;
  latitude: number | null;
  longitude: number | null;
  floors_above: number | null;
  floors_below: number | null;
  gross_area_sqm: string | null;
  gross_area_pyeong: string | null;
  efficiency_ratio: string | null;
  completed_year: number | null;
  ceiling_height_m: string | null;
  ev_count: number | null;
  parking_total: number | null;
  features_raw: string | null;
  main_purpose: string | null;
  building_coverage_ratio: string | null;
  floor_area_ratio: string | null;
  height_m: string | null;
  land_area_sqm: string | null;
  use_zone: string | null;
}

// v_current_vacancies 일부 — 상세 층별 공실 (building_id 필터)
export interface FloorVacancy {
  floor_label: string | null;
  floor_number: number | null;
  exclusive_area_pyeong: string | null;
  lease_area_pyeong: string | null;
  exclusive_area_sqm: string | null;
  lease_area_sqm: string | null;
  availability_kind: string | null;
  availability_raw: string | null;
  rent_per_pyeong: string | null;
  maintenance_per_pyeong: string | null;
  deposit_per_pyeong: string | null;
}

// v_rent_trend — 월별 임대료 추이
export interface RentTrendPoint {
  building_id: string;
  broker: string;
  snapshot_month: string; // YYYY-MM-DD
  scope_label: string | null;
  rent_per_pyeong: string | null;
  maintenance_per_pyeong: string | null;
  deposit_per_pyeong: string | null;
}

// building_images
export interface BuildingImage {
  storage_path: string;
  kind: string;
  page_number: number | null;
}
