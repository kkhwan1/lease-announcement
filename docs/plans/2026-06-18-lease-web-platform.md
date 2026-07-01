# 임대매물 공개 플랫폼 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 260개 건물 임대매물 DB를 직방/다방식 공개 웹 플랫폼(지도+리스트)으로 서비스한다.

**Architecture:** Next.js 15 App Router(SSR/ISR)가 Supabase anon 키(SELECT-only RLS)로 공개 데이터를 읽어 렌더. 지도는 카카오맵 JS SDK. 좌표 보강은 Python CLI(카카오 REST 1차, V-World 폴백). 이미지/추이/CRM 관리는 후속.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS, lucide-react(아이콘), @supabase/supabase-js, recharts(추이), 카카오맵 JS SDK. 백엔드 보강은 Python 3.12(.venv).

**UI 원칙(사용자 지정):** 라이트 단일 테마(흰 배경), 이모지 전면 금지(아이콘은 lucide SVG만), 깔끔/미니멀.

**작업 방식:** 에이전트 팀 협업. 각 Phase 완료 시 codex-rescue로 리뷰 후 다음 Phase. 모르는 것/바뀌는 것은 사용자에게 즉시 질문.

---

## 현재 상태 (2026-06-18 실측)

- buildings 260 / **좌표 보유 84** → **176개 보강 필요**
- building_images 1,418행 적재됨 (메타 + storage_path). 이미지는 DB에 있는 것으로 사용.
- listing_snapshots months=1 (2026.06) → 추이 차트는 자리만 + 안내문구.
- rent_terms 649. RLS는 authenticated 전용 → anon SELECT 정책 추가 필요.
- 키 준비됨: KAKAO_REST_API_KEY, KAKAO_JS_KEY/NEXT_PUBLIC_KAKAO_JS_KEY, VWORLD_KEY, SUPABASE_*.

---

## 진행 현황 (2026-06-18)

- Phase 0 (데이터/DB): 완료. 좌표 245/260, 공개 RLS, 화면 뷰 4종, 'Others' 숨김. Codex 리뷰 반영.
- Phase 1 (웹 셋업): 완료. Next.js 16 + 라이트테마 + Supabase anon + 뷰쿼리. Codex 리뷰 반영.
- Phase 2 (홈 지도+리스트): 완료. 카드 259건·필터·지도(도메인 등록 시 표시). Codex 리뷰 반영.
- Phase 3 (건물 상세): 완료. 전 섹션 + 실측 검증. Codex 리뷰 반영.
- Phase 4 (마감): 검색=홈 통합, 반응형·SEO 완료. 배포는 보류(사용자 요청).
- 미완: 카카오 지도 도메인 등록(사용자), 이미지 Storage 업로드(후속), Vercel 배포(후속).

## 전체 Phase 골격

| Phase | 목표 | 산출물 | 게이트 |
|-------|------|--------|--------|
| **0. 데이터/DB 준비** | 좌표 보강 + 공개 RLS + 화면 뷰 | `cli.py geocode`, 0020/0021/0022 마이그레이션 | 좌표≈260, anon SELECT OK/INSERT 거부, 뷰 조회 OK |
| **1. 웹 셋업** | Next.js 골격 + 공통 레이아웃 | `web/` 프로젝트, supabase 클라이언트, 헤더/푸터 | `npm run dev` 라이트 레이아웃, 키없음 placeholder |
| **2. 홈(지도+리스트)** | 메인 탐색 화면 | KakaoMap, BuildingCard, FilterBar, 양방향 연동 | 260건물 지도·리스트·필터·임대료 노출 |
| **3. 건물 상세** | 핵심 자산 화면 | 갤러리·개요·대장·층별공실·특장점·추이자리·출처 | 케이스퀘어 실측 대조 |
| **4. 검색/소개+배포** | 마감 | /search, /about, 반응형, SEO, Vercel | 비로그인 시크릿창 공개 URL 동작 |

> 이 문서는 **Phase 0 상세**까지 작성. Phase 1~4는 각 착수 시점에 상세화한다(사용자 결정: Phase별 순차).

---

# Phase 0: 데이터/DB 준비

**목표:** 웹이 읽을 데이터(좌표)와 공개 접근(RLS), 조회 최적화(뷰)를 준비한다.

