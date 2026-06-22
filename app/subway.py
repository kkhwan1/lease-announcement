"""전국 도시철도역 좌표 — 정적 마스터 적재 + 매물 최근접역 계산.

출처: 국가철도공단 레일포털 '전국도시철도역사정보 표준데이터'(XLSX, 전국 ~1,099역).
지하철역 좌표는 거의 불변이라 API가 아닌 정적 마스터(subway_stations)로 1회 적재한다.
매물(buildings) 좌표 기준 최근접역을 Haversine으로 계산해
building_commercial_areas.nearest_station* 컬럼에 보강한다.

XLSX는 표준 라이브러리(zipfile + xml)만으로 파싱한다(openpyxl 등 의존성 불필요).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

# 표준데이터 XLSX 헤더(2026-02 기준):
#   역번호, 역사명, 노선번호, 노선명, 영문역사명, 한자역사명, 환승역구분,
#   환승노선번호, 환승노선명, 역위도, 역경도, 운영기관명, 역사도로명주소,
#   역사전화번호, 데이터기준일자
_COL = {
    "station_code": "역번호",
    "name": "역사명",
    "line_code": "노선번호",
    "line_name": "노선명",
    "transfer": "환승역구분",
    "latitude": "역위도",
    "longitude": "역경도",
    "operator": "운영기관명",
    "road_address": "역사도로명주소",
    "base_date": "데이터기준일자",
}

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass
class Station:
    station_code: str | None
    name: str
    line_name: str | None
    line_code: str | None
    latitude: float
    longitude: float
    operator: str | None
    road_address: str | None
    is_transfer: bool
    base_date: str | None


def parse_stations_xlsx(path: str) -> list[Station]:
    """레일포털 표준데이터 XLSX 첫 시트를 파싱해 Station 리스트로 반환.

    위경도가 비거나 숫자가 아닌 행은 건너뛴다.
    """
    z = zipfile.ZipFile(path)

    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in tree.findall(f"{_NS}si"):
            shared.append("".join(node.text or "" for node in si.iter(f"{_NS}t")))

    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    data = sheet.find(f"{_NS}sheetData")
    rows = data.findall(f"{_NS}row") if data is not None else []

    def cell_value(c) -> str:
        v = c.find(f"{_NS}v")
        if v is None or v.text is None:
            return ""
        if c.get("t") == "s":
            return shared[int(v.text)]
        return v.text

    def col_letter(ref: str) -> str:
        """셀 참조('J2')에서 컬럼 문자('J')만 추출."""
        return "".join(ch for ch in (ref or "") if ch.isalpha())

    if not rows:
        return []

    # 빈 셀이 생략돼 위치 인덱싱이 어긋나므로 셀 참조(A/B/C…) 기반으로 매핑한다.
    # 헤더 행: 컬럼 문자 → 헤더 라벨
    header_by_col = {
        col_letter(c.get("r")): cell_value(c) for c in rows[0].findall(f"{_NS}c")
    }
    # 우리가 쓸 키 → 컬럼 문자
    col_of: dict[str, str] = {}
    for key, label in _COL.items():
        for col, lbl in header_by_col.items():
            if lbl == label:
                col_of[key] = col
                break

    def get(cells: dict[str, str], key: str) -> str:
        col = col_of.get(key)
        return cells.get(col, "").strip() if col else ""

    out: list[Station] = []
    for row in rows[1:]:
        cells = {
            col_letter(c.get("r")): cell_value(c) for c in row.findall(f"{_NS}c")
        }
        try:
            lat = float(get(cells, "latitude"))
            lon = float(get(cells, "longitude"))
        except (TypeError, ValueError):
            continue  # 좌표 없는 역 스킵
        name = get(cells, "name")
        if not name:
            continue
        out.append(Station(
            station_code=get(cells, "station_code") or None,
            name=name,
            line_name=get(cells, "line_name") or None,
            line_code=get(cells, "line_code") or None,
            latitude=lat,
            longitude=lon,
            operator=get(cells, "operator") or None,
            road_address=get(cells, "road_address") or None,
            is_transfer=get(cells, "transfer") == "환승역",
            base_date=get(cells, "base_date") or None,
        ))
    return out


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 직선거리(m). 지구 반지름 6,371km."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_station(
    lat: float, lon: float, stations: list[dict]
) -> tuple[dict, int] | None:
    """매물 좌표 기준 최근접역과 거리(m, 반올림)를 반환.

    stations: subway_stations 행 dict 리스트 (name/line_name/latitude/longitude).
    빈 리스트면 None.
    """
    best: dict | None = None
    best_d = float("inf")
    for s in stations:
        try:
            d = haversine_m(lat, lon, float(s["latitude"]), float(s["longitude"]))
        except (TypeError, ValueError, KeyError):
            continue
        if d < best_d:
            best_d, best = d, s
    if best is None:
        return None
    return best, round(best_d)
