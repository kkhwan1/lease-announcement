// GET /api/map — 지도 핀(좌표 보유 건물만).
// MVP: 로컬 데이터는 좌표 대부분 null → 대체로 빈 배열(지도 준비중).
import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { BuildingMapPin } from "@/lib/types";

export const dynamic = "force-dynamic";

export function GET() {
  const rows = getDb()
    .prepare(
      `SELECT
         b.building_id, b.name, b.district, b.latitude, b.longitude,
         (SELECT COUNT(*) FROM floor_availabilities f
            WHERE f.building_id = b.building_id AND f.is_total_row = 0) AS vacancy_count,
         (SELECT MIN(r.rent_per_pyeong) FROM rent_terms r
            WHERE r.building_id = b.building_id AND r.rent_per_pyeong > 0) AS min_rent_per_pyeong
       FROM buildings b
       WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL`,
    )
    .all() as Array<Record<string, unknown>>;

  const data: BuildingMapPin[] = rows.map((r) => ({
    building_id: r.building_id as string,
    name: r.name as string,
    district: (r.district ?? null) as BuildingMapPin["district"],
    latitude: r.latitude as number,
    longitude: r.longitude as number,
    vacancy_count: (r.vacancy_count as number) ?? 0,
    min_rent_per_pyeong:
      r.min_rent_per_pyeong == null ? null : String(r.min_rent_per_pyeong),
  }));

  return NextResponse.json(data);
}