**파일 구조:**
- Create: `app/geocode.py` — 주소→좌표 보강 로직(카카오 REST 1차, V-World 폴백)
- Modify: `cli.py` — `geocode` 서브커맨드 추가
- Create: `app/normalize_address_spacing.py` 또는 `app/normalize.py`에 함수 추가 — C&W 공백없는 주소 정규화
- Create: `supabase/migrations/0020_public_read_rls.sql` — anon SELECT 정책
- Create: `supabase/migrations/0021_web_views.sql` — v_buildings_summary / v_buildings_map / v_building_detail
- Create: `supabase/migrations/0022_rent_trend_view.sql` — v_rent_trend
- Create: `tests/test_geocode.py` — 좌표 보강 단위 테스트

---

## Task 0.1: C&W 주소 공백 정규화 함수

C&W 주소는 "서울특별시종로구율곡로 2길19"처럼 시·구가 붙어 지오코더가 실패한다. 시·도/구 사이 공백을 삽입한다.

**Files:**
- Modify: `app/normalize.py` (함수 추가)
- Test: `tests/test_address_spacing.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_address_spacing.py
from app.normalize import insert_address_spacing


def test_cnw_spaceless_address():
    # 시 + 구가 붙은 C&W 형식
    assert insert_address_spacing("서울특별시종로구율곡로 2길19") == "서울특별시 종로구 율곡로 2길19"


def test_already_spaced_passthrough():
    # 오스카 형식(이미 공백) — 변형 없음
    assert insert_address_spacing("서울특별시 강남구 강남대로 374") == "서울특별시 강남구 강남대로 374"


def test_seoul_seocho_spaceless():
    assert insert_address_spacing("서울서초구서초대로 396") == "서울 서초구 서초대로 396"


def test_none_safe():
    assert insert_address_spacing(None) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_address_spacing.py -v`
Expected: FAIL — `ImportError: cannot import name 'insert_address_spacing'`

- [ ] **Step 3: 함수 구현**

```python
# app/normalize.py 에 추가
import re

# 시/도 명칭 (긴 것 우선 매칭)
_SIDO_NAMES = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도", "서울", "부산", "대구",
    "인천", "광주", "대전", "울산", "세종",
]
_SIDO_PATTERN = "|".join(_SIDO_NAMES)
# "<시도><구/군/시>" 가 공백 없이 붙은 경우를 분리
_SPACELESS_RE = re.compile(
    rf"^({_SIDO_PATTERN})\s*([가-힣]{{1,4}}(?:구|군|시))\s*"
)


def insert_address_spacing(address: str | None) -> str | None:
    """C&W식 공백없는 주소에 시·도/구 사이 공백을 삽입.

    '서울특별시종로구율곡로 2길19' → '서울특별시 종로구 율곡로 2길19'
    이미 공백이 정상이면 그대로 반환.
    """
    if not address:
        return address
    s = address.strip()
    m = _SPACELESS_RE.match(s)
    if not m:
        return s
    sido, gu = m.group(1), m.group(2)
    rest = s[m.end():].strip()
    return f"{sido} {gu} {rest}".strip()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_address_spacing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/normalize.py tests/test_address_spacing.py
git commit -m "feat: C&W 공백없는 주소 정규화 insert_address_spacing 추가"
```

---

## Task 0.2: 좌표 보강 로직 (geocode.py)

주소→위경도. 카카오 REST(주소검색) 1차, 실패 시 V-World geocoder 폴백.

**Files:**
- Create: `app/geocode.py`
- Test: `tests/test_geocode.py`

- [ ] **Step 1: 실패 테스트 작성 (네트워크 모킹)**

```python
# tests/test_geocode.py
from unittest.mock import patch, MagicMock
from app.geocode import geocode_kakao, GeoPoint


def test_geocode_kakao_success():
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "documents": [{"x": "127.0276", "y": "37.4979"}]
    }
    with patch("app.geocode.httpx.get", return_value=fake):
        pt = geocode_kakao("서울특별시 강남구 강남대로 374", api_key="dummy")
    assert pt == GeoPoint(lat=37.4979, lng=127.0276)


def test_geocode_kakao_no_result():
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {"documents": []}
    with patch("app.geocode.httpx.get", return_value=fake):
        pt = geocode_kakao("없는주소", api_key="dummy")
    assert pt is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_geocode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.geocode'`

