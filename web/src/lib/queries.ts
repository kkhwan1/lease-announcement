// 공개 데이터 조회 함수. Supabase 뷰를 anon 키로 직접 SELECT.
import { supabase } from "./supabase";
import type {
  BuildingSummary,
  BuildingMapPin,
  BuildingDetail,
  CommercialArea,
  FloorVacancy,
  RentTrendPoint,
  BuildingImage,
  NewsArticle,
} from "./types";

export interface BuildingFilter {
  district?: string;
  minRent?: number; // 평당 원
  maxRent?: number;
  immediateOnly?: boolean;
  keyword?: string;
}

/** PostgREST 필터 문자열에서 구조 조작 가능 문자를 제거/치환.
 *  쉼표·괄호·별표·역슬래시는 .or()/ilike 패턴 문법과 충돌하므로 안전 처리. */
function sanitizePostgrestTerm(s: string): string {
  return s.replace(/[,()\\*%]/g, " ").trim();
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
    const kw = sanitizePostgrestTerm(filter.keyword);
    if (kw) {
      q = q.or(`name.ilike.%${kw}%,address_road.ilike.%${kw}%`);
    }
  }
  // 임대료 필터: 범위를 명시한 경우에만 적용(미상 건물은 필터 미적용 시 노출됨).
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

/** 건물 발달상권 요약 1건(없으면 null). 법정동 직장인구(국민연금)도 조인. */
export async function fetchCommercialArea(
  id: string,
): Promise<CommercialArea | null> {
  const { data, error } = await supabase
    .from("building_commercial_areas")
    .select("*")
    .eq("building_id", id)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;

  const area = data as CommercialArea;
  // 법정동코드로 직장인구(사업장·종사자) 조인
  if (area.ldong_cd) {
    const { data: wp } = await supabase
      .from("dong_workplace_stats")
      .select("*")
      .eq("ldong_cd", area.ldong_cd)
      .maybeSingle();
    area.workplace = (wp as CommercialArea["workplace"]) ?? null;
  }
  return area;
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

/** 허용 섹터 코드. "all" 포함. */
const VALID_SECTORS = new Set(["all", "office", "retail", "hotel", "logistics", "datacenter"]);

/** 허용 서브카테고리 코드. "all" 포함. */
const VALID_SUBS = new Set(["all", "tenant", "landlord", "deal", "general"]);

/** 허용 기간 필터. */
const VALID_PERIODS = new Set(["all", "day", "week", "month"]);
const PERIOD_DAYS: Record<string, number> = { day: 1, week: 7, month: 30 };

export interface NewsFilter {
  sector?: string; // 기본 "all"
  sub?: string; // 기본 "all"
  q?: string; // 검색어 (title/description ilike)
  period?: string; // "day" | "week" | "month" | "all"
  sortAsc?: boolean; // 기본 false(=desc 최신순)
  limit?: number; // 기본 60
  offset?: number; // 기본 0
}

/** 뉴스 소식 목록. 모든 필터는 화이트리스트/sanitize로 방어. */
export async function fetchNews(filter: NewsFilter = {}): Promise<NewsArticle[]> {
  const {
    sector = "all",
    sub = "all",
    q: keyword = "",
    period = "all",
    sortAsc = false,
    limit = 60,
    offset = 0,
  } = filter;

  const safeSector = VALID_SECTORS.has(sector) ? sector : "all";
  const safeSub = VALID_SUBS.has(sub) ? sub : "all";
  const safePeriod = VALID_PERIODS.has(period) ? period : "all";

  let q = supabase.from("v_news_feed").select("*");

  if (safeSector !== "all") q = q.eq("sector", safeSector);
  if (safeSub !== "all") q = q.eq("subcategory", safeSub);

  if (keyword) {
    const kw = sanitizePostgrestTerm(keyword);
    if (kw) q = q.or(`title.ilike.%${kw}%,description.ilike.%${kw}%`);
  }

  if (safePeriod !== "all") {
    const since = new Date(Date.now() - PERIOD_DAYS[safePeriod] * 86400_000);
    q = q.gte("published_at", since.toISOString());
  }

  const { data, error } = await q
    .order("published_at", { ascending: sortAsc })
    .range(offset, offset + limit - 1);
  if (error) throw error;
  return (data ?? []) as NewsArticle[];
}
