// 건물 상세 번들 조회 (서버 전용 — SQLite 직접 호출).
// RSC(상세 페이지)와 /api/buildings/[id] Route Handler가 공유.
// self-fetch를 없애 Vercel Deployment Protection(배포URL SSO)에 걸리지 않게 한다.
import { getDb } from "./db";
import type { BuildingDetail, FloorVacancy, RentTrendPoint } from "./types";

export interface BuildingDetailBundle {
  detail: BuildingDetail | null;
  floors: FloorVacancy[];
  rents: RentTrendPoint[];
}

export function getBuildingDetailBundle(id: string): BuildingDetailBundle {
  const db = getDb();

  const b = db
    .prepare(`SELECT * FROM buildings WHERE building_id = ? LIMIT 1`)
    .get(id) as Record<string, unknown> | undefined;

  if (!b) return { detail: null, floors: [], rents: [] };

  const s = (v: unknown) => (v == null ? null : String(v));

  const detail: BuildingDetail = {
    building_id: b.building_id as string,
    name: b.name as string,
    name_raw: (b.name_raw ?? null) as string | null,
    district: (b.district ?? null) as BuildingDetail["district"],
    address_road: (b.address_road ?? null) as string | null,
    address_raw: (b.address_raw ?? null) as string | null,
    station_area: (b.station_area ?? null) as string | null,
    latitude: (b.latitude ?? null) as number | null,
    longitude: (b.longitude ?? null) as number | null,
    floors_above: (b.floors_above ?? null) as number | null,
    floors_below: (b.floors_below ?? null) as number | null,
    gross_area_sqm: s(b.gross_area_sqm),
    gross_area_pyeong: s(b.gross_area_pyeong),
    efficiency_ratio: s(b.efficiency_ratio),
    completed_year: (b.completed_year ?? null) as number | null,
    ceiling_height_m: s(b.ceiling_height_m),
    ev_count: (b.ev_count ?? null) as number | null,
    parking_total: (b.parking_total ?? null) as number | null,
    features_raw: (b.features_raw ?? null) as string | null,
    main_purpose: (b.main_purpose ?? null) as string | null,
    building_coverage_ratio: s(b.building_coverage_ratio),
    floor_area_ratio: s(b.floor_area_ratio),
    height_m: s(b.height_m),
    land_area_sqm: s(b.land_area_sqm),
    use_zone: (b.use_zone ?? null) as string | null,
  };

  const floorRows = db
    .prepare(
      `SELECT floor_label, floor_number, exclusive_area_pyeong, lease_area_pyeong,
              exclusive_area_sqm, lease_area_sqm, availability_kind, availability_raw
         FROM floor_availabilities
        WHERE building_id = ? AND is_total_row = 0
        ORDER BY floor_number DESC`,
    )
    .all(id) as Array<Record<string, unknown>>;

  const rentRows = db
    .prepare(
      `SELECT scope_label, rent_per_pyeong, maintenance_per_pyeong, deposit_per_pyeong
         FROM rent_terms WHERE building_id = ?`,
    )
    .all(id) as Array<Record<string, unknown>>;
  const rentByScope = new Map<string, Record<string, unknown>>();
  for (const r of rentRows) {
    if (r.scope_label != null) rentByScope.set(String(r.scope_label), r);
  }

  const floors: FloorVacancy[] = floorRows.map((f) => {
    const rent =
      f.floor_label != null ? rentByScope.get(String(f.floor_label)) : undefined;
    return {
      floor_label: (f.floor_label ?? null) as string | null,
      floor_number: (f.floor_number ?? null) as number | null,
      exclusive_area_pyeong: s(f.exclusive_area_pyeong),
      lease_area_pyeong: s(f.lease_area_pyeong),
      exclusive_area_sqm: s(f.exclusive_area_sqm),
      lease_area_sqm: s(f.lease_area_sqm),
      availability_kind: (f.availability_kind ?? null) as string | null,
      availability_raw: (f.availability_raw ?? null) as string | null,
      rent_per_pyeong: s(rent?.rent_per_pyeong),
      maintenance_per_pyeong: s(rent?.maintenance_per_pyeong),
      deposit_per_pyeong: s(rent?.deposit_per_pyeong),
    };
  });

  const month = (b.source_month as string) || "2026-06";
  const rents: RentTrendPoint[] = rentRows.map((r) => ({
    building_id: id,
    broker: (b.broker as string) ?? "",
    snapshot_month: /^\d{4}-\d{2}$/.test(month) ? `${month}-01` : month,
    scope_label: (r.scope_label ?? null) as string | null,
    rent_per_pyeong: s(r.rent_per_pyeong),
    maintenance_per_pyeong: s(r.maintenance_per_pyeong),
    deposit_per_pyeong: s(r.deposit_per_pyeong),
  }));

  return { detail, floors, rents };
}