- [ ] **Step 3: geocode.py 구현**

```python
# app/geocode.py
"""주소 → 위경도 보강.

1차: 카카오 로컬 주소검색 REST API (KAKAO_REST_API_KEY)
폴백: kk_real_estate V-World geocoder (VWORLD_KEY)
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

import httpx

from app.normalize import insert_address_spacing

logger = logging.getLogger(__name__)

_KAKAO_URL = "https://dapi.kakao.com/v2/local/search/address.json"


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float


def geocode_kakao(address: str, api_key: str, timeout: float = 5.0) -> Optional[GeoPoint]:
    """카카오 주소검색으로 좌표 조회. 실패 시 None."""
    try:
        resp = httpx.get(
            _KAKAO_URL,
            params={"query": address},
            headers={"Authorization": f"KakaoAK {api_key}"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("카카오 지오코딩 HTTP %s: %s", resp.status_code, address)
            return None
        docs = resp.json().get("documents", [])
        if not docs:
            return None
        d = docs[0]
        return GeoPoint(lat=float(d["y"]), lng=float(d["x"]))
    except Exception as exc:
        logger.warning("카카오 지오코딩 예외(%s): %s", address, exc)
        return None


def geocode_vworld(address: str) -> Optional[GeoPoint]:
    """kk_real_estate V-World geocoder 폴백. 실패 시 None."""
    try:
        kk_src = "/home/kkhwan/projects/kk_real_estate/src"
        if kk_src not in sys.path:
            sys.path.insert(0, kk_src)
        import geocoder as kk_geocoder  # type: ignore

        rec = kk_geocoder.resolve(address)
        if rec and rec.lat and rec.lon:
            return GeoPoint(lat=float(rec.lat), lng=float(rec.lon))
        return None
    except Exception as exc:
        logger.warning("V-World 지오코딩 예외(%s): %s", address, exc)
        return None


def geocode_address(address: Optional[str], kakao_key: Optional[str]) -> Optional[GeoPoint]:
    """주소 정규화 후 카카오 1차 → V-World 폴백."""
    if not address:
        return None
    norm = insert_address_spacing(address) or address
    if kakao_key:
        pt = geocode_kakao(norm, kakao_key)
        if pt:
            return pt
    return geocode_vworld(norm)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_geocode.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/geocode.py tests/test_geocode.py
git commit -m "feat: 좌표 보강 geocode.py (카카오 1차 + V-World 폴백)"
```

---

## Task 0.3: cli.py geocode 서브커맨드

buildings에서 좌표 NULL 행을 조회해 보강하고 UPDATE.

**Files:**
- Modify: `cli.py` (cmd_geocode 함수 + 서브파서)

- [ ] **Step 1: cmd_geocode 함수 추가**

`cli.py`의 `cmd_push` 함수 정의 뒤에 추가:

```python
def cmd_geocode(limit: int | None = None, dry_run: bool = False) -> int:
    """buildings.latitude/longitude가 NULL인 행을 주소 기반으로 보강."""
    import os
    from app.geocode import geocode_address
    from app.supa_store import get_client

    client = get_client()
    kakao_key = os.environ.get("KAKAO_REST_API_KEY")

    q = (
        client.table("buildings")
        .select("id, name, address_road, address_raw, latitude")
        .is_("latitude", "null")
    )
    if limit:
        q = q.limit(limit)
    rows = q.execute().data or []
    print(f"좌표 NULL 건물: {len(rows)}건")

    ok = fail = 0
    for r in rows:
        addr = r.get("address_road") or r.get("address_raw")
        pt = geocode_address(addr, kakao_key)
        if pt:
            ok += 1
            print(f"  OK  {r['name']}: ({pt.lat}, {pt.lng}) <- {addr}")
            if not dry_run:
                client.table("buildings").update(
                    {"latitude": pt.lat, "longitude": pt.lng}
                ).eq("id", r["id"]).execute()
        else:
            fail += 1
            print(f"  --  {r['name']}: 보강 실패 <- {addr}")
    print(f"\n완료: 성공 {ok} / 실패 {fail}" + (" (dry-run)" if dry_run else ""))
    return 0
```

- [ ] **Step 2: 서브파서 등록**

