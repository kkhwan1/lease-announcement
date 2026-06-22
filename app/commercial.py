"""소상공인시장진흥공단 상가(상권)정보 API — 건물 좌표 반경 점포 집계.

BDS Planet '발달상권 정보'와 동일한 공공데이터 출처(B553077). 건물 좌표(lat/lon)
기준 반경 내 상가업소 목록을 모두 받아 업종 대분류(도소매/서비스/외식)로 집계한다.

키 전달(중요): httpx params에 raw DATAGO_SERVICE_KEY를 넣어 httpx가 자동 URL
인코딩하게 둔다. urllib quote(safe="")로는 동작하지 않음(kk_real_estate
src/opendata.py 검증 패턴 — 건축물대장 API와 동일 키·동일 호출 방식).
"""
from __future__ import annotations

import collections
import os
from dataclasses import dataclass, field

import httpx

BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
# 행정안전부 주민등록 인구·세대현황(법정동별). PNU 앞 10자리(법정동코드)와 직결.
PPLTN_BASE = "https://apis.data.go.kr/1741000/stdgPpltnHhStus"
UA = "lease-platform/1.0"

# 거주인구 통계 조회월(YYYYMM). 데이터 가용성 확인된 값(2026-06-18 검증: 202604 정상).
PPLTN_YM = "202604"

# 업종 대분류 코드(indsLclsCd)를 BDS 3분류로 매핑한다(실응답 검증 2026-06-18).
# 소상공인 상가업소 표준 대분류 코드:
#   G2=소매, I2=음식, I1=숙박, L1=부동산, M1=과학·기술, N1=시설관리·임대,
#   P1=교육, Q1=보건의료, R1=예술·스포츠, S2=수리·개인 등.
#   - G2(소매)  → 도소매(retail)
#   - I2(음식)  → 외식(food)
#   - 그 외      → 서비스(service)
# 코드 기반 매핑이 한글 부분일치보다 정확(부동산/보건의료의 오분류 방지).
_RETAIL_CODES = {"G2"}
_FOOD_CODES = {"I2"}


@dataclass
class CommercialSummary:
    """건물 1개의 반경 상권 집계 결과 + 법정동 거주인구."""

    area_name: str | None
    store_count: int
    retail_count: int
    service_count: int
    food_count: int
    radius_m: int
    base_period: str | None
    # 세부업종(중분류) Top — [{"name": "회계·세무", "count": 99}, ...]
    top_industries: list[dict] = field(default_factory=list)
    # 법정동 거주인구 (행안부 주민등록)
    dong_name: str | None = None          # 법정동명
    resident_total: int | None = None     # 총 거주인구
    resident_male: int | None = None
    resident_female: int | None = None
    household_count: int | None = None     # 세대수
    resident_period: str | None = None     # 통계 기준월 'YYYY.MM'
    ldong_cd: str | None = None            # 최빈 법정동코드(직장인구 조인용)


def _key() -> str:
    k = os.environ.get("DATAGO_SERVICE_KEY", "").strip()
    if not k:
        raise RuntimeError("DATAGO_SERVICE_KEY 미설정 — .env 확인")
    return k


def _classify(lcls_code: str) -> str:
    """업종 대분류 코드 → 'retail' | 'food' | 'service'."""
    if lcls_code in _RETAIL_CODES:
        return "retail"
    if lcls_code in _FOOD_CODES:
        return "food"
    return "service"


def _extract_body(payload: dict) -> dict:
    """응답 JSON에서 body 딕셔너리를 꺼낸다(래핑 방식 2가지 모두 대응)."""
    if not isinstance(payload, dict):
        return {}
    if "response" in payload:
        return (payload.get("response") or {}).get("body", {}) or {}
    return payload.get("body", {}) or {}


def _extract_items(body: dict) -> list[dict]:
    """body에서 item 리스트를 꺼낸다(items.item / items / list 변형 대응)."""
    items = body.get("items")
    if items is None:
        items = body.get("list")  # 일부 오퍼레이션은 'list' 키 사용
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):  # item이 단일 객체로 올 때
        items = [items]
    return items or []


