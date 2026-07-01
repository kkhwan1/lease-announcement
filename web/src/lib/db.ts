// 로컬 SQLite 조회 싱글턴 (서버 전용).
// Supabase pause 우회 MVP. web/data/lease.db 는 scripts/build-db.mjs 로 생성.
// ⚠️ 서버(Route Handler)에서만 import. 브라우저 번들에 포함되면 안 된다.
import Database from "better-sqlite3";
import { join } from "node:path";

let _db: Database.Database | null = null;

/** 프로세스당 1회 연결. readonly. */
export function getDb(): Database.Database {
  if (_db) return _db;
  const dbPath = join(process.cwd(), "data", "lease.db");
  _db = new Database(dbPath, { readonly: true, fileMustExist: true });
  return _db;
}
