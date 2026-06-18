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
_KK_GEOCODER_SRC = "/home/kkhwan/projects/kk_real_estate/src"


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
    """kk_real_estate V-World geocoder 폴백. 실패 시 None.

    geocoder.py가 형제 모듈/패키지 컨텍스트에 의존하므로 sys.path에
    src 경로를 추가해 import한다. 경로 존재를 먼저 검증한다.
    """
    import os.path

    if not os.path.exists(os.path.join(_KK_GEOCODER_SRC, "geocoder.py")):
        logger.warning("V-World geocoder 모듈 없음: %s", _KK_GEOCODER_SRC)
        return None
    try:
        if _KK_GEOCODER_SRC not in sys.path:
            sys.path.insert(0, _KK_GEOCODER_SRC)
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