`cli.py`의 `sub.add_parser("push", ...)` 블록 뒤에 추가:

```python
    p_geo = sub.add_parser("geocode", help="buildings 좌표 보강 (주소→위경도)")
    p_geo.add_argument("--limit", type=int, default=None, help="처리 건수 제한")
    p_geo.add_argument("--dry-run", action="store_true", help="DB 미반영, 결과만 출력")
```

그리고 디스패치 분기(`elif args.cmd == "push":` 부근)에 추가:

```python
    elif args.cmd == "geocode":
        return cmd_geocode(limit=args.limit, dry_run=args.dry_run)
```

- [ ] **Step 3: dry-run 5건 검증**

Run: `.venv/bin/python cli.py geocode --limit 5 --dry-run`
Expected: 5건 중 대부분 `OK ... (위도, 경도)` 출력, DB 미반영.

- [ ] **Step 4: 전체 보강 실행**

Run: `.venv/bin/python cli.py geocode`
Expected: 176건 처리, 성공률 80%+ (실패분은 주소 품질 문제 — 로그로 확인).

- [ ] **Step 5: DB 검증 + 커밋**

```bash
git add cli.py
git commit -m "feat: cli.py geocode 서브커맨드 (좌표 보강)"
```

MCP로 검증: `select count(*) filter (where latitude is not null) as with_coords, count(*) as total from buildings;` → with_coords가 84에서 크게 증가(목표 230+).

---

## Task 0.4: 공개 읽기 RLS (마이그레이션 0020)

공개 테이블에 anon SELECT 부여. 내부 테이블은 미부여(차단 유지). 쓰기는 anon 차단.

**Files:**
- Create: `supabase/migrations/0020_public_read_rls.sql`

- [ ] **Step 1: 마이그레이션 SQL 작성**

```sql
-- 0020_public_read_rls.sql
-- 공개 플랫폼: anon(비로그인) 역할에 공개 테이블 SELECT 허용.
-- 내부 테이블(raw_extractions/source_documents/review_queue/merge_candidates/
-- building_field_values)은 정책 미부여 = anon 접근 차단 유지.
-- anon은 SELECT만 — INSERT/UPDATE/DELETE 정책 없음 = 쓰기 차단.

begin;

-- 공개 대상 테이블
create policy "anon read buildings"           on buildings            for select to anon using (true);
create policy "anon read listing_snapshots"   on listing_snapshots    for select to anon using (true);
create policy "anon read floor_availabilities" on floor_availabilities for select to anon using (true);
create policy "anon read rent_terms"          on rent_terms           for select to anon using (true);
create policy "anon read building_images"     on building_images      for select to anon using (true);
create policy "anon read brokers"             on brokers              for select to anon using (true);
create policy "anon read building_aliases"    on building_aliases     for select to anon using (true);

commit;
```

- [ ] **Step 2: 마이그레이션 적용**

`mcp__supabase__apply_migration`로 적용 (name: `public_read_rls`, query: 위 SQL).

- [ ] **Step 3: anon SELECT 동작 검증**

ANON 키로 buildings SELECT가 되는지 확인하는 스크립트:

```bash
.venv/bin/python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_ANON_KEY'])
r = c.table('buildings').select('id,name').limit(3).execute()
print('anon SELECT buildings:', len(r.data), '건 OK')
"
```
Expected: `anon SELECT buildings: 3 건 OK`

- [ ] **Step 4: anon 쓰기 거부 + 내부테이블 차단 검증**

```bash
.venv/bin/python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_ANON_KEY'])
# 쓰기 시도 → 거부되어야 함
try:
    c.table('buildings').insert({'name':'해커','match_key':'name:해커'}).execute()
    print('FAIL: anon INSERT가 허용됨!')
except Exception as e:
    print('OK: anon INSERT 거부됨')
# 내부 테이블 조회 → 0건이어야 함
r = c.table('source_documents').select('id').limit(1).execute()
print('source_documents anon 조회:', len(r.data), '건 (0이어야 정상)')
"
```
Expected: `OK: anon INSERT 거부됨` + `source_documents anon 조회: 0 건`

- [ ] **Step 5: 마이그레이션 파일 커밋**

