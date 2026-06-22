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

// building_commercial_areas — 발달상권 요약 + 거주인구 (소상공인/행안부)
export interface IndustryCount {
  name: string;
  count: number;
}

export interface CommercialArea {
  building_id: string;
  area_name: string | null;
  store_count: number | null;
  retail_count: number | null;
  service_count: number | null;
  food_count: number | null;
  radius_m: number | null;
  base_period: string | null;
  top_industries: IndustryCount[] | null;
  dong_name: string | null;
  resident_total: number | null;
  resident_male: number | null;
  resident_female: number | null;
  household_count: number | null;
  resident_period: string | null;
  ldong_cd: string | null;
  // 직장인구(국민연금 사업장) — dong_workplace_stats 조인 결과
  workplace?: WorkplaceStats | null;
}

// dong_workplace_stats — 법정동 직장인구(국민연금 가입 사업장)
export interface WorkplaceStats {
  ldong_cd: string;
  biz_count: number | null;
  employee_total: number | null;
  top_industries: IndustryCount[] | null;       // 사업장수 기준
  top_industries_emp: IndustryCount[] | null;    // 종사자수 기준
  base_period: string | null;
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

// v_news_feed — 부동산 뉴스 소식
// sector: lease 제거, datacenter 추가 (0026 마이그레이션)
export type NewsSector = "office" | "retail" | "hotel" | "logistics" | "datacenter";

export const NEWS_SECTOR_LABELS: Record<NewsSector, string> = {
  office: "오피스",
  retail: "리테일",
  hotel: "호텔",
  logistics: "물류",
  datacenter: "데이터센터",
};

// subcategory: 동향 소분류 (tenant/landlord/deal/general)
export type NewsSubcategory = "tenant" | "landlord" | "deal" | "general";

export const NEWS_SUB_LABELS: Record<NewsSubcategory, string> = {
  tenant: "임차동향",
  landlord: "임대동향",
  deal: "매매·투자",
  general: "일반",
};

export interface NewsArticle {
  id: string;
  sector: NewsSector;
  subcategory: NewsSubcategory | null;
  title: string;
  description: string | null;
  press: string | null;
  thumbnail_url: string | null;
  display_link: string;
  published_at: string | null;
}
