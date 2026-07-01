// out/*.json (304건) → web/data/lease.db 로컬 SQLite 빌드.
// Supabase pause 우회용 MVP 데이터 계층. 재실행 멱등(파일 삭제 후 재생성).
//
// 실행: cd web && node scripts/build-db.mjs
import Database from "better-sqlite3";
import { readFileSync, readdirSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = join(__dirname, "..");
const PROJECT_ROOT = join(WEB_ROOT, ".."); // "Lease Announcemen/"
const OUT_DIR = join(PROJECT_ROOT, "out");
const DATA_DIR = join(WEB_ROOT, "data");
const DB_PATH = join(DATA_DIR, "lease.db");

// building_id slug: URL-safe ASCII만. 한글/특수문자가 섞이면 Next.js 동적 라우트
// (params 인코딩/디코딩)에서 깨지므로, 비ASCII는 제거하고 broker+인덱스로 유일성 보장.
function slugify(broker, name, index) {
  const ascii = `${name}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-") // 영숫자 외(한글 포함) → 하이픈
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  const brokerLc = String(broker).toLowerCase();
  // ascii가 비면(순수 한글명) 인덱스로 대체. 항상 broker prefix + 인덱스로 충돌 원천 차단.
  return `${brokerLc}-${ascii || "b"}-${index}`;
}

function main() {
  if (!existsSync(OUT_DIR)) {
    throw new Error(`소스 디렉토리 없음: ${OUT_DIR}`);
  }
  mkdirSync(DATA_DIR, { recursive: true });
  rmSync(DB_PATH, { force: true }); // 멱등: 기존 DB 제거 후 재생성

  const db = new Database(DB_PATH);
  // 빌드용은 WAL 불필요. 단일 파일로 유지(dev 서버가 readonly로 열 때 -wal/-shm 잔재 충돌 방지).
  db.pragma("journal_mode = DELETE");

  db.exec(`
    CREATE TABLE buildings (
      building_id TEXT PRIMARY KEY,
      broker TEXT,
      name TEXT NOT NULL,
      name_raw TEXT,
      district TEXT,
      address_road TEXT,
      address_raw TEXT,
      station_area TEXT,
      latitude REAL,
      longitude REAL,
      floors_above INTEGER,
      floors_below INTEGER,
      gross_area_sqm REAL,
      gross_area_pyeong REAL,
      exclusive_area_sqm REAL,
      exclusive_area_pyeong REAL,
      efficiency_ratio REAL,
      completed_year INTEGER,
      ceiling_height_m REAL,
      ev_count INTEGER,
      parking_total INTEGER,
      features_raw TEXT,
      main_purpose TEXT,
      building_coverage_ratio REAL,
      floor_area_ratio REAL,
      height_m REAL,
      land_area_sqm REAL,
      use_zone TEXT,
      source_month TEXT
    );

    CREATE TABLE floor_availabilities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      building_id TEXT NOT NULL REFERENCES buildings(building_id),
      floor_label TEXT,
      floor_number INTEGER,
      is_total_row INTEGER DEFAULT 0,
      exclusive_area_sqm REAL,
      exclusive_area_pyeong REAL,
      lease_area_sqm REAL,
      lease_area_pyeong REAL,
      availability_kind TEXT,
      availability_raw TEXT
    );

    CREATE TABLE rent_terms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      building_id TEXT NOT NULL REFERENCES buildings(building_id),
      scope_label TEXT,
      deposit_per_pyeong REAL,
      rent_per_pyeong REAL,
      maintenance_per_pyeong REAL
    );

    CREATE INDEX idx_floor_building ON floor_availabilities(building_id);
    CREATE INDEX idx_rent_building ON rent_terms(building_id);
    CREATE INDEX idx_building_district ON buildings(district);
  `);

  const insBuilding = db.prepare(`
    INSERT INTO buildings (
      building_id, broker, name, name_raw, district, address_road, address_raw,
      station_area, latitude, longitude, floors_above, floors_below,
      gross_area_sqm, gross_area_pyeong, exclusive_area_sqm, exclusive_area_pyeong,
      efficiency_ratio, completed_year, ceiling_height_m, ev_count, parking_total,
      features_raw, main_purpose, building_coverage_ratio, floor_area_ratio,
      height_m, land_area_sqm, use_zone, source_month
    ) VALUES (
      @building_id, @broker, @name, @name_raw, @district, @address_road, @address_raw,
      @station_area, @latitude, @longitude, @floors_above, @floors_below,
      @gross_area_sqm, @gross_area_pyeong, @exclusive_area_sqm, @exclusive_area_pyeong,
      @efficiency_ratio, @completed_year, @ceiling_height_m, @ev_count, @parking_total,
      @features_raw, @main_purpose, @building_coverage_ratio, @floor_area_ratio,
      @height_m, @land_area_sqm, @use_zone, @source_month
    )
  `);
  const insFloor = db.prepare(`
    INSERT INTO floor_availabilities (
      building_id, floor_label, floor_number, is_total_row,
      exclusive_area_sqm, exclusive_area_pyeong, lease_area_sqm, lease_area_pyeong,
      availability_kind, availability_raw
    ) VALUES (
      @building_id, @floor_label, @floor_number, @is_total_row,
      @exclusive_area_sqm, @exclusive_area_pyeong, @lease_area_sqm, @lease_area_pyeong,
      @availability_kind, @availability_raw
    )
  `);
  const insRent = db.prepare(`
    INSERT INTO rent_terms (
      building_id, scope_label, deposit_per_pyeong, rent_per_pyeong, maintenance_per_pyeong
    ) VALUES (
      @building_id, @scope_label, @deposit_per_pyeong, @rent_per_pyeong, @maintenance_per_pyeong
    )
  `);

  const num = (v) => (v === undefined || v === null || v === "" ? null : v);
  const bool = (v) => (v ? 1 : 0);

  const files = readdirSync(OUT_DIR).filter((f) => f.endsWith(".json"));
  let nB = 0, nF = 0, nR = 0, idx = 0;

  // "Others" 등 미분류 덤프 항목 제외(단일 파일에 여러 건물 층이 뒤섞여 있어 MVP 품질 저해).
  const SKIP_NAMES = new Set(["Others", "기타", "미상"]);

  const run = db.transaction(() => {
    for (const file of files) {
      const d = JSON.parse(readFileSync(join(OUT_DIR, file), "utf8"));
      if (SKIP_NAMES.has((d.building_name ?? "").trim())) continue;
      const broker = d.broker ?? "ETC";
      const id = slugify(broker, d.building_name ?? file.replace(/\.json$/, ""), idx++);

      insBuilding.run({
        building_id: id,
        broker,
        name: d.building_name ?? "(이름없음)",
        name_raw: num(d.building_name_raw),
        district: num(d.district),
        address_road: num(d.address_road),
        address_raw: num(d.address_raw),
        station_area: num(d.station_area),
        latitude: num(d.latitude),
        longitude: num(d.longitude),
        floors_above: num(d.floors_above),
        floors_below: num(d.floors_below),
        gross_area_sqm: num(d.gross_area_sqm),
        gross_area_pyeong: num(d.gross_area_pyeong),
        exclusive_area_sqm: num(d.exclusive_area_sqm),
        exclusive_area_pyeong: num(d.exclusive_area_pyeong),
        efficiency_ratio: num(d.efficiency_ratio),
        completed_year: num(d.completed_year),
        ceiling_height_m: num(d.ceiling_height_m),
        ev_count: num(d.ev_count),
        parking_total: num(d.parking_total),
        features_raw: num(d.features_raw),
        main_purpose: num(d.main_purpose),
        building_coverage_ratio: num(d.building_coverage_ratio),
        floor_area_ratio: num(d.floor_area_ratio),
        height_m: num(d.height_m),
        land_area_sqm: num(d.land_area_sqm),
        use_zone: num(d.use_zone),
        source_month: num(d.source_month),
      });
      nB++;

      for (const f of d.floors ?? []) {
        insFloor.run({
          building_id: id,
          floor_label: num(f.floor_label),
          floor_number: num(f.floor_number),
          is_total_row: bool(f.is_total_row),
          exclusive_area_sqm: num(f.exclusive_area_sqm),
          exclusive_area_pyeong: num(f.exclusive_area_pyeong),
          lease_area_sqm: num(f.lease_area_sqm),
          lease_area_pyeong: num(f.lease_area_pyeong),
          availability_kind: num(f.availability_kind),
          availability_raw: num(f.availability_raw),
        });
        nF++;
      }
      for (const r of d.rents ?? []) {
        insRent.run({
          building_id: id,
          scope_label: num(r.scope_label),
          deposit_per_pyeong: num(r.deposit_per_pyeong),
          rent_per_pyeong: num(r.rent_per_pyeong),
          maintenance_per_pyeong: num(r.maintenance_per_pyeong),
        });
        nR++;
      }
    }
  });
  run();

  db.close();
  console.log(`✓ ${DB_PATH}`);
  console.log(`  buildings=${nB}  floor_availabilities=${nF}  rent_terms=${nR}`);
}

main();
