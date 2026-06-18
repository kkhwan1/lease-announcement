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

// building-images 버킷은 public read. storage_path를 공개 이미지 URL로 변환.
const IMAGE_BUCKET = "building-images";
const PUBLIC_BASE = `${url}/storage/v1/object/public/${IMAGE_BUCKET}`;

/** building_images.storage_path → 브라우저에서 바로 <img src>로 쓸 공개 URL. */
export function buildingImageUrl(storagePath: string): string {
  // 경로 세그먼트별 인코딩 (한글 broker 코드는 없지만 안전하게 공백/특수문자 대비)
  const encoded = storagePath
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
  return `${PUBLIC_BASE}/${encoded}`;
}
