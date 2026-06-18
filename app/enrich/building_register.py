"""건축물대장 표제부 보강 — kk_real_estate 프로젝트 연동.

kk_real_estate는 별도 venv(.venv)와 .env를 갖지만, sys.path에 추가해 직접 임포트하는
방식을 사용한다. subprocess 방식은 dotenv 로드·geocoder 초기화 등 오버헤드가 크고
02_fetch_data.py stdout 경로 파싱이 취약해 직접 임포트로 대체한다.

매핑 (건축물대장 표제부 → BuildingExtraction):
  totArea       → gross_area_sqm            연면적 ㎡
  grndFlrCnt    → floors_above              지상 층수
  ugrndFlrCnt   → floors_below              지하 층수
  useAprDay     → completed_year            사용승인일 (YYYYMMDD → int 연도)
  bcRat         → building_coverage_ratio   건폐율 %
  vlRat         → floor_area_ratio          용적률 %
  mainPurpsCdNm → main_purpose              주용도명
  heit          → height_m                  건물 높이 m
  platArea      → land_area_sqm             대지면적 ㎡
  rideUseElvtCnt → ev_count                 승강기 대수

주소 매핑 quirk:
  V-World geocoder는 부번(ji)을 실제 지번 번호로 반환하지만,
  건축물대장 API는 집합건물의 경우 ji=0000 (부번 없음) 으로 등록된 경우가 많다.
  따라서 jigangu 우선 → ji=0000 폴백 순서로 조회한다.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

from app.enrich.base import Enricher
from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)

# kk_real_estate 프로젝트 루트 경로 (읽기 전용, 수정 금지)
_KK_ROOT = Path("/home/kkhwan/projects/kk_real_estate")
_KK_ENV = _KK_ROOT / ".env"


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


def _get_kk_modules() -> tuple[Any, Any] | None:
    """(geocoder 모듈, opendata 모듈) 반환. 임포트 실패 시 None."""
    if not _ensure_kk_on_path():
        logger.warning("[BuildingRegisterEnricher] kk_real_estate 디렉토리 없음: %s", _KK_ROOT)
        return None
    _load_kk_env()
    try:
        # 이미 임포트된 경우 캐시에서 꺼냄 (재임포트 방지)
        geocoder = importlib.import_module("src.geocoder")
        opendata = importlib.import_module("src.opendata")
        return geocoder, opendata
    except ImportError as exc:
        logger.warning("[BuildingRegisterEnricher] kk_real_estate 임포트 실패: %s", exc)
        return None


# ── 건축물대장 조회 ──────────────────────────────────────────────

def _fetch_title_item(addr: str) -> dict[str, Any] | None:
    """주소 → 건축물대장 표제부 대표 item dict.

    실패(geocode 불가, API 오류, 주소 미매칭) 시 None 반환.
    ji 폴백: geocoder 반환 ji → ji=0000 순으로 시도.
    """
    mods = _get_kk_modules()
    if mods is None:
        return None
    geocoder, opendata = mods

    # 1) geocode
    try:
        rec = geocoder.resolve(addr)
    except Exception as exc:
        logger.warning(
            "[BuildingRegisterEnricher] geocode 실패 — addr=%s: %s", addr, exc
        )
        return None

    # 2) 표제부 조회 (ji 폴백 포함)
    sg, bj, bn = rec.sigungu_cd, rec.bjdong_cd, rec.bun
    candidates_ji = [rec.ji]
    if rec.ji != "0000":
        candidates_ji.append("0000")  # 집합건물은 ji=0000으로 등록된 경우가 많음

    for ji in candidates_ji:
        try:
            res = opendata.building_title(sg, bj, bn, ji)
        except Exception as exc:
            logger.warning(
                "[BuildingRegisterEnricher] building_title 호출 실패 (ji=%s): %s", ji, exc
            )
            continue

        if res.ok and res.items:
            # 연면적(totArea) 최대 동을 대표동으로 선택 (kk_real_estate report.py 동일 로직)
            def _area(it: dict) -> float:
                try:
                    return float(str(it.get("totArea") or "0").replace(",", ""))
                except (ValueError, TypeError):
                    return 0.0

            item = max(res.items, key=_area)
            logger.debug(
                "[BuildingRegisterEnricher] 표제부 조회 성공 — addr=%s, ji=%s, 건수=%d",
                addr, ji, res.total_count,
            )
            return item

    logger.warning(
        "[BuildingRegisterEnricher] 표제부 item 없음 — addr=%s (ji 후보: %s)",
        addr, candidates_ji,
    )
    return None


# ── Enricher 구현 ────────────────────────────────────────────────

class BuildingRegisterEnricher(Enricher):
    """건축물대장 표제부 보강 Enricher.

    kk_real_estate를 직접 임포트해 표제부(getBrTitleInfo) 데이터를 가져온 뒤
    빈 필드를 채운다. 호출 실패 시 b를 그대로 반환하므로 파이프라인이 보강 없이도
    정상 동작한다 (graceful degradation).
    """

    name = "building_register"

    def enrich(self, b: BuildingExtraction) -> BuildingExtraction:
        """건축물대장 표제부로 b의 빈 필드 보강."""
        # 보강 후보 없으면 API 호출 절약
        missing = set(b.missing_fields())
        fillable = {
            "gross_area_sqm", "floors_above", "floors_below", "completed_year",
            "building_coverage_ratio", "floor_area_ratio", "main_purpose",
            "height_m", "land_area_sqm",
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

        item = _fetch_title_item(addr)
        if item is None:
            return b

        # ── 필드 매핑 (빈 필드만, PDF 우선 정책) ──
        filled: list[str] = []

        mapping = [
            ("gross_area_sqm",            _to_float(item.get("totArea"))),
            ("floors_above",              _to_int(item.get("grndFlrCnt"))),
            ("floors_below",              _to_int(item.get("ugrndFlrCnt"))),
            ("completed_year",            _parse_year(item.get("useAprDay"))),
            ("building_coverage_ratio",   _to_float(item.get("bcRat"))),
            ("floor_area_ratio",          _to_float(item.get("vlRat"))),
            ("main_purpose",              item.get("mainPurpsCdNm") or None),
            ("height_m",                  _to_float(item.get("heit"))),
            ("land_area_sqm",             _to_float(item.get("platArea"))),
            # ev_count — missing_fields()에는 없지만 표제부에 있으면 채움
            ("ev_count",                  _to_int(item.get("rideUseElvtCnt"))),
        ]

        for field, value in mapping:
            if self._set_field(b, field, value):
                filled.append(field)

        if filled:
            logger.info(
                "[BuildingRegisterEnricher] %s — %d개 필드 채움: %s",
                b.building_name, len(filled), ", ".join(filled),
            )
        else:
            logger.info(
                "[BuildingRegisterEnricher] %s — API 응답 있으나 추가 채울 필드 없음",
                b.building_name,
            )

        return b
