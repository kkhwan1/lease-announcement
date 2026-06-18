# 임대매물 공개 플랫폼 — 웹 설계 문서

> 작성: 2026-06-18 · 대상: 직방/다방식 공개 상업용 임대매물 플랫폼
> 백엔드(DB) 완성 상태에서 **공개 웹 프론트엔드**를 신규 구축한다.

---

## 1. Context — 왜 만드는가

사용자(1인 부동산·금융 테크 기업가)는 여러 중개사(C&W·오스카·에스원·JLL)의 월별 임대 안내문 PDF를 파싱·정규화해 **건물 마스터 DB**(260개 건물·1,116층 공실·임대료)를 구축했다. 이제 이 데이터를 **직방/다방처럼 누구나 로그인 없이 볼 수 있는 공개 매물 플랫폼**으로 서비스한다.

추가 핵심 요구:
- **월별 갱신·추이 추적**: 매월 새 안내문을 적재하면서 임대료 등의 **시계열 추이**를 본다. DB의 `listing_snapshots`(건물×중개사×월) 구조가 이를 이미 지원한다.
- **지도 키만 넣으면 작동**: 카카오맵 키 한 줄(`.env.local`)만 설정하면 지도가 동작하는 구조.

### 결정 요약 (브레인스토밍 확정)
| 항목 | 결정 |
|------|------|
| MVP 목적 | 공개 매물 조회·검색 플랫폼 (직방/다방식) |
| 접근 | **로그인 없음** — 누구나 공개 열람 |
| 메인 UX | **지도+리스트 분할** (좌 리스트 / 우 지도) |
| 지도 | **카카오맵** (Kakao Maps JS SDK) |
| 상세 공개범위 | 건물기본+사진 · 층별공실 · **임대료/관리비** · 건축물대장 · **특장점** 전부 공개 |
| 임대료 노출 | 카드 + 테이블 양쪽 |
| 스택 | **Next.js 15 (App Router) + Supabase + Vercel** |
| 추이 | 월별 스냅샷 누적 → 상세에 임대료 시계열 차트 |
| UI 테마 | **라이트(흰 배경) 단일 테마**, 다크모드 없음 |
| 아이콘 | **이모지 전면 금지**. 필요한 아이콘은 SVG 라이브러리(lucide-react)만 사용 |

---

## 2. 아키텍처

```
[브라우저 - 누구나 로그인 없이]
   │  Next.js 15 App Router (SSR/ISR)
   │  카카오맵 JS SDK (.env.local 키)
   ▼
[Vercel]
   ├─ 공개 조회 → Supabase anon 키 (SELECT-only RLS)   ← 브라우저 안전
   ├─ 이미지 → Storage public 버킷
   └─ 적재/보강(월별) → service_role (서버/CLI 전용, 브라우저 노출 금지)
```

### 보안 원칙 (공개 플랫폼의 핵심)
- 공개되는 데이터: **건물·공실·임대료·이미지·중개사명**뿐.
- 내부 테이블(`raw_extractions`·`source_documents`·`review_queue`·`merge_candidates`·`building_field_values`)은 **anon 정책 미부여 = 접근 차단**.
- `service_role` 키는 **절대 `NEXT_PUBLIC_*`에 넣지 않음**. 브라우저는 anon 키만.
- anon은 **SELECT만**, INSERT/UPDATE/DELETE 차단.

---

## 3. 데이터 모델 — 월별 추이 (신규 핵심)

### 기존 스키마가 이미 지원하는 것 (검증 완료)
`listing_snapshots` (0007):
- `snapshot_month date` (YYYY-MM-01) + UNIQUE `(building_id, broker_id, snapshot_month)` → **월별 이력 누적**.
- `is_latest boolean` + demote 트리거 → 조합당 최신 1건만 true, **과거 스냅샷은 `is_latest=false`로 보존**.

### 추이 추적을 위해 보장해야 할 것
매월 재적재 시 과거 임대료를 보려면 **과거 스냅샷의 `rent_terms`/`floor_availabilities`가 삭제되지 않고 보존**되어야 한다.
- `rent_terms`/`floor_availabilities`는 `listing_snapshot_id` FK로 특정 월 스냅샷에 묶인다.
- 월별 적재 흐름: 새 달 = 새 `snapshot_month` 행 INSERT(새 id) → 그 id로 rent_terms 적재 → 이전 달 행은 `is_latest=false`로 강등되지만 **데이터는 그대로 남음**.
- **적재 코드 점검 필요**: 현재 `supa_store.py`가 같은 (building,broker)에 대해 월이 바뀔 때 과거 rent_terms를 지우지 않는지(덮어쓰기 아님) 확인. 덮어쓰면 추이 불가 → 구현 Phase 0에서 검증·수정.

