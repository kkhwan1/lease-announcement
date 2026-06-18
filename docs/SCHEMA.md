# 임대 매물 데이터베이스 — 스키마 설계 문서

> 최종 갱신: 2026-06-18 · Supabase 프로젝트 `tdmfbxwszxzhyywntbks` (ap-northeast-1)
> 현재 적재: 건물 260개 · 층별공실 1,116행 · 출처 병합(PDF+건축물대장) 작동

---

## 1. 설계 철학 (왜 이렇게 짰는가)

이 DB의 핵심 난제는 **"같은 건물이 여러 중개사 안내문에 제각각 표기로 중복 등장"**한다는 것이다.
이를 해결하기 위한 4가지 축:

| 축 | 구현 | 목적 |
|----|------|------|
| **건물 마스터 단일화** | `buildings` + `match_key`(주소 우선) | 같은 건물은 1행. 중개사 표기 차이를 주소로 흡수 |
| **마스터 ↔ 스냅샷 분리** | `buildings`(불변 물리스펙) vs `listing_snapshots`(중개사×월 거래현황) | 건물 스펙과 매월 바뀌는 공실/임대료를 분리 |
| **필드 단위 출처 병합** | `building_field_values` (필드×출처) | "PDF로 채우고 부족분은 다른 PDF/API로" — 출처별 추적 |
| **raw 원본 보존** | `raw_extractions` (immutable) | 파서 개선 시 PDF 재파싱 없이 재처리 |

**Entity Resolution 키 전략 (사용자 결정):** 주소가 1차 키. 건물명은 표기가 불안정하므로 보조 키.
`match_key = "addr:" + 도로명+건물번호` (예: `addr:강남대로374`), 주소 없으면 `name:` 네임스페이스.

---

## 2. 현재 테이블 구조 (12개 + 뷰 1개)

### 데이터 흐름
```
PDF → source_documents (1 PDF=1행, sha256 멱등)
    → raw_extractions     (가공 전 원본, immutable)
    → buildings           (마스터, match_key로 중복 해소)
        ├ building_field_values  (필드×출처 병합: pdf_parse / building_register)
        ├ building_aliases       (중개사별 호칭 차이)
        └ listing_snapshots      (건물×중개사×월, is_latest 1건)
              ├ floor_availabilities (층별 공실 1:N)
              └ rent_terms           (임대조건, 평당+㎡ generated)
    → building_images     (Storage 경로 + 분류)
    → merge_candidates / review_queue  (수동 병합·검수 큐)
```

### 계층별 역할
- **마스터**: `brokers`(중개사 4), `buildings`(건물, +건축물대장 8필드)
- **원본보존**: `source_documents`, `raw_extractions`, `building_field_values`
- **거래현황**: `listing_snapshots`, `floor_availabilities`, `rent_terms`
- **보조**: `building_aliases`, `building_images`, `merge_candidates`, `review_queue`
- **뷰**: `v_current_vacancies` (최신 공실 검색용 평탄화)

### buildings 주요 컬럼
- 식별: `match_key`(uniq), `identity_key`(generated 보조), `name`, `name_raw`
- 위치: `address_road`, `address_raw`, `district`(GBD/CBD/YBD/BBD/ETC enum), `station_area`, `latitude`/`longitude`
- 물리스펙(PDF): `floors_above/below`, `gross_area_sqm/pyeong`, `ev_count`, `completed_year`, `ceiling_height_m`, `efficiency_ratio`, `parking_total`, `features_raw`
- 건축물대장(API 보강): `main_purpose`, `building_coverage_ratio`, `floor_area_ratio`, `height_m`, `land_area_sqm`, `use_zone`

---

## 3. 마이그레이션 현황 ⚠️ (정리 필요)

| 파일 | 상태 |
|------|------|
| 0001~0012, 0019 | ✅ 파일 있음 |
| **0013~0018** | ⚠️ **파일 없음, DB엔 적용됨** (MCP 직접 적용) |

