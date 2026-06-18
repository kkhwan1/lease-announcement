"""건축물대장 표제부 보강 — kk_real_estate 프로젝트 연동.

kk_real_estate는 별도 venv(.venv)와 .env를 갖지만, sys.path에 추가해 직접 임포트하는
방식을 사용한다. subprocess 방식은 dotenv 로드·geocoder 초기화 등 오버헤드가 크고
stdout 경로 파싱이 취약해 직접 임포트로 대체한다.

채우는 필드:
  표제부(getBrTitleInfo):
    totArea       → gross_area_sqm            연면적 ㎡
    grndFlrCnt    → floors_above              지상 층수
    ugrndFlrCnt   → floors_below              지하 층수
    useAprDay     → completed_year            사용승인일 (YYYYMMDD → 연도 int)
    bcRat         → building_coverage_ratio   건폐율 %
    vlRat         → floor_area_ratio          용적률 %
    mainPurpsCdNm → main_purpose              주용도명
    heit          → height_m                  건물 높이 m
    platArea      → land_area_sqm             대지면적 ㎡
    rideUseElvtCnt → ev_count                 승강기 대수

  총괄표제부(getBrRecapTitleInfo):
    totPkngCnt    → parking_total             주차 총 대수

  지오코딩(V-World geocoder.resolve):
    rec.lat       → latitude                  위도
    rec.lon       → longitude                 경도

  토지이용계획(V-World landuse_attr):
    prposAreaDstrcCodeNm 중 UQA* 코드 → use_zone  용도지역명

주소 매핑 quirk:
  V-World geocoder는 부번(ji)을 실제 지번 번호로 반환하지만,
  건축물대장 API는 집합건물의 경우 ji=0000(부번 없음)으로 등록된 경우가 많다.
  표제부·총괄표제부 모두 geocoder 반환 ji → 0000 폴백 순서로 조회한다.

캐시:
  같은 주소의 반복 조회를 방지하기 위해 모듈 수준 메모리 캐시를 사용한다.
  (key=정규화된 주소, value=_FetchResult). 프로세스 재시작 전까지 유효.
  309개 건물 배치에서 동일 주소 중복 조회를 막아 API 호출·시간을 절약한다.

타임아웃:
  threading.Thread + join(timeout)으로 건물당 최대 대기 시간을 제한한다.
  초과 시 graceful skip — 파이프라인이 보강 없이 계속 진행된다.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.enrich.base import Enricher
from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)

# kk_real_estate 프로젝트 루트 경로 (읽기 전용, 수정 금지)
_KK_ROOT = Path("/home/kkhwan/projects/kk_real_estate")
_KK_ENV = _KK_ROOT / ".env"

# 용도지역 코드 접두사 — 국토교통부 토지이용계획 prposAreaDstrcCode 체계
# UQA* = 도시계획 용도지역 (일반주거/상업/공업/녹지)
_USE_ZONE_PREFIX = "UQA"


# ── 헬퍼: 숫자 변환 ──────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    """문자열/숫자 → float. 0이거나 변환 불가면 None."""
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", "").strip())
        return f if f != 0.0 else None
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    f = _to_float(v)
    return int(f) if f is not None else None


def _parse_year(v: Any) -> int | None:
    """YYYYMMDD(또는 YYYY...) → 연도 int. 범위 밖이면 None."""
    s = str(v or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        return y if 1900 < y < 2100 else None
    return None


def _use_zone_from_landuse(items: list[dict]) -> str | None:
    """토지이용계획 item 목록에서 용도지역명 추출.

    prposAreaDstrcCode가 UQA로 시작하는 항목이 도시계획 용도지역이다.
    UQA01X(도시지역/관리지역 등 상위 분류)보다 UQA2xx/UQA3xx 등
    세부 용도지역(일반상업지역/제2종일반주거지역 등)을 우선 반환한다.
    세부 코드가 없으면 UQA01X를 반환한다.
    """
    # 1순위: UQA로 시작하고 코드가 UQA01X가 아닌 것 (세부 용도지역)
    for it in items:
        code = str(it.get("prposAreaDstrcCode") or "")
        if code.startswith(_USE_ZONE_PREFIX) and code != "UQA01X":
            name = it.get("prposAreaDstrcCodeNm")
            if name:
                return str(name).strip()
    # 2순위: UQA01X (상위 분류 — 세부 코드 없을 때 폴백)
    for it in items:
        code = str(it.get("prposAreaDstrcCode") or "")
        if code.startswith(_USE_ZONE_PREFIX):
            name = it.get("prposAreaDstrcCodeNm")
            if name:
                return str(name).strip()
    return None


# ── kk_real_estate 임포트 관리 ───────────────────────────────────

def _ensure_kk_on_path() -> bool:
    """kk_real_estate 루트 및 venv site-packages를 sys.path에 추가.

    kk_real_estate는 별도 venv를 사용하므로 xmltodict·httpx 등 의존성이
    우리 venv에 없다. 해당 venv의 site-packages를 path에 추가해야 임포트 가능.
    """
    if not _KK_ROOT.is_dir():
        return False

    # 프로젝트 루트 (src/ 패키지 임포트용)
    kk = str(_KK_ROOT)
    if kk not in sys.path:
        sys.path.insert(0, kk)

    # kk_real_estate venv site-packages (xmltodict, httpx 등 의존성)
    site_pkgs = _KK_ROOT / ".venv" / "lib" / "python3.12" / "site-packages"
    if site_pkgs.is_dir():
        sp = str(site_pkgs)
        if sp not in sys.path:
            sys.path.insert(1, sp)

    return True


def _load_kk_env() -> None:
    """kk_real_estate/.env 로드 (이미 세팅된 키는 덮어쓰지 않음)."""
    if not _KK_ENV.exists():
        return
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(str(_KK_ENV)).items():
            if k not in os.environ and v is not None:
                os.environ[k] = v
    except Exception as exc:
        logger.debug("[BuildingRegisterEnricher] .env 로드 실패: %s", exc)


def _get_kk_modules() -> tuple[Any, Any, Any] | None:
    """(geocoder, opendata, vworld_land) 모듈 반환. 임포트 실패 시 None."""
    if not _ensure_kk_on_path():
        logger.warning("[BuildingRegisterEnricher] kk_real_estate 디렉토리 없음: %s", _KK_ROOT)
        return None
    _load_kk_env()
    try:
        geocoder = importlib.import_module("src.geocoder")
        opendata = importlib.import_module("src.opendata")
        vworld_land = importlib.import_module("src.vworld_land")
        return geocoder, opendata, vworld_land
    except ImportError as exc:
        logger.warning("[BuildingRegisterEnricher] kk_real_estate 임포트 실패: %s", exc)
        return None


# ── 캐시 ─────────────────────────────────────────────────────────

@dataclass
class _FetchResult:
    """geocode + 건축물대장 조회 결과 묶음. 캐시 단위."""
    lat: float | None = None
    lon: float | None = None
    pnu: str | None = None
    title_item: dict[str, Any] = field(default_factory=dict)        # 표제부 대표 동
    recap_item: dict[str, Any] = field(default_factory=dict)        # 총괄표제부
    landuse_items: list[dict[str, Any]] = field(default_factory=list)  # 토지이용계획


# 주소 → _FetchResult 메모리 캐시 (프로세스 수명 동안 유효)
_cache: dict[str, _FetchResult] = {}
_cache_lock = threading.Lock()


def _normalize_addr(addr: str) -> str:
    """캐시 키 정규화 — 앞뒤 공백 제거 및 연속 공백 단일화."""
    return " ".join(addr.strip().split())


# ── 건축물대장 조회 내부 함수 ────────────────────────────────────

def _best_title_item(items: list[dict]) -> dict[str, Any]:
    """연면적(totArea) 최대 동 = 대표동 (kk_real_estate report.py 동일 로직)."""
    def _area(it: dict) -> float:
        try:
            return float(str(it.get("totArea") or "0").replace(",", ""))
        except (ValueError, TypeError):
            return 0.0
    return max(items, key=_area)


def _query_title(
    opendata: Any, sg: str, bj: str, bn: str, ji: str,
) -> tuple[dict[str, Any], str]:
    """표제부 조회. ji → 0000 폴백. (item, 실제_사용된_ji) 반환."""
    for try_ji in ([ji] if ji == "0000" else [ji, "0000"]):
        try:
            res = opendata.building_title(sg, bj, bn, try_ji)
            if res.ok and res.items:
                return _best_title_item(res.items), try_ji
        except Exception as e:
            logger.debug("[BuildingRegisterEnricher] building_title 실패(ji=%s): %s", try_ji, e)
    return {}, ji


def _query_recap(
    opendata: Any, sg: str, bj: str, bn: str, ji: str,
) -> dict[str, Any]:
    """총괄표제부 조회. ji → 0000 폴백."""
    for try_ji in ([ji] if ji == "0000" else [ji, "0000"]):
        try:
            res = opendata.building_recap(sg, bj, bn, try_ji)
            if res.ok and res.items:
                return res.items[0]
        except Exception as e:
            logger.debug("[BuildingRegisterEnricher] building_recap 실패(ji=%s): %s", try_ji, e)
    return {}


def _fetch(addr: str, timeout: int) -> _FetchResult | None:
    """주소 → _FetchResult. threading.Thread로 타임아웃 제어. 실패 시 None."""
    mods = _get_kk_modules()
    if mods is None:
        return None
    geocoder, opendata, vworld_land = mods

    result: list[_FetchResult] = []
    errors: list[Exception] = []

    def _run() -> None:
        try:
            # 1) 지오코딩 (V-World)
            rec = geocoder.resolve(addr)
            fr = _FetchResult(lat=rec.lat, lon=rec.lon, pnu=rec.pnu)
            sg, bj, bn, ji = rec.sigungu_cd, rec.bjdong_cd, rec.bun, rec.ji

            # 2) 표제부 (ji 폴백 포함)
            fr.title_item, used_ji = _query_title(opendata, sg, bj, bn, ji)

            # 3) 총괄표제부 (주차)
            fr.recap_item = _query_recap(opendata, sg, bj, bn, used_ji)

            # 4) 토지이용계획 (용도지역) — V-World
            try:
                lr = vworld_land.landuse_attr(rec.pnu)
                fr.landuse_items = lr.items if lr.ok else []
            except Exception as e:
                logger.debug("[BuildingRegisterEnricher] landuse_attr 실패: %s", e)
                fr.landuse_items = []

            result.append(fr)
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        # 타임아웃 — daemon 스레드이므로 프로세스 종료 시 함께 종료됨
        logger.warning("[BuildingRegisterEnricher] 타임아웃(%ds) — addr=%s", timeout, addr)
        return None

    if errors:
        logger.warning("[BuildingRegisterEnricher] 조회 실패 — addr=%s: %s", addr, errors[0])
        return None

    fr = result[0] if result else None
    if fr and not fr.title_item:
        logger.warning(
            "[BuildingRegisterEnricher] 표제부 item 없음(주소 매핑 실패?) — addr=%s", addr
        )
    return fr


def _fetch_cached(addr: str, timeout: int) -> _FetchResult | None:
    """캐시 히트 시 즉시 반환, 미스 시 _fetch() 후 캐시에 저장."""
    key = _normalize_addr(addr)
    with _cache_lock:
        if key in _cache:
            logger.debug("[BuildingRegisterEnricher] 캐시 히트 — addr=%s", addr)
            return _cache[key]

    fr = _fetch(addr, timeout)

    if fr is not None:
        with _cache_lock:
            _cache[key] = fr

    return fr


# ── Enricher 구현 ────────────────────────────────────────────────

class BuildingRegisterEnricher(Enricher):
    """건축물대장 + 지오코딩 + 토지이용계획 통합 보강 Enricher.

    채우는 필드 (빈 필드만, PDF 우선 정책):
      - gross_area_sqm, floors_above, floors_below, completed_year
      - building_coverage_ratio, floor_area_ratio, main_purpose
      - height_m, land_area_sqm, ev_count  (건축물대장 표제부)
      - parking_total                       (건축물대장 총괄표제부)
      - latitude, longitude                 (V-World 지오코딩)
      - use_zone                            (V-World 토지이용계획 용도지역)

    성능:
      - timeout(기본 30초) 초과 시 graceful skip.
      - 주소별 메모리 캐시로 309개 건물 배치 중 중복 조회 방지.
    """

    name = "building_register"

    def __init__(self, timeout: int = 30) -> None:
        # 건물당 API 조회 타임아웃 (초). 30초 권장 (geocode+표제부+총괄+landuse 4회 호출).
        self.timeout = timeout

    def enrich(self, b: BuildingExtraction) -> BuildingExtraction:
        """건축물대장/지오코딩/토지이용계획으로 b의 빈 필드 보강."""
        missing = set(b.missing_fields())
        fillable = {
            "gross_area_sqm", "floors_above", "floors_below", "completed_year",
            "building_coverage_ratio", "floor_area_ratio", "main_purpose",
            "height_m", "land_area_sqm",
            "parking_total",
            "latitude", "longitude",
            "use_zone",
        }
        if not (missing & fillable):
            logger.debug(
                "[BuildingRegisterEnricher] %s — 채울 필드 없음, 스킵", b.building_name
            )
            return b

        # 조회용 주소: 도로명 우선 → 지번 → raw
        addr = b.address_road or b.address_jibun or b.address_raw
        if not addr:
            logger.warning(
                "[BuildingRegisterEnricher] %s — 주소 없음, 보강 불가", b.building_name
            )
            return b

        logger.info(
            "[BuildingRegisterEnricher] %s 보강 시작 — addr=%s", b.building_name, addr
        )

        fr = _fetch_cached(addr, self.timeout)
        if fr is None:
            return b

        filled: list[str] = []

        # ── 지오코딩 ──
        if self._set_field(b, "latitude", fr.lat):
            filled.append("latitude")
        if self._set_field(b, "longitude", fr.lon):
            filled.append("longitude")

        # ── 표제부 ──
        t = fr.title_item
        for fld, val in [
            ("gross_area_sqm",          _to_float(t.get("totArea"))),
            ("floors_above",            _to_int(t.get("grndFlrCnt"))),
            ("floors_below",            _to_int(t.get("ugrndFlrCnt"))),
            ("completed_year",          _parse_year(t.get("useAprDay"))),
            ("building_coverage_ratio", _to_float(t.get("bcRat"))),
            ("floor_area_ratio",        _to_float(t.get("vlRat"))),
            ("main_purpose",            t.get("mainPurpsCdNm") or None),
            ("height_m",                _to_float(t.get("heit"))),
            ("land_area_sqm",           _to_float(t.get("platArea"))),
            ("ev_count",                _to_int(t.get("rideUseElvtCnt"))),
        ]:
            if self._set_field(b, fld, val):
                filled.append(fld)

        # ── 총괄표제부 (주차) ──
        if self._set_field(b, "parking_total", _to_int(fr.recap_item.get("totPkngCnt"))):
            filled.append("parking_total")

        # ── 토지이용계획 (용도지역) ──
        zone = _use_zone_from_landuse(fr.landuse_items)
        if self._set_field(b, "use_zone", zone):
            filled.append("use_zone")

        if filled:
            logger.info(
                "[BuildingRegisterEnricher] %s — %d개 필드 채움: %s",
                b.building_name, len(filled), ", ".join(filled),
            )
        else:
            logger.info(
                "[BuildingRegisterEnricher] %s — 응답 있으나 추가 채울 필드 없음",
                b.building_name,
            )

        return b
