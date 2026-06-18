"""에스원(삼성 S1) 추출 어댑터.

에스원 안내문은 find_tables()로 표가 안 잡히지만, 텍스트가
섹션 헤더로 명확히 구분된다:
  PROPERTY OVERVIEW  — 주소/교통/연면적/빌딩규모/준공연도/전용율/기준층면적/엘리베이터/주차사항/특이사항
  FLOOR PLAN         — (이미지)
  SPACE AVAILABILITY — 층/임대면적/전용면적/입주시기 (4개씩 묶음, '공실없음' 가능)
  RENT               — 층/보증금/임대료/관리비 (4개씩, '담당자문의' 가능)
  CONTACT POINT      — (담당자, 무시)

레이블-값이 줄바꿈으로 교대하는 구조라 줄 단위로 파싱한다.
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

# 섹션 헤더 (대문자)
_SECTIONS = [
    "PROPERTY OVERVIEW",
    "FLOOR PLAN",
    "SPACE AVAILABILITY",
    "RENT",
    "CONTACT POINT",
    "SITE",
]

# PROPERTY OVERVIEW 레이블 → 정규 필드
_OVERVIEW_LABELS = {
    "주소", "교통", "연면적", "빌딩규모", "준공연도", "준공년도",
    "전용율", "전용률", "기준층면적", "엘리베이터", "주차사항", "특이사항",
}


def _to_int(s: str) -> Optional[int]:
    m = re.search(r"(\d+)", (s or "").replace(",", ""))
    return int(m.group(1)) if m else None


class S1OverviewAdapter(ExtractorAdapter):
    """에스원 섹션 텍스트 기반 추출기."""

    broker = BrokerCode.S1

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
            extraction_method="section_text",
        )

        # 그룹의 첫 detail 페이지 텍스트를 섹션별로 분할
        for idx in page_group.page_indices:
            text = doc[idx].get_text()
            if "PROPERTY OVERVIEW" not in text:
                continue
            sections = self._split_sections(text)
            if "PROPERTY OVERVIEW" in sections:
                self._parse_overview(sections["PROPERTY OVERVIEW"], b)
            if "SPACE AVAILABILITY" in sections:
                self._parse_space(sections["SPACE AVAILABILITY"], b)
            if "RENT" in sections:
                self._parse_rent(sections["RENT"], b)
            break  # 상세 페이지 하나만 처리

        self._finalize(b)
        return b

    # ------------------------------------------------------------------
    @staticmethod
    def _split_sections(text: str) -> dict[str, list[str]]:
        """텍스트를 섹션 헤더 기준으로 분할. 반환: {섹션명: [줄,...]}."""
        lines = [ln.strip() for ln in text.split("\n")]
        result: dict[str, list[str]] = {}
        current: Optional[str] = None
        for ln in lines:
            if ln in _SECTIONS:
                current = ln
                result.setdefault(current, [])
                continue
            if current:
                if ln:
                    result[current].append(ln)
        return result

    # ------------------------------------------------------------------
    def _parse_overview(self, lines: list[str], b: BuildingExtraction) -> None:
        """레이블-값이 교대하는 줄을 dict로 모은다.

        일부 값은 여러 줄(주차사항: 총337대 / 무료... / 유료...). 다음 레이블 전까지 누적.
        """
        kv: dict[str, list[str]] = {}
        cur_label: Optional[str] = None
        for ln in lines:
            if ln in _OVERVIEW_LABELS:
                cur_label = ln
                kv.setdefault(cur_label, [])
            elif cur_label:
                kv[cur_label].append(ln)

        def get(*keys: str) -> str:
            for k in keys:
                if k in kv and kv[k]:
                    return " ".join(kv[k])
            return ""

        if (v := get("주소")):
            b.address_raw = v
            b.address_road = v
        station = get("교통")
        if (v := get("연면적")):
            b.gross_area_sqm, b.gross_area_pyeong = parse_area(v)
        if (v := get("빌딩규모")):
            b.scale_raw = v
            b.floors_above, b.floors_below = parse_scale(v)
        if (v := get("준공연도", "준공년도")):
            from app.normalize import parse_completed_year
            b.completed_raw = v
            b.completed_year = parse_completed_year(v)
        if (v := get("전용율", "전용률")):
            n = re.search(r"([\d.]+)", v)
            if n:
                b.efficiency_ratio = float(n.group(1))
        if (v := get("기준층면적")):
            m = re.search(r"전용\s*([\d,]+(?:\.\d+)?)\s*평", v)
            if m:
                from app.normalize import PYEONG_PER_SQM
                pyeong = float(m.group(1).replace(",", ""))
                b.exclusive_area_pyeong = pyeong
                b.exclusive_area_sqm = round(pyeong / PYEONG_PER_SQM, 2)
        if (v := get("엘리베이터")):
            b.ev_count = _to_int(v)
        if (v := get("주차사항")):
            b.parking_terms_raw = v
            b.parking_total = _to_int(v)
        if (v := get("특이사항")):
            b.features_raw = v

        b.station_area = station or None
        b.district = classify_district(" ".join(filter(None, [station, b.address_raw])))

    # ------------------------------------------------------------------
    def _parse_space(self, lines: list[str], b: BuildingExtraction) -> None:
        """SPACE AVAILABILITY: '단위: 3.3㎡' 다음 '층/임대면적/전용면적/입주시기' 헤더,
        이후 4개씩 묶인 데이터. '공실없음'이면 floors 비움 + warning.
        """
        # 헤더 위치 찾기
        joined = " ".join(lines)
        if "공실없음" in joined or "공실 없음" in joined:
            b.warnings.append("공실없음")
            return

        # '층','임대면적','전용면적','입주시기' 헤더 다음부터 데이터
        try:
            h_start = next(
                i for i, ln in enumerate(lines)
                if ln == "층" or ln.startswith("층")
            )
        except StopIteration:
            return

        # 헤더 4개 칸 건너뛰고 데이터 시작
        data = lines[h_start + 4:]
        # 4개씩 묶기: [층, 임대면적, 전용면적, 입주시기]
        for i in range(0, len(data) - 3, 4):
            label, lease, excl, avail = data[i], data[i + 1], data[i + 2], data[i + 3]
            if not label:
                continue
            is_total = label in ("계", "합계", "Total", "소계")
            fa = FloorAvailability(floor_label=label, is_total_row=is_total)
            if not is_total:
                m = re.search(r"B?(\d+)", label)
                if m:
                    fa.floor_number = -int(m.group(1)) if label.upper().startswith("B") else int(m.group(1))
            # 에스원 면적 단위는 '3.3㎡'(평) → default_unit='pyeong'
            fa.lease_area_sqm, fa.lease_area_pyeong = parse_area(lease, default_unit="pyeong")
            fa.exclusive_area_sqm, fa.exclusive_area_pyeong = parse_area(excl, default_unit="pyeong")
            fa.area_raw = {"lease": lease, "exclusive": excl}
            kind, raw = classify_availability(avail)
            fa.availability_kind = kind
            fa.availability_raw = raw if raw and raw != "-" else None
            b.floors.append(fa)

    # ------------------------------------------------------------------
    def _parse_rent(self, lines: list[str], b: BuildingExtraction) -> None:
        """RENT: '층/보증금/임대료/관리비' 헤더, 이후 4개씩.

        단위 판별:
        - '단위: 원/3.3㎡' → 평당 단가 (정상)
        - '단위: 원'        → 총액 (평당 아님). 임대면적으로 나눠 평당 환산 시도.
        합계/통임대/계/소계/Total 행은 평당 단가로 신뢰 불가.
        parse_korean_money가 S1 셀 병합 아티팩트('8,528,000빌' 등)를 이미 제거함.
        """
        # '단위: 원' 이면 총액 형식 (예: 대교타워). '단위: 원/3.3㎡'이면 평당.
        # lines에서 '단위:' 줄을 찾아 판별
        unit_line = next(
            (ln for ln in lines if ln.startswith("단위:")),
            "단위: 원/3.3㎡",  # 기본값: 평당
        )
        # '원/3.3㎡' 또는 '원/평' 포함하면 평당, 아니면 총액
        is_total_unit = not any(kw in unit_line for kw in ("3.3㎡", "/평", "원/평"))

        try:
            h_start = next(
                i for i, ln in enumerate(lines)
                if ln == "층" or (ln.startswith("층") and len(ln) <= 3)
            )
        except StopIteration:
            return

        # 합계/통임대/계/소계/Total 행: 평당 단가로 신뢰 불가
        _SCOPE_TOTAL_LABELS = frozenset(["계", "Total", "합계", "소계", "통임대"])

        # 총액 형식일 때 면적 환산에 사용할 층별 임대면적 매핑 {floor_label: pyeong}
        floor_area: dict[str, float] = {}
        if is_total_unit:
            for fa in b.floors:
                if fa.lease_area_pyeong and fa.floor_label:
                    floor_area[fa.floor_label] = fa.lease_area_pyeong

        data = lines[h_start + 4:]
        for i in range(0, len(data) - 3, 4):
            label, dep, rent, maint = data[i], data[i + 1], data[i + 2], data[i + 3]
            if not label or label in _SECTIONS:
                break
            rt = RentTerm(scope_label=label)
            rt.terms_raw = {"deposit": dep, "rent": rent, "maintenance": maint}

            is_scope_total = label in _SCOPE_TOTAL_LABELS
            if is_scope_total:
                # 합계 행: 총액이라 평당 단가 신뢰 불가 → None 유지, note만 기록
                rt.terms_raw["scope_note"] = "합계행_총액_평당제외"
            elif is_total_unit:
                # 총액 단위(예: 대교타워): 임대면적으로 나눠 평당 환산
                area = floor_area.get(label)
                dep_total = parse_korean_money(dep)
                rent_total = parse_korean_money(rent)
                maint_total = parse_korean_money(maint)
                rt.terms_raw["unit_note"] = "총액단위_면적환산"
                if area:
                    rt.deposit_per_pyeong = round(dep_total / area, 2) if dep_total else None
                    rt.rent_per_pyeong = round(rent_total / area, 2) if rent_total else None
                    rt.maintenance_per_pyeong = round(maint_total / area, 2) if maint_total else None
                # 면적 정보 없으면 평당 None (이상치 방지)
            else:
                dep_val = parse_korean_money(dep)
                rent_val = parse_korean_money(rent)
                maint_val = parse_korean_money(maint)

                # 폴백 휴리스틱: 단위 표기가 '원/3.3㎡'(평당)이어도
                # 임대료 > 5,000,000 또는 보증금 > 5억이면 총액으로 의심.
                # 해당 층 임대면적으로 나눠 정상 범위(임대료 5~50만/평)인지 재확인.
                # 환산 결과가 정상 범위면 총액으로 처리, 아니면 원본 값 그대로.
                _RENT_ANOMALY_THRESHOLD = 5_000_000   # 평당 임대료 이상치 기준
                _DEP_ANOMALY_THRESHOLD = 500_000_000  # 평당 보증금 이상치 기준
                _RENT_NORMAL_MAX = 2_000_000           # 환산 후 정상 최대값 (200만/평)

                is_anomaly = (
                    (rent_val is not None and rent_val > _RENT_ANOMALY_THRESHOLD)
                    or (dep_val is not None and dep_val > _DEP_ANOMALY_THRESHOLD)
                )
                if is_anomaly:
                    # 면적 환산 시도 — 층 label로 면적 매핑
                    area = floor_area.get(label)
                    if not area:
                        # floor_area가 비어있으면(is_total_unit=False 경로) 직접 조회
                        for fa in b.floors:
                            if fa.lease_area_pyeong and fa.floor_label == label:
                                area = fa.lease_area_pyeong
                                break
                    if area and rent_val:
                        converted_rent = rent_val / area
                        if converted_rent <= _RENT_NORMAL_MAX:
                            # 환산 결과가 정상 → 총액이었음
                            rt.deposit_per_pyeong = round(dep_val / area, 2) if dep_val else None
                            rt.rent_per_pyeong = round(converted_rent, 2)
                            rt.maintenance_per_pyeong = round(maint_val / area, 2) if maint_val else None
                            rt.terms_raw["unit_note"] = "단위표기오류_총액환산"
                        else:
                            # 환산해도 이상치 → None 처리 (적재 안 함)
                            rt.terms_raw["unit_note"] = "이상치_환산불가"
                    else:
                        # 면적 없으면 이상치 → None
                        rt.terms_raw["unit_note"] = "이상치_면적없음"
                else:
                    rt.deposit_per_pyeong = dep_val
                    rt.rent_per_pyeong = rent_val
                    rt.maintenance_per_pyeong = maint_val

            b.rents.append(rt)

    # ------------------------------------------------------------------
    def _finalize(self, b: BuildingExtraction) -> None:
        warnings = list(b.warnings)
        if not b.address_raw:
            warnings.append("주소 없음")
        if not b.floors and "공실없음" not in warnings:
            warnings.append("층별 공실 정보 없음")
        b.warnings = warnings
        required = [b.building_name, b.address_raw, b.gross_area_sqm]
        filled = sum(1 for v in required if v)
        b.confidence = round(0.6 + 0.4 * (filled / len(required)), 2)
        from app.adapters.base import finalize_common
        finalize_common(b, source_label="pdf_parse")
