// 공개 데이터 조회 함수. MVP: 로컬 SQLite를 /api Route Handler 경유로 조회.
// (Supabase pause 우회. 함수 시그니처·반환 타입은 기존과 동일 → 컴포넌트 무수정.)
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

/** 서버(RSC)/클라 겸용 절대 base URL.
 *  - 브라우저: 상대경로("")로 충분.
 *  - 서버: 절대 URL 필요 → env 또는 localhost 폴백. */
function getBaseUrl(): string {
  if (typeof window !== "undefined") return "";
  // Vercel(프로덕션/프리뷰)은 VERCEL_URL(호스트만) 자동 주입 → https 스킴 부여.
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return (
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.PORT ? `http://localhost:${process.env.PORT}` : "http://localhost:3000")
  );
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${getBaseUrl()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return (await res.json()) as T;
}

/** 홈/검색 카드 리스트. 필터 적용. */
export async function fetchBuildingSummaries(
  filter: BuildingFilter = {},
): Promise<BuildingSummary[]> {
  const sp = new URLSearchParams();
  if (filter.district && filter.district !== "ALL") sp.set("district", filter.district);
  if (filter.keyword) sp.set("keyword", filter.keyword);
  if (filter.minRent !== undefined) sp.set("minRent", String(filter.minRent));
  if (filter.maxRent !== undefined) sp.set("maxRent", String(filter.maxRent));
  const qs = sp.toString();
  return getJson<BuildingSummary[]>(`/api/buildings${qs ? `?${qs}` : ""}`);
}

/** 지도 핀(좌표 보유 건물만). */
export async function fetchMapPins(): Promise<BuildingMapPin[]> {
  return getJson<BuildingMapPin[]>(`/api/map`);
}

// 상세 응답 묶음 (Route Handler /api/buildings/[id] 반환 형태)
interface BuildingDetailBundle {
  detail: BuildingDetail | null;
  floors: FloorVacancy[];
  rents: RentTrendPoint[];
}

/** 상세 번들 캐시(같은 렌더에서 detail/floors/rents 3회 호출을 1 fetch로). */
const bundleCache = new Map<string, Promise<BuildingDetailBundle>>();
function fetchBundle(id: string): Promise<BuildingDetailBundle> {
  let p = bundleCache.get(id);
  if (!p) {
    p = getJson<BuildingDetailBundle>(`/api/buildings/${encodeURIComponent(id)}`);
    bundleCache.set(id, p);
  }
  return p;
}

/** 건물 상세 1건. */
export async function fetchBuildingDetail(
  id: string,
): Promise<BuildingDetail | null> {
  return (await fetchBundle(id)).detail;
}

/** 건물 발달상권 요약 — MVP: 로컬 데이터 없음 → null(섹션 숨김). */
export async function fetchCommercialArea(
  _id: string,
): Promise<CommercialArea | null> {
  return null;
}

/** 건물 층별 공실(최신 스냅샷). */
export async function fetchFloorVacancies(
  buildingId: string,
): Promise<FloorVacancy[]> {
  return (await fetchBundle(buildingId)).floors;
}

/** 건물 임대료 추이. MVP: 단일 월 스냅샷 점들. */
export async function fetchRentTrend(
  buildingId: string,
): Promise<RentTrendPoint[]> {
  return (await fetchBundle(buildingId)).rents;
}

/** 건물 이미지 목록 — MVP: 이미지 데이터 없음 → 빈 배열(플레이스홀더). */
export async function fetchBuildingImages(
  _buildingId: string,
): Promise<BuildingImage[]> {
  return [];
}

export interface NewsFilter {
  sector?: string;
  sub?: string;
  q?: string;
  period?: string;
  sortAsc?: boolean;
  limit?: number;
  offset?: number;
}

/** 뉴스 소식 목록 — MVP: 로컬 데이터 없음 → 빈 배열(준비중). */
export async function fetchNews(_filter: NewsFilter = {}): Promise<NewsArticle[]> {
  return getJson<NewsArticle[]>(`/api/news`);
}