```bash
git add supabase/migrations/0020_public_read_rls.sql
git commit -m "feat: 공개 읽기 RLS (anon SELECT-only) 마이그레이션 0020"
```

---

## Task 0.5: 화면 전용 뷰 (마이그레이션 0021)

홈/검색/상세용 평탄화 뷰. security_invoker=on으로 RLS 상속.

**Files:**
- Create: `supabase/migrations/0021_web_views.sql`

- [ ] **Step 1: 뷰 SQL 작성**

```sql
-- 0021_web_views.sql
-- 웹 화면 전용 평탄화 뷰. security_invoker=on → 조회자 권한(anon RLS) 상속.

begin;

-- 건물별 공실수 + 최저 평당임대료 + 대표 썸네일 + 좌표 (홈/검색 카드)
create or replace view v_buildings_summary
with (security_invoker = on) as
select
    b.id                          as building_id,
    b.name,
    b.district,
    b.address_road,
    b.latitude,
    b.longitude,
    b.completed_year,
    b.floors_above,
    b.floors_below,
    coalesce(fa.vacancy_count, 0)  as vacancy_count,
    fa.min_rent_per_pyeong,
    img.thumbnail_path
from buildings b
left join lateral (
    select
        count(*) filter (where not f.is_total_row)        as vacancy_count,
        min(rt.rent_per_pyeong) filter (where rt.rent_per_pyeong > 0) as min_rent_per_pyeong
    from listing_snapshots ls
    left join floor_availabilities f on f.listing_snapshot_id = ls.id
    left join rent_terms rt          on rt.listing_snapshot_id = ls.id
    where ls.building_id = b.id and ls.is_latest
) fa on true
left join lateral (
    select bi.storage_path as thumbnail_path
    from building_images bi
    where bi.building_id = b.id
    order by case bi.kind
        when 'exterior' then 1 when 'lobby' then 2
        when 'interior' then 3 else 9 end,
        bi.page_number
    limit 1
) img on true;

-- 지도 핀 경량 (좌표 있는 건물만)
create or replace view v_buildings_map
with (security_invoker = on) as
select building_id, name, district, latitude, longitude, vacancy_count, min_rent_per_pyeong
from v_buildings_summary
where latitude is not null and longitude is not null;

-- 상세 한 방 조회 (건물 스펙 + 건축물대장 + 특장점)
create or replace view v_building_detail
with (security_invoker = on) as
select
    b.id as building_id, b.name, b.name_raw, b.district,
    b.address_road, b.address_raw, b.station_area,
    b.latitude, b.longitude,
    b.floors_above, b.floors_below,
    b.gross_area_sqm, b.gross_area_pyeong,
    b.efficiency_ratio, b.completed_year, b.ceiling_height_m,
    b.ev_count, b.parking_total, b.features_raw,
    b.main_purpose, b.building_coverage_ratio, b.floor_area_ratio,
    b.height_m, b.land_area_sqm, b.use_zone
from buildings b;

commit;
```

- [ ] **Step 2: 적용**

`mcp__supabase__apply_migration` (name: `web_views`).

- [ ] **Step 3: 뷰 조회 검증**

MCP execute_sql:
```sql
select building_id, name, vacancy_count, min_rent_per_pyeong, thumbnail_path
from v_buildings_summary
where name like '%케이스퀘어%' limit 3;
```
Expected: 케이스퀘어 건물의 공실수·최저임대료·썸네일경로가 채워져 나옴.

- [ ] **Step 4: 지도뷰 카운트**

```sql
select count(*) from v_buildings_map;
```
Expected: 좌표 보강된 건물 수(230+)와 일치.

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0021_web_views.sql
git commit -m "feat: 화면 전용 뷰 0021 (summary/map/detail)"
```

---

## Task 0.6: 임대료 추이 뷰 (마이그레이션 0022)

전체 스냅샷(is_latest 무관) + rent_terms를 월별로 평탄화.

**Files:**
- Create: `supabase/migrations/0022_rent_trend_view.sql`

- [ ] **Step 1: 뷰 SQL 작성**

```sql
-- 0022_rent_trend_view.sql
-- 임대료 추이: 모든 월 스냅샷 × rent_terms. building_id 필터로 월별 추이 조회.

begin;

