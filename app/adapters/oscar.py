"""오스카앤컴퍼니 추출 어댑터.

오스카 안내문은 1페이지=1건물 상세이며 PyMuPDF find_tables()로
3종 표가 깔끔하게 추출된다:
  표0 (7x4): 건물 기본정보 (주소/빌딩규모/전용면적/연면적/E.V/준공일/천정고/전용률/주차/특장점)
  표1 (4x4): 층별 공실   (공실층/전용면적/임대면적/입주시기) — 1:N, Total 행 포함
  표2 (2x4): 임대조건    (관련층/보증금/임대료/관리비)

표는 헤더 셀 텍스트로 종류를 식별한다 (페이지마다 표 순서가 다를 수 있어 위치 의존 X).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.adapters.base import ExtractorAdapter
from app.normalize import (
    classify_availability,
    classify_district,
    normalize_building_name,
    parse_area,
    parse_korean_money,
    parse_scale,
)
from app.schemas import (
    BrokerCode,
    BuildingExtraction,
    FloorAvailability,
    RentTerm,
)

if TYPE_CHECKING:
    import fitz


def _clean(v) -> str:
    """셀 값을 한 줄 문자열로 정리 (None → '')."""
    if v is None:
        return ""
    return str(v).replace("\n", " ").strip()


def _num(s: str) -> Optional[float]:
    """순수 숫자 문자열 → float. 실패 시 None."""
    s = _clean(s).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> Optional[int]:
    """'2022년' '100대' '5대' 같은 표기에서 첫 정수 추출."""
    import re
    s = _clean(s)
    m = re.search(r"(\d+)", s.replace(",", ""))
    return int(m.group(1)) if m else None


class OscarTableAdapter(ExtractorAdapter):
    """오스카앤컴퍼니 표 기반 추출기."""

    broker = BrokerCode.OSCAR

    def extract(
        self,
        doc: "fitz.Document",
        page_group,
        source_filename: str,
        source_month: str | None = None,
    ) -> BuildingExtraction:
        name_raw = page_group.building_name
        building = BuildingExtraction(
            broker=self.broker,
            source_filename=source_filename,
            source_month=source_month,
            page_range=[i + 1 for i in page_group.page_indices],
            building_name=normalize_building_name(name_raw) or name_raw,
            building_name_raw=name_raw,
            extraction_method="rule_table",
        )

        # 그룹의 모든 페이지에서 표를 수집 (사진 페이지엔 표 없음 → 자연 skip)
        for idx in page_group.page_indices:
            page = doc[idx]
            try:
                tables = page.find_tables().tables
            except Exception:
                continue
            for t in tables:
                rows = t.extract()
                if not rows:
                    continue
                kind = self._classify_table(rows)
                if kind == "info":
                    self._parse_info_table(rows, building)
                elif kind == "floor":
                    self._parse_floor_table(rows, building)
                elif kind == "rent":
                    self._parse_rent_table(rows, building)

        self._finalize(building)
        return building

    # ------------------------------------------------------------------
    # 표 종류 식별 (헤더 셀 텍스트 기반)
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_table(rows: list[list]) -> Optional[str]:
        flat = " ".join(_clean(c) for row in rows for c in row)
        # 층별 공실표: '공실층' + '입주시기'
        if "공실층" in flat or ("임대면적" in flat and "입주시기" in flat):
            return "floor"
        # 임대조건표: '보증금' + '관리비'
        if "보증금" in flat and "관리비" in flat:
            return "rent"
        # 건물정보표: '연면적' 또는 '전용률' 또는 '주소'
        if any(k in flat for k in ("연면적", "전용률", "빌딩 규모", "준공")):
            return "info"
        return None

    # ------------------------------------------------------------------
    # 표0: 건물 기본정보 (키-값이 좌우로 교대하는 격자)
    # ------------------------------------------------------------------
    def _parse_info_table(self, rows: list[list], b: BuildingExtraction) -> None:
        # 키-값 쌍을 모두 수집: (col0,col1), (col2,col3) ...
        kv: dict[str, str] = {}
        for row in rows:
            cells = [_clean(c) for c in row]
            i = 0
            while i < len(cells) - 1:
                key = cells[i].replace(" ", "")
                val = cells[i + 1]
                if key and val:
                    kv[key] = val
                i += 2

        def get(*keys: str) -> str:
            for k in keys:
                if k in kv:
                    return kv[k]
            return ""

        if (v := get("주소")):
            b.address_raw = v
            b.address_road = v
        if (v := get("빌딩규모")):
            b.scale_raw = v
            b.floors_above, b.floors_below = parse_scale(v)
        if (v := get("전용면적")):
            b.exclusive_area_sqm, b.exclusive_area_pyeong = parse_area(v)
        if (v := get("연면적")):
            b.gross_area_sqm, b.gross_area_pyeong = parse_area(v)
        if (v := get("E/V", "EV", "엘리베이터")):
            b.ev_count = _to_int(v)
        if (v := get("준공일", "준공", "준공연도", "준공년도")):
            b.completed_raw = v
            b.completed_year = _to_int(v)
        if (v := get("천정고", "층고")):
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", v)
            if m:
                b.ceiling_height_m = float(m.group(1))
        if (v := get("전용률", "전용율")):
            n = _num(v.replace("%", ""))
            if n is not None:
                b.efficiency_ratio = n
        if (v := get("총주차대수", "주차대수", "총주차")):
            b.parking_total = _to_int(v)
        if (v := get("주차조건", "주차사항")):
            b.parking_terms_raw = v
        if (v := get("특장점", "특이사항")):
            b.features_raw = v

        # 권역/역세권: 특장점·주소에서 역명 추정
        src = " ".join(filter(None, [b.features_raw, b.address_raw]))
        b.district = classify_district(src)

    # ------------------------------------------------------------------
    # 표1: 층별 공실 (헤더행 + 데이터행 N개, Total 포함)
    # ------------------------------------------------------------------
    def _parse_floor_table(self, rows: list[list], b: BuildingExtraction) -> None:
        if len(rows) < 2:
            return
        # 헤더에서 컬럼 위치 파악
        header = [_clean(c) for c in rows[0]]
        col = {name: i for i, name in enumerate(header)}

        def cidx(*names: str) -> Optional[int]:
            for n in names:
                for h, i in col.items():
                    if n in h.replace(" ", ""):
                        return i
            return None

        i_floor = cidx("공실층", "층")
        i_excl = cidx("전용면적")
        i_lease = cidx("임대면적")
        i_avail = cidx("입주시기", "입주가능시기")

        for row in rows[1:]:
            cells = [_clean(c) for c in row]
            if not any(cells):
                continue
            label = cells[i_floor] if i_floor is not None and i_floor < len(cells) else ""
            if not label:
                continue
            is_total = label in ("Total", "total", "계", "합계")

            fa = FloorAvailability(
                floor_label=label,
                is_total_row=is_total,
            )
            # 층 번호 파싱 (Total 제외)
            if not is_total:
                fa.floor_number = self._parse_floor_number(label)

            # 오스카 층별표 단위는 '3.3㎡'(평) → default_unit='pyeong'
            if i_excl is not None and i_excl < len(cells):
                fa.exclusive_area_sqm, fa.exclusive_area_pyeong = parse_area(cells[i_excl], default_unit="pyeong")
                fa.area_raw["exclusive"] = cells[i_excl]
            if i_lease is not None and i_lease < len(cells):
                fa.lease_area_sqm, fa.lease_area_pyeong = parse_area(cells[i_lease], default_unit="pyeong")
                fa.area_raw["lease"] = cells[i_lease]
            if i_avail is not None and i_avail < len(cells):
                kind, raw = classify_availability(cells[i_avail])
                fa.availability_kind = kind
                fa.availability_raw = raw if raw and raw != "-" else None

            b.floors.append(fa)

    @staticmethod
    def _parse_floor_number(label: str) -> Optional[int]:
        """'18층' → 18, 'B1' → -1, '지하2층' → -2."""
        import re
        s = label.strip()
        if s.upper().startswith("B"):
            m = re.search(r"\d+", s)
            return -int(m.group()) if m else None
        if "지하" in s:
            m = re.search(r"\d+", s)
            return -int(m.group()) if m else None
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else None

    # ------------------------------------------------------------------
    # 표2: 임대조건 (헤더 + 데이터행, 보증금/임대료/관리비)
    # ------------------------------------------------------------------
    def _parse_rent_table(self, rows: list[list], b: BuildingExtraction) -> None:
        if len(rows) < 2:
            return
        header = [_clean(c) for c in rows[0]]
        col = {name.replace(" ", ""): i for i, name in enumerate(header)}

        def cidx(*names: str) -> Optional[int]:
            for n in names:
                for h, i in col.items():
                    if n in h:
                        return i
            return None

        i_scope = cidx("관련층", "층", "구분")
        i_deposit = cidx("보증금")
        i_rent = cidx("임대료")
        i_maint = cidx("관리비")

        for row in rows[1:]:
            cells = [_clean(c) for c in row]
            if not any(cells):
                continue
            rt = RentTerm()
            if i_scope is not None and i_scope < len(cells):
                rt.scope_label = cells[i_scope] or None
            if i_deposit is not None and i_deposit < len(cells):
                rt.deposit_per_pyeong = parse_korean_money(cells[i_deposit])
                rt.terms_raw["deposit"] = cells[i_deposit]
            if i_rent is not None and i_rent < len(cells):
                rt.rent_per_pyeong = parse_korean_money(cells[i_rent])
                rt.terms_raw["rent"] = cells[i_rent]
            if i_maint is not None and i_maint < len(cells):
                rt.maintenance_per_pyeong = parse_korean_money(cells[i_maint])
                rt.terms_raw["maintenance"] = cells[i_maint]
            b.rents.append(rt)

    # ------------------------------------------------------------------
    def _finalize(self, b: BuildingExtraction) -> None:
        """신뢰도·경고 산정."""
        warnings = []
        if not b.address_raw:
            warnings.append("주소 없음")
        if not b.floors:
            warnings.append("층별 공실 정보 없음")
        if not b.rents:
            warnings.append("임대조건 없음")
        b.warnings = warnings
        # 필수 필드 충족률 기반 신뢰도
        required = [b.building_name, b.address_raw, b.gross_area_sqm]
        filled = sum(1 for v in required if v)
        b.confidence = round(0.6 + 0.4 * (filled / len(required)), 2)
        # 주소 매칭키 + provenance 기록
        from app.adapters.base import finalize_common
        finalize_common(b, source_label="pdf_parse")
