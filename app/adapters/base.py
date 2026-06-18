"""추출 어댑터 추상 기반 클래스.

모든 중개사 어댑터는 ExtractorAdapter를 상속하고 extract()를 구현한다.
PageGroup의 단일 정의는 app/group_buildings.py에 있다 (여기서는 import만).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.schemas import BuildingExtraction

if TYPE_CHECKING:
    import fitz
    from app.group_buildings import PageGroup


class ExtractorAdapter(ABC):
    """중개사별 추출 어댑터 인터페이스.

    각 어댑터는 PageGroup(건물 단위 페이지 묶음)을 받아
    BuildingExtraction(표준 출력 스키마)을 반환한다.
    """

    @abstractmethod
    def extract(
        self,
        doc: "fitz.Document",
        page_group: "PageGroup",
        source_filename: str,
        source_month: str | None = None,
    ) -> BuildingExtraction:
        """페이지 그룹에서 건물 정보를 추출해 BuildingExtraction으로 반환.

        Args:
            doc: 전체 PDF Document (페이지 접근용)
            page_group: 이 건물에 속하는 페이지 인덱스 묶음
            source_filename: 원본 PDF 파일명 (provenance)
            source_month: 발행월 'YYYY-MM' (없으면 None)
        """
        ...


# 물리 스펙 필드 — provenance 추적 대상 (자식 컬렉션/메타 제외)
_PROVENANCE_FIELDS = [
    "address_road", "address_jibun", "district", "station_area",
    "floors_above", "floors_below", "gross_area_sqm", "exclusive_area_sqm",
    "ev_count", "completed_year", "ceiling_height_m", "efficiency_ratio",
    "parking_total", "features_raw", "main_purpose", "building_coverage_ratio",
    "floor_area_ratio", "height_m", "land_area_sqm", "use_zone",
    "latitude", "longitude",
]


def finalize_common(b: BuildingExtraction, source_label: str = "pdf_parse") -> None:
    """모든 어댑터 공통 후처리.

    1. 주소 매칭키 생성 (Entity Resolution 1차 키)
    2. PDF에서 채워진 필드를 field_sources에 'pdf_parse'로 기록
       → 이후 enrich 단계가 빈 필드만 외부 소스로 채우고 출처를 구분.
    """
    from app.normalize import address_match_key

    if b.address_raw and not b.address_match_key:
        b.address_match_key = address_match_key(b.address_raw)

    for f in _PROVENANCE_FIELDS:
        if getattr(b, f, None) not in (None, "", []) and f not in b.field_sources:
            b.field_sources[f] = source_label