### 신규 추이 뷰 `v_rent_trend`
```
building_id, broker, snapshot_month, scope_label,
rent_per_pyeong, maintenance_per_pyeong, deposit_per_pyeong
  ← listing_snapshots(전체, is_latest 무관) + rent_terms
  ← snapshot_month 오름차순
```
상세 페이지에서 building_id로 필터 → 월별 평당 임대료 라인차트.

---

## 4. 화면 전용 뷰 (공개 조회 최적화)

| 뷰 | 용도 | 핵심 컬럼 |
|----|------|-----------|
| `v_buildings_summary` | 홈/검색 카드 리스트 | building_id, name, district, address_road, 공실수, **최저 평당임대료**, 대표 썸네일, lat, lng |
| `v_buildings_map` | 지도 핀(경량) | building_id, name, lat, lng, district, 공실수 (좌표 있는 건물만) |
| `v_building_detail` | 상세 한 방 조회 | buildings 전체 + 건축물대장 8필드 + features_raw + 출처 요약 |
| `v_current_vacancies` | 상세 층별공실 (기존 재사용) | building_id 필터로 사용 |
| `v_rent_trend` | 상세 임대료 추이 (신규) | 위 §3 |

성능 한계 시 `v_buildings_summary`를 **materialized view** 전환 + 월 적재 후 `refresh`.

---

## 4-1. UI 디자인 시스템 (사용자 지정)

- **라이트 테마 단일**: 흰 배경(`#ffffff`), 본문 텍스트 짙은 회색(`#1a1a1a` 계열), 다크모드 미지원.
- **깔끔/미니멀**: 직방식 정보 밀도. 카드는 흰 배경 + 옅은 보더(`#e5e7eb`) + 미세 그림자. 강조색은 절제된 1색(예: 블루 계열) 포인트.
- **이모지 전면 금지**: 본문/버튼/헤더 어디에도 이모지 사용 안 함. 아이콘이 필요하면 `lucide-react` SVG 컴포넌트만 사용.
- Tailwind CSS 기반, 기본 폰트는 시스템 한글 폰트 스택(Pretendard 우선).

---

## 5. 페이지 구성 (사이트맵)

```
/                  홈 = 지도+리스트 분할 (메인 탐색)
/building/[id]     건물 상세 (핵심 자산)
/search            검색 결과 (필터 리스트, 홈과 컴포넌트 공유)
/about             서비스 소개 + 면책(중개 아님, 정보 제공)
공통: 헤더(검색바·권역탭) / 푸터(데이터 출처·갱신일·건수)
```

### 화면 1. 홈 `/` — 지도+리스트 분할 (메인)
- **좌: 건물 카드 리스트** — 건물명 · 권역+주소 · 공실 개수 · **최저 평당 임대료** · 외관 썸네일. 정렬(임대료·면적·준공년·공실수). 무한스크롤.
- **우: 카카오 지도** — 핀 + 클러스터, hover 미니카드, **핀↔카드 양방향 연동**, "이 지역 재검색".
- **상단 필터** — 권역(GBD/CBD/YBD/BBD/ETC) · 전용/임대 면적범위 · 평당 임대료범위 · 즉시입주 · 준공년도. → `v_current_vacancies` 컬럼과 1:1.
- 데이터: `v_buildings_summary` + `v_buildings_map`.

### 화면 2. 건물 상세 `/building/[id]` (핵심)
순서대로:
1. **사진 갤러리** — building_images (외관→로비→평면도).
2. **건물 개요** — 주소·권역·준공·규모(층/연면적)·전용률·주차·천정고·EV.
3. **위치 미니맵** — 카카오 단일 핀 + 근접역.
4. **건축물대장** — 건폐율·용적률·주용도·용도지역 등 8필드(있을 때만).
5. **층별 공실 테이블** 1순위 — 층 · 전용(평) · 임대(평) · 입주 · **평당 임대료/관리비**. 평↔㎡ 토글. Total행 제외.
6. **특장점 섹션** — `buildings.features_raw` 표시.
7. **임대료 추이 차트** — `v_rent_trend` 월별 라인차트.
8. **데이터 출처** — "C&W·오스카 안내문(2026.06) + 건축물대장" 투명 표기.

### 화면 3~5
- `/search` — 홈 필터를 URL 쿼리로 받는 전체화면 리스트(지도 접기). 카드 컴포넌트 공유.
- `/about` — 데이터 출처·갱신주기·면책.
- 공통 푸터 — 마지막 갱신일·데이터 건수·출처 중개사.

---

## 6. 프로젝트 구조 (신규 `web/`)