create or replace view v_rent_trend
with (security_invoker = on) as
select
    ls.building_id,
    br.code            as broker,
    ls.snapshot_month,
    rt.scope_label,
    rt.rent_per_pyeong,
    rt.maintenance_per_pyeong,
    rt.deposit_per_pyeong
from listing_snapshots ls
join brokers br        on br.id = ls.broker_id
join rent_terms rt     on rt.listing_snapshot_id = ls.id
where rt.rent_per_pyeong is not null
order by ls.building_id, ls.snapshot_month;

commit;
```

- [ ] **Step 2: 적용**

`mcp__supabase__apply_migration` (name: `rent_trend_view`).

- [ ] **Step 3: 조회 검증**

```sql
select snapshot_month, broker, scope_label, rent_per_pyeong
from v_rent_trend
where building_id = (select id from buildings where name like '%케이스퀘어%' limit 1)
limit 10;
```
Expected: 2026-06-01 기준 행들이 나옴(현재 1개월).

- [ ] **Step 4: 커밋**

```bash
git add supabase/migrations/0022_rent_trend_view.sql
git commit -m "feat: 임대료 추이 뷰 0022 (v_rent_trend)"
```

---

## Task 0.7: 이미지 Storage 공개 접근 확인

building_images는 이미 1,418행. Storage 버킷에 실제 파일이 있는지, 공개 접근 가능한지 확인.

**Files:** (조사 전용 — 코드 변경은 결과에 따라)

- [ ] **Step 1: 버킷 공개 여부 + 파일 존재 확인**

```bash
.venv/bin/python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
buckets = c.storage.list_buckets()
for b in buckets:
    print('bucket:', b.name, 'public=', getattr(b,'public',None))
"
```

- [ ] **Step 2: 샘플 storage_path로 파일 조회**

MCP: `select storage_path from building_images limit 1;` → 그 경로로 파일 존재 확인.

- [ ] **Step 3: 결정 기록**

- 버킷 비공개 + 파일 있음 → 0023 마이그레이션으로 버킷 public 전환 또는 웹에서 signed URL.
- 파일 없음(메타만) → Phase 0 범위에서 이미지 표시는 placeholder, 이미지 업로드는 후속 작업으로 사용자에게 보고.

> 이 Task는 결과를 사용자에게 보고하고 다음 행동을 확인한다(이미지 관리 페이지가 후속이므로).

### 조사 결과 (2026-06-18 확정)
- building_images 메타 1,418행은 있으나 **Storage에 실제 PNG 0개**(과거 `--no-images` 적재). 경로 period도 `unknown`.
- **사용자 결정: 사진 없이 먼저 진행**. 모든 사진 자리는 회색 placeholder로 렌더. 이미지 업로드+관리페이지는 웹 화면(Phase 1~4) 완성 후 후속 작업.
- 따라서 PhotoGallery/BuildingCard 썸네일은 thumbnail_path가 있어도 **실파일 부재를 가정**하고 placeholder 우선. 후속 업로드 시 자동으로 실사진 노출되도록 컴포넌트 설계.

---

## Phase 0 완료 게이트

- [ ] 좌표 보유 건물 84 → 230+ 로 증가 (MCP 카운트)
- [ ] anon 키로 공개 테이블 SELECT 성공, INSERT 거부, 내부 테이블 0건
- [ ] v_buildings_summary / v_buildings_map / v_building_detail / v_rent_trend 조회 정상
- [ ] 이미지 Storage 상태 파악 및 사용자 보고
- [ ] **codex-rescue로 Phase 0 산출물 리뷰** (geocode.py, 마이그레이션 0020~0022)

게이트 통과 후 Phase 1(웹 셋업) 상세화 진행.

---

## Phase 0 검증 (end-to-end)

```bash
# 1) 좌표
.venv/bin/python cli.py geocode --dry-run --limit 3   # 동작 확인
.venv/bin/python cli.py geocode                        # 전체 보강
# 2) anon RLS
.venv/bin/python -c "..."  # Task 0.4 Step 3/4 스크립트
# 3) 뷰 (MCP execute_sql로 각 뷰 조회)
```

MCP 최종 확인:
```sql
select
  (select count(*) from buildings where latitude is not null) as coords,
  (select count(*) from v_buildings_map) as map_rows,
  (select count(*) from v_buildings_summary) as summary_rows;
```
