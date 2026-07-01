// MVP: Supabase 프로젝트가 pause되어 로컬 SQLite로 전환됨.
// Supabase 클라이언트 생성부는 제거(env 없어도 빌드 통과). 이미지 URL 헬퍼만 잔존.
// 로컬 데이터에는 이미지가 없어 실제로 호출되지 않지만, 컴포넌트 import 호환을 위해 유지.

/** 이미지 storage_path → 공개 URL. MVP에선 이미지 데이터가 없어 사실상 미사용.
 *  Supabase Storage base가 없으므로 경로를 그대로 인코딩해 반환(플레이스홀더 폴백은 컴포넌트가 처리). */
export function buildingImageUrl(storagePath: string): string {
  return storagePath
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}
