// GET /api/buildings — 홈/검색 카드 리스트. SQLite 조회 + 파생 계산.
// 필터: district, keyword(name/address_road), minRent, maxRent (평당 원).
// v_buildings_summary 뷰를 SQL로 재현: vacancy_count, min_rent_per_pyeong 파생.
import { NextResponse, type NextRequest } from "next/server";
import { getDb } from "@/lib/db";
import type { BuildingSummary } from "@/lib/types";

export const dynamic = "force-dynamic"; // 필터별 매 요청 조회

export function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const district = sp.get("district") ?? undefined;
  const keyword = sp.get("keyword")?.trim() || undefined;
  const minRent = sp.get("minRent");
  const maxRent = sp.get("maxRent");

  const where: string[] = [];
  const params: Record<string, unknown> = {};

  if (district && district !== "ALL") {
    where.push("b.district = @district");
    params.district = district;
  }
  if (keyword) {
    // LIKE 특수문자(% _) 이스케이프 후 바인딩 → 인젝션·패턴오염 방어
    const kw = `%${keyword.replace(/[%_\\]/g, "\\$&")}%`;
    where.push(
      "(b.name LIKE @kw ESCAPE '\\' OR b.address_road LIKE @kw ESCAPE '\\')",
    );
    params.kw = kw;
  }

  // 임대료 필터는 파생 별칭(min_rent_per_pyeong)이라 바깥 쿼리로 래핑해 필터.
  const outerWhere: string[] = [];
  if (minRent !== null && minRent !== "") {
    outerWhere.push("min_rent_per_pyeong >= @minRent");
    params.minRent = Number(minRent);
  }
  if (maxRent !== null && maxRent !== "") {
    outerWhere.push("min_rent_per_pyeong <= @maxRent");
    params.maxRent = Number(maxRent);
  }

  const sql = `
    SELECT * FROM (
      SELECT
        b.building_id,
        b.name,
        b.district,
        b.address_road,
        b.latitude,
        b.longitude,
        b.completed_year,
        b.floors_above,
        b.floors_below,
        (SELECT COUNT(*) FROM floor_availabilities f
           WHERE f.building_id = b.building_id AND f.is_total_row = 0) AS vacancy_count,
        (SELECT MIN(r.rent_per_pyeong) FROM rent_terms r
           WHERE r.building_id = b.building_id AND r.rent_per_pyeong > 0) AS min_rent_per_pyeong,
        NULL AS thumbnail_path
      FROM buildings b
      ${where.length ? "WHERE " + where.join(" AND ") : ""}
    )
    ${outerWhere.length ? "WHERE " + outerWhere.join(" AND ") : ""}
    ORDER BY vacancy_count DESC
  `;

  const rows = getDb().prepare(sql).all(params) as Array<
    Record<string, unknown>
  >;
  // supabase-js는 numeric을 string으로 주던 관례 → min_rent_per_pyeong을 string化해 타입 유지.
  const data: BuildingSummary[] = rows.map((r) => ({
    building_id: r.building_id as string,
    name: r.name as string,
    district: (r.district ?? null) as BuildingSummary["district"],
    address_road: (r.address_road ?? null) as string | null,
    latitude: (r.latitude ?? null) as number | null,
    longitude: (r.longitude ?? null) as number | null,
    completed_year: (r.completed_year ?? null) as number | null,
    floors_above: (r.floors_above ?? null) as number | null,
    floors_below: (r.floors_below ?? null) as number | null,
    vacancy_count: (r.vacancy_count as number) ?? 0,
    min_rent_per_pyeong:
      r.min_rent_per_pyeong == null ? null : String(r.min_rent_per_pyeong),
    thumbnail_path: null,
  }));

  return NextResponse.json(data);
}
