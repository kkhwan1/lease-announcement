// Supabase 공개 클라이언트 (anon 키, SELECT-only).
// 브라우저/서버 양쪽에서 공개 데이터 조회에만 사용. service_role 키는 절대 포함하지 않는다.
import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY 가 .env.local에 필요합니다.",
  );
}

export const supabase = createClient(url, anonKey, {
  auth: { persistSession: false },
});
