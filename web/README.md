# 오피스 임대매물 검색 (웹)

서울 주요 권역 오피스 임대매물 공개 플랫폼. Next.js 15 App Router + Supabase + 카카오맵.

## 빠른 시작

```bash
cd web
cp .env.local.example .env.local   # 키 입력
npm install
npm run dev                        # http://localhost:3000
```

## 환경변수 (.env.local)

| 변수 | 설명 |
|------|------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase 프로젝트 URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon 키(공개 읽기 전용) |
| `NEXT_PUBLIC_KAKAO_JS_KEY` | 카카오맵 JavaScript 키 |

카카오 JS 키만 넣으면 지도가 동작합니다. 키가 없으면 지도 자리에 안내 문구가
표시되고 목록은 정상 작동합니다.

> service_role 키 등 비공개 키는 절대 넣지 마세요. 이 앱은 공개 읽기 전용입니다.