def fetch_commercial(
    lat: float,
    lon: float,
    radius_m: int = 300,
    timeout: float = 25.0,
) -> CommercialSummary | None:
    """건물 좌표 반경 내 점포를 모두 받아 업종 대분류로 집계.

    데이터 없으면 None. API 오류는 예외로 던진다(호출부에서 건별 처리).
    """
    rows: list[dict] = []
    page = 1
    with httpx.Client(timeout=timeout, headers={"User-Agent": UA}) as cli:
        while page <= 20:  # 안전 상한 (최대 20*1000 = 2만 점포)
            params = {
                "serviceKey": _key(),
                "radius": str(radius_m),
                "cx": str(lon),  # 경도 (소상공인 API는 cx=경도)
                "cy": str(lat),  # 위도
                "type": "json",
                "numOfRows": "1000",
                "pageNo": str(page),
            }
            r = cli.get(f"{BASE}/storeListInRadius", params=params)
            r.raise_for_status()
            body = _extract_body(r.json())
            items = _extract_items(body)
            if not items:
                break
            rows.extend(items)
            try:
                total = int(body.get("totalCount", 0) or 0)
            except (TypeError, ValueError):
                total = 0
            if (total and len(rows) >= total) or len(items) < 1000:
                break
            page += 1

    if not rows:
        return None

    retail = food = service = 0
    mid_counter: collections.Counter[str] = collections.Counter()  # 세부업종(중분류)
    ldong_codes: collections.Counter[str] = collections.Counter()  # 법정동코드
    for it in rows:
        # 업종 대분류 코드(indsLclsCd) 기반 분류 — G2=소매, I2=음식, 그외=서비스
        kind = _classify((it.get("indsLclsCd") or "").strip())
        if kind == "retail":
            retail += 1
        elif kind == "food":
            food += 1
        else:
            service += 1
        mcls = (it.get("indsMclsNm") or "").strip()
        if mcls:
            mid_counter[mcls] += 1
        lcode = (it.get("ldongCd") or "").strip()
        if lcode:
            ldong_codes[lcode] += 1

    # 세부업종 Top 6
    top_industries = [
        {"name": nm, "count": n} for nm, n in mid_counter.most_common(6)
    ]

    # 상권명·기준일은 별도 오퍼레이션(storeZoneInRadius)에서 가장 가까운 주요상권으로.
    # 상권 폴리곤은 점포보다 듬성해, 점포 반경과 같으면 폴리곤에 안 닿는 건물이 생긴다.
    # 따라서 상권영역 조회는 최소 500m로 넓게 잡는다. 점포 응답에는 발달상권명이
    # 없어 행정동(ldongNm)을 폴백으로 둔다.
    zone_radius = max(radius_m, 500)
    area_name, base_period = _nearest_zone(lat, lon, zone_radius, timeout)
    if not area_name:
        ldongs = [(it.get("ldongNm") or "").strip() for it in rows]
        ldongs = [n for n in ldongs if n]
        area_name = max(set(ldongs), key=ldongs.count) if ldongs else None

    # 거주인구·직장인구 — 점포 최빈 법정동코드 기준(건물이 속한 법정동).
    ppl = None
    top_ldong = ldong_codes.most_common(1)[0][0] if ldong_codes else None
    if top_ldong:
        ppl = _fetch_population(top_ldong, timeout)

    summary = CommercialSummary(
        area_name=area_name,
        store_count=len(rows),
        retail_count=retail,
        service_count=service,
        food_count=food,
        radius_m=radius_m,
        base_period=base_period,
        top_industries=top_industries,
        ldong_cd=top_ldong,
    )
    if ppl:
        (summary.dong_name, summary.resident_total, summary.resident_male,
         summary.resident_female, summary.household_count,
         summary.resident_period) = ppl
    return summary


def _fetch_population(
    stdg_cd: str, timeout: float
) -> tuple[str | None, int, int, int, int, str] | None:
    """법정동코드(10자리)의 거주인구를 통+반 전체 합산해 반환.

    행안부 주민등록 인구·세대현황(법정동별). 응답은 통/반 최소단위로 쪼개져
    오므로 totNmprCnt/hhCnt/maleNmprCnt/femlNmprCnt를 모두 합산한다.
    반환: (법정동명, 총인구, 남, 녀, 세대수, 'YYYY.MM'). 실패 시 None.
    """
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": UA}) as cli:
            page = 1
            while page <= 10:  # 안전 상한 (동당 행 수백~수천)
                r = cli.get(f"{PPLTN_BASE}/selectStdgPpltnHhStus", params={
                    "serviceKey": _key(),
                    "type": "json",
                    "numOfRows": "1000",
                    "pageNo": str(page),
                    "stdgCd": stdg_cd,
                    "srchFrYm": PPLTN_YM,
                    "srchToYm": PPLTN_YM,
                })
                r.raise_for_status()
                resp = r.json().get("Response", {})
                items = resp.get("items", "")
                arr = items.get("item", []) if isinstance(items, dict) else []
                if not arr:
                    break
                rows.extend(arr)
                if len(arr) < 1000:
                    break
                page += 1
    except Exception:
        return None
    if not rows:
        return None

    def _sum(field_name: str) -> int:
        s = 0
        for x in rows:
            try:
                s += int(x.get(field_name) or 0)
            except (TypeError, ValueError):
                pass
        return s

    name = (rows[0].get("stdgNm") or "").strip() or None
    period = PPLTN_YM[:4] + "." + PPLTN_YM[4:6]
    return (
        name,
        _sum("totNmprCnt"),
        _sum("maleNmprCnt"),
        _sum("femlNmprCnt"),
        _sum("hhCnt"),
        period,
    )


def _nearest_zone(
    lat: float, lon: float, radius_m: int, timeout: float
) -> tuple[str | None, str | None]:
    """반경 내 주요상권 중 첫 번째의 (상권명, 기준일)을 반환.

    storeZoneInRadius: mainTrarNm(상권명), stdrDt(데이터 기준일 'YYYY-MM-DD').
    실패해도 (None, None)으로 graceful — 점포 집계는 유효해야 하므로.
    """
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": UA}) as cli:
            r = cli.get(f"{BASE}/storeZoneInRadius", params={
                "serviceKey": _key(),
                "radius": str(radius_m),
                "cx": str(lon),
                "cy": str(lat),
                "type": "json",
                "numOfRows": "1",
                "pageNo": "1",
            })
            r.raise_for_status()
            items = _extract_items(_extract_body(r.json()))
    except Exception:
        return None, None
    if not items:
        return None, None
    z = items[0]
    name = (z.get("mainTrarNm") or z.get("trarNm") or "").strip() or None
    std = (z.get("stdrDt") or "").strip()
    # 'YYYY-MM-DD' → 'YYYY.MM' 표기
    period = None
    if len(std) >= 7:
        period = std[:7].replace("-", ".")
    return name, period