```
Lease Announcemen/
├── app/ ...                 # 기존 Python 파이프라인 (유지)
├── cli.py                   # + geocode 명령 추가
├── supabase/migrations/
│   ├── 0020_public_rls.sql      # anon SELECT-only 공개 정책
│   ├── 0021_web_views.sql       # v_buildings_summary/map/detail
│   └── 0022_rent_trend_view.sql # v_rent_trend
└── web/                     # 신규 Next.js 15
    ├── app/
    │   ├── page.tsx                 # 홈 (지도+리스트)
    │   ├── building/[id]/page.tsx   # 상세
    │   ├── search/page.tsx
    │   └── about/page.tsx
    ├── components/
    │   ├── KakaoMap.tsx             # 키 없으면 안내 placeholder, 있으면 SDK 동적 로드
    │   ├── BuildingCard.tsx         # 임대료 노출
    │   ├── FilterBar.tsx
    │   ├── FloorTable.tsx           # 평↔㎡ 토글
    │   ├── PhotoGallery.tsx
    │   ├── FeatureSection.tsx       # 특장점
    │   └── RentTrendChart.tsx       # 월별 추이
    ├── lib/supabase.ts              # anon 클라이언트
    ├── lib/queries.ts               # 뷰 조회 함수
    ├── .env.local.example           # NEXT_PUBLIC_* + NEXT_PUBLIC_KAKAO_MAP_KEY
    └── README.md                    # "카카오 키 한 줄 넣고 npm run dev"
```

### 카카오 키 "한 줄만 넣으면 작동" 구조
- `KakaoMap.tsx`는 `process.env.NEXT_PUBLIC_KAKAO_MAP_KEY`를 읽어:
  - **키 있음** → `//dapi.kakao.com/v2/maps/sdk.js?appkey=KEY&autoload=false` 스크립트 동적 주입 → 지도 렌더.
  - **키 없음** → "카카오맵 키를 .env.local에 입력하세요" placeholder 표시(앱은 죽지 않음, 리스트는 정상 작동).
- 사용자는 [developers.kakao.com](https://developers.kakao.com) → 앱 생성 → JavaScript 키 → `.env.local`에 `NEXT_PUBLIC_KAKAO_MAP_KEY=...` 한 줄.
- Vercel 배포 시 동일 키를 환경변수로 등록.

---

## 7. 사전 데이터 작업 (Phase 0)

| # | 작업 | 이유 | 방법 |
|---|------|------|------|
| 1 | **좌표 보강** | 지도 핀 필수. lat/lng 대부분 NULL | `cli.py geocode` 신규: NULL 행 → kk_real_estate `geocoder.resolve(address_road)` → UPDATE. C&W 공백없는 주소는 시·구 공백 정규화 후 호출 |
| 2 | **이미지 Storage 적재** | 사진 표시. 현재 file_path NULL | `cli.py push --with-images` → **public 버킷** 업로드 |
| 3 | **RLS 공개 정책** | 익명 읽기 | 0020: 공개 테이블에 anon SELECT, 내부 테이블 차단 |
| 4 | **추이 보존 검증** | 월별 추이 | supa_store가 과거 rent_terms 덮어쓰지 않는지 확인·수정 |

---

## 8. 구현 순서 (Phase)

| Phase | 내용 | 게이트 |
|-------|------|--------|
| **0. 데이터 준비** | 좌표 보강 + 이미지 적재 + RLS(0020) + 뷰(0021/0022) + 추이보존 검증 | 260건물 좌표·이미지·anon읽기·과거스냅샷 보존 확인 |
| **1. 셋업** | `web/` Next.js 15 + anon 클라이언트 + 카카오 SDK 래퍼 + 레이아웃 | `npm run dev` 헤더·푸터·키없음 placeholder |
| **2. 홈** | KakaoMap + BuildingCard + FilterBar + 양방향 연동 | 260건물 지도·리스트·필터·임대료 노출 |
| **3. 상세** | 갤러리·개요·건축물대장·층별공실·특장점·**추이차트**·출처 | 케이스퀘어 실측 대조 + 추이 표시 |
| **4. 검색/소개 + 배포** | /search·/about·반응형·SEO·Vercel 배포 | 비로그인 시크릿창에서 공개 URL 동작 |

---

## 9. 검증 (end-to-end)

- **Phase 0**: `cli.py geocode` 후 `count(latitude not null) ≈ 260` / anon 키 SELECT 성공 + INSERT 거부 / 같은 건물 2개월 적재 후 `listing_snapshots` 2행·rent_terms 양쪽 보존.
- **Phase 2**: GBD 필터 → 강남 핀만, 카드↔핀 연동, 임대료 카드 노출.
- **Phase 3**: 케이스퀘어강남2 → B3/20F·연면적 21,930·18층 전용98.15/임대128.43·건폐율59.35% 대조 + 추이차트 월별 점 표시.
- **Phase 4**: Vercel URL 시크릿창(비로그인) 정상 = 공개 플랫폼 검증.

---

## 10. 미해결/구현 중 확정

- 카카오 지오코딩 vs kk_real_estate geocoder 중 좌표 보강 1차 소스 (geocoder 우선, 실패분 카카오 폴백 검토).
- `v_buildings_summary` 일반뷰 vs materialized (성능 보고 결정).
- 추이 차트 라이브러리 (recharts 등 경량 우선).
- 면책 문구 법무 표현 (정보 제공 목적, 중개행위 아님).