**누락된 0013~0018 실제 내용** (이 문서에 기록):
- **0013**: RLS 정책 (모든 테이블, authenticated 전체 허용) + Storage 버킷 정책
- **0014/0015**: 멱등 UNIQUE 제약 (raw_extractions, building_field_values, listing_snapshots, building_aliases, merge_candidates)
- **0016**: `immutable_unaccent` search_path 수정 (public 추가)
- **0017**: numeric precision 12→18 확대 (금액·면적) + 뷰 재생성
- **0018**: `buildings.match_key` 컬럼 + 부분 UNIQUE 인덱스, identity_key UNIQUE 제거

> **조치 필요**: 위 내용을 `supabase/migrations/0013~0018_*.sql` 파일로 역생성해 버전관리에 등록.
> 안 하면 신규 환경에서 DB 재현 불가 / 협업·CI 파손.

---

## 4. 발견된 데이터 정확도 오류 (수정 진행 중)

| 오류 | 원인 | 상태 |
|------|------|------|
| 임대료 평당 1000만↑ 67건 | "총월임대료"(총액)를 평당 컬럼에 넣음 | 🔧 어댑터에 총액→평당 환산 추가 |
| 보증금 평당 1억↑ 33건 | "합계/통임대" 행(총액)을 평당으로 | 🔧 동일 |
| "빌" 노이즈 39건 | S1 셀 병합 아티팩트 | ✅ 금액 파서 수정 |
| 준공년도 "2" | 천정고("2.6m")가 준공 셀에 혼입 | 🔧 4자리 연도 우선 파싱 |
| 건물명에 주소 잔류 | C&W 주소 분리 실패(공백없는 주소) | 🔧 정규식 보강 |
| 병합 후보 10건 | 이름 유사+주소 다른 별개 건물 | ✅ 전수 검토 → 모두 rejected(정상) |

**데이터 충실도(양호):** PDF 필드 98~100%, 건축물대장 API 27~32%(주소 조회 성공분).

---

## 5. 확장성 로드맵 — 영업 도구 + 웹 화면 대비

현재는 "PDF→DB 적재"까지 완성. 향후 **영업 도구 + 웹**을 위해 필요한 추가 설계:

### 우선순위별 추가 테이블

| 순위 | 영역 | 추가 테이블 | 목적 |
|------|------|-------------|------|
| **1** | 사용자/권한 | `users`(role: admin/agent/viewer), RLS 세분화 | 멀티유저 협업, 내 데이터 격리 |
| **1** | CRM/영업 | `clients`, `client_requirements`, `proposals`, `proposal_notes` | 고객 요구사항 저장 → 매물 자동 매칭 → 제안 이력 |
| **2** | 매물 상태 | `floor_availabilities.listing_status`(available/negotiating/leased/withdrawn) + 이력 | "계약중/성약" 추적, 검색 제외 |
| **2** | 지도 | `buildings.location_geom`(PostGIS) + GIST 인덱스 | 네이버지도식 핀·반경검색 (위경도는 이미 보강됨) |
| **3** | 영업 UX | `building_bookmarks`, `building_notes`, `tags`, `building_tags` | 즐겨찾기·메모·태그 분류 |
| **3** | 감사 | `audit_log` + 트리거 | 변경 이력 추적 |
| **4** | 첨부 | `building_attachments` | PDF 원본·계약서 등 |

### 웹 화면용 추가 뷰 (제안)
- `v_buildings_summary`: 건물별 공실수·최저임대료 집계 (리스트/카드 뷰)
- `v_buildings_map`: 좌표 + 최소정보 (지도 핀)
- `v_listing_status_summary`: 거래현황 대시보드
- `v_client_matching_results`: 고객조건 vs 공실 매칭

### 데이터 모델 개선 후보
- **`rent_terms.scope_label` → enum화**: 기준층/통층/특정층/총액 구분 명확화 (현재 '합계/총액' 모호)
- **`building_field_values` EAV**: value가 text라 타입별 조회 어려움. 1000건 넘으면 타입별 컬럼 분리 검토.

---

## 6. 다음 단계 권장 순서

1. **(즉시) 데이터 오류 수정 완료 + 전체 재적재** — 임대료/준공년도/주소 정확도
2. **(즉시) 마이그레이션 0013~0018 파일 역생성** — 재현성 확보
3. **(웹 착수 전) 사용자/RLS + CRM 테이블 설계** — 영업 도구 기반
4. **(웹) Next.js + 지도(PostGIS) + 검색 뷰** — 화면 구축
