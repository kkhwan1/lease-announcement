"""쿠시먼앤드웨이크필드(C&W) 추출 어댑터.

C&W 안내문 구조:
  - 상세 페이지(FOR LEASE): 건물정보표(8x2, 키-값 2열) + "SPACE AVAILABILITY & RENT"
  - 층별 공실표가 "다음페이지참조"로 분리되어 다음 페이지(16x6 등)에 위치
  → PageGroup의 모든 페이지에서 표를 수집해 결합한다.

단위: 평(3.3㎡) / 원·평. 면적은 normalize.parse_area로 ㎡ 병산.
"""
from __future__ import annotations

import re
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
    if v is None:
        return ""
    return str(v).replace("\n", " ").strip()


def _to_int(s: str) -> Optional[int]:
    m = re.search(r"(\d+)", _clean(s).replace(",", ""))
    return int(m.group(1)) if m else None


class CnWTableAdapter(ExtractorAdapter):
    """C&W 표 기반 추출기 (분리 층별표 결합)."""

    broker = BrokerCode.CW

    def extract(
        self,
        doc: "fitz.Document",
        page_group,
        source_filename: str,
        source_month: str | None = None,
    ) -> BuildingExtraction:
        name_raw = page_group.building_name
        b = BuildingExtraction(
            broker=self.broker,
            source_filename=source_filename,
            source_month=source_month,
            page_range=[i + 1 for i in page_group.page_indices],
            building_name=normalize_building_name(name_raw) or name_raw,
            building_name_raw=name_raw,
            extraction_method="rule_table",
        )

        # C&W는 상세 페이지 헤더(20pt)에 '건물명[전속] 주소'가 한 줄로 있다.
        # group_buildings는 건물명만 분리했으므로, 여기서 주소를 별도로 추출한다.
        self._extract_address(doc, page_group, b)

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
                    self._parse_info_table(rows, b)
                elif kind == "floor_rent":
                    self._parse_floor_rent_table(rows, b)

        self._finalize(b)
        return b

    # ------------------------------------------------------------------
    # 주소 추출 (C&W 헤더 줄에서 '건물명[전속] 주소' → 주소 분리)
    # ------------------------------------------------------------------
    _ADDR_START = re.compile(
        r"(서울(?:특별)?시|경기도?|인천(?:광역)?시|부산(?:광역)?시|대구(?:광역)?시"
        r"|대전(?:광역)?시|광주(?:광역)?시|울산(?:광역)?시|세종(?:특별자치)?시).*"
    )

    def _extract_address(self, doc, page_group, b: BuildingExtraction) -> None:
        from app.normalize import normalize_address, address_match_key

        for idx in page_group.page_indices:
            page = doc[idx]
            try:
                blocks = page.get_text("dict")["blocks"]
            except Exception:
                continue
            for blk in blocks:
                if blk.get("type") != 0:
                    continue
                for ln in blk.get("lines", []):
                    txt = "".join(s.get("text", "") for s in ln.get("spans", [])).strip()
                    m = self._ADDR_START.search(txt)
                    if m:
                        addr = m.group(0).strip()
                        b.address_raw = addr
                        b.address_road = normalize_address(addr)
                        b.address_match_key = address_match_key(addr)
                        return  # 첫 주소만

    @staticmethod
    def _classify_table(rows: list[list]) -> Optional[str]:
        flat = " ".join(_clean(c) for row in rows for c in row)
        header = " ".join(_clean(c) for c in rows[0]) if rows else ""
        # 층별+임대조건 통합표: 헤더에 '층수'/'임대면적'/'입주가능시기'
        if ("임대면적" in header and ("입주" in header or "전용면적" in header)):
            return "floor_rent"
        # 건물정보표: '연면적'/'전용률'/'층수'(키-값 2열)
        if any(k in flat for k in ("연면적", "전용률", "기준층면적", "준공")):
            return "info"
        return None

    def _parse_info_table(self, rows: list[list], b: BuildingExtraction) -> None:
        """8x2 키-값 표."""
        kv: dict[str, str] = {}
        for row in rows:
            cells = [_clean(c) for c in row]
            if len(cells) >= 2 and cells[0]:
                key = cells[0].replace(" ", "")
                val = " ".join(filter(None, cells[1:]))
                if val:
                    kv[key] = val

        def get(*keys: str) -> str:
            for k in keys:
                for kk, vv in kv.items():
                    if k in kk:
                        return vv
            return ""

        if (v := get("연면적")):
            b.gross_area_sqm, b.gross_area_pyeong = parse_area(v)
        if (v := get("기준층면적")):
            # '임대: 1,037.74 평 / 전용: 571.92 평' — 전용면적만 대표값으로
            m = re.search(r"전용[:\s]*([\d,]+(?:\.\d+)?)\s*평", v)
            if m:
                from app.normalize import PYEONG_PER_SQM
                pyeong = float(m.group(1).replace(",", ""))
                b.exclusive_area_pyeong = pyeong
                b.exclusive_area_sqm = round(pyeong / PYEONG_PER_SQM, 2)
        if (v := get("전용률", "전용율")):
            n = re.search(r"([\d.]+)", v)
            if n:
                b.efficiency_ratio = float(n.group(1))
        if (v := get("층수")):
            b.scale_raw = v
            b.floors_above, b.floors_below = parse_scale(v)
        if (v := get("층고")):
            m = re.search(r"천정고\s*([\d.]+)", v) or re.search(r"([\d.]+)\s*m", v)
            if m:
                b.ceiling_height_m = float(m.group(1))
        if (v := get("준공", "준공년도", "준공연도")):
            b.completed_raw = v
            b.completed_year = _to_int(v)
        if (v := get("엘리베이터", "E/V", "EV")):
            b.ev_count = _to_int(v)
        if (v := get("주차")):
            b.parking_terms_raw = v
            b.parking_total = _to_int(v)
        if (v := get("특장점", "특이사항", "PROPERTY")):
            b.features_raw = v

        b.district = classify_district(" ".join(filter(None, [b.address_raw, b.features_raw])))

    def _parse_floor_rent_table(self, rows: list[list], b: BuildingExtraction) -> None:
        """층별 공실 + 임대조건 통합표 (헤더: 층수/임대면적/전용면적/입주가능시기/보증금/임대료/관리비).

        C&W는 보증금 열이 없는 경우도 있음(임대료/관리비만). '다음페이지참조' 행은 skip.
        """
        if len(rows) < 2:
            return
        header = [_clean(c) for c in rows[0]]
        col = {h.replace(" ", ""): i for i, h in enumerate(header)}

        def cidx(*names: str) -> Optional[int]:
            for n in names:
                for h, i in col.items():
                    if n in h:
                        return i
            return None

        i_floor = cidx("층수", "층")
        i_lease = cidx("임대면적")
        i_excl = cidx("전용면적")
        i_avail = cidx("입주가능시기", "입주시기", "입주")
        i_dep = cidx("보증금")
        i_rent = cidx("임대료")
        i_maint = cidx("관리비")

        for row in rows[1:]:
            cells = [_clean(c) for c in row]
            if not any(cells):
                continue
            label = cells[i_floor] if i_floor is not None and i_floor < len(cells) else ""
            if not label or "참조" in label:  # '다음페이지참조' skip
                continue
            is_total = label in ("계", "Total", "합계", "소계")

            fa = FloorAvailability(floor_label=label, is_total_row=is_total)
            if not is_total:
                m = re.search(r"B?(\d+)", label)
                if m:
                    fa.floor_number = -int(m.group(1)) if label.upper().startswith("B") else int(m.group(1))
            # C&W 면적표 단위는 평(3.3㎡) → default_unit='pyeong'
            if i_excl is not None and i_excl < len(cells):
                fa.exclusive_area_sqm, fa.exclusive_area_pyeong = parse_area(cells[i_excl], default_unit="pyeong")
                fa.area_raw["exclusive"] = cells[i_excl]
            if i_lease is not None and i_lease < len(cells):
                fa.lease_area_sqm, fa.lease_area_pyeong = parse_area(cells[i_lease], default_unit="pyeong")
                fa.area_raw["lease"] = cells[i_lease]
            if i_avail is not None and i_avail < len(cells) and cells[i_avail]:
                kind, raw = classify_availability(cells[i_avail])
                fa.availability_kind = kind
                fa.availability_raw = raw if raw and raw != "-" else None
            b.floors.append(fa)

            # 같은 행에 임대조건이 있으면 RentTerm으로
            if any(idx is not None for idx in (i_dep, i_rent, i_maint)):
                rt = RentTerm(scope_label=label)
                if i_dep is not None and i_dep < len(cells):
                    rt.deposit_per_pyeong = parse_korean_money(cells[i_dep])
                    rt.terms_raw["deposit"] = cells[i_dep]
                if i_rent is not None and i_rent < len(cells):
                    rt.rent_per_pyeong = parse_korean_money(cells[i_rent])
                    rt.terms_raw["rent"] = cells[i_rent]
                if i_maint is not None and i_maint < len(cells):
                    rt.maintenance_per_pyeong = parse_korean_money(cells[i_maint])
                    rt.terms_raw["maintenance"] = cells[i_maint]
                if any(v is not None for v in (rt.deposit_per_pyeong, rt.rent_per_pyeong, rt.maintenance_per_pyeong)) \
                        or any(rt.terms_raw.values()):
                    b.rents.append(rt)

    def _finalize(self, b: BuildingExtraction) -> None:
        warnings = []
        if not b.gross_area_sqm:
            warnings.append("연면적 없음")
        if not b.floors:
            warnings.append("층별 공실 정보 없음(분리표 미발견 가능)")
        b.warnings = warnings
        required = [b.building_name, b.gross_area_sqm]
        filled = sum(1 for v in required if v)
        b.confidence = round(0.6 + 0.4 * (filled / len(required)), 2)
        from app.adapters.base import finalize_common
        finalize_common(b, source_label="pdf_parse")
