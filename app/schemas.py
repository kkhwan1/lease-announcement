"""추출 결과의 Pydantic 스키마 — 모든 중개사 어댑터의 공통 출력 계약.

설계 원칙:
- 면적은 ㎡ 정규화(_sqm) + 평 원문(_pyeong) 병존.
- 금액은 원/평(_per_pyeong) 원문 보존 (㎡ 환산은 DB의 generated 컬럼이 담당).
- 필수 필드(building_name)만 strict, 나머지는 Optional — PDF 형식 차이를 흡수.
- 모든 raw 원문을 *_raw 로 보존 (재처리 안전성).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BrokerCode(str, Enum):
    JLL = "JLL"
    CW = "CW"
    S1 = "S1"
    OSCAR = "OSCAR"


class BusinessDistrict(str, Enum):
    GBD = "GBD"  # 강남권
    CBD = "CBD"  # 도심권
    YBD = "YBD"  # 여의도권
    BBD = "BBD"  # 분당/판교권
    ETC = "ETC"


class AvailabilityKind(str, Enum):
    IMMEDIATE = "immediate"      # 즉시
    NEGOTIABLE = "negotiable"    # 협의
    BY_DATE = "by_date"          # 특정일
    UNKNOWN = "unknown"


class ImageKind(str, Enum):
    EXTERIOR = "exterior"          # 외관
    LOCATION_MAP = "location_map"  # 위치도
    FLOOR_PLAN = "floor_plan"      # 평면도
    LOBBY = "lobby"                # 로비
    INTERIOR = "interior"          # 전용부/내부
    OTHER = "other"


class FloorAvailability(BaseModel):
    """층별 공실 (사용자 1순위 데이터). 한 건물에 N개."""
    floor_label: str                            # '18층', 'B1', '기준층' 원문
    floor_number: Optional[int] = None          # 18 (정렬/범위검색, 파싱 가능 시)
    is_total_row: bool = False                  # 'Total'/'계' 행 구분
    exclusive_area_sqm: Optional[float] = None  # 전용면적 ㎡
    exclusive_area_pyeong: Optional[float] = None
    lease_area_sqm: Optional[float] = None      # 임대면적 ㎡
    lease_area_pyeong: Optional[float] = None
    availability_kind: AvailabilityKind = AvailabilityKind.UNKNOWN
    availability_raw: Optional[str] = None       # '즉시', '협의 후 1개월'
    area_raw: dict[str, Any] = Field(default_factory=dict)  # 원본 셀 보존


class RentTerm(BaseModel):
    """임대조건. 단위: 원/평(3.3㎡)."""
    scope_label: Optional[str] = None            # '기준층', '전층', '18층'
    deposit_per_pyeong: Optional[float] = None   # 보증금
    rent_per_pyeong: Optional[float] = None      # 임대료
    maintenance_per_pyeong: Optional[float] = None  # 관리비
    terms_raw: dict[str, Any] = Field(default_factory=dict)


class BuildingImage(BaseModel):
    """추출된 이미지 메타 (바이너리는 별도 파일/Storage)."""
    kind: ImageKind = ImageKind.OTHER
    page_number: int
    bbox: Optional[list[float]] = None           # [x0,y0,x1,y1] PDF 좌표
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    file_path: Optional[str] = None              # 로컬 crop 저장 경로


class BuildingExtraction(BaseModel):
    """한 건물의 전체 추출 결과 — 어댑터 출력의 표준 형태.

    이것이 raw_extractions / buildings / floor_availabilities / rent_terms 로
    승격되는 1차 산출물(JSON)이다.
    """
    # 출처 (provenance 뿌리)
    broker: BrokerCode
    source_filename: str
    source_month: Optional[str] = None           # 'YYYY-MM'
    page_range: list[int] = Field(default_factory=list)  # 이 건물이 걸친 페이지들

    # 건물 식별 (필수: building_name)
    building_name: str
    building_name_raw: Optional[str] = None      # 정규화 전 원문

    # 위치
    address_road: Optional[str] = None           # 도로명
    address_jibun: Optional[str] = None          # 지번
    address_raw: Optional[str] = None
    district: Optional[BusinessDistrict] = None
    station_area: Optional[str] = None           # '강남역'

    # 물리 스펙 (㎡ 정규화 + 평 원문)
    floors_above: Optional[int] = None
    floors_below: Optional[int] = None
    scale_raw: Optional[str] = None              # 'B3 / 20F'
    gross_area_sqm: Optional[float] = None        # 연면적
    gross_area_pyeong: Optional[float] = None
    exclusive_area_sqm: Optional[float] = None    # 대표 전용면적(건물정보표)
    exclusive_area_pyeong: Optional[float] = None
    ev_count: Optional[int] = None
    completed_year: Optional[int] = None
    completed_raw: Optional[str] = None          # '2022년', '1976년(2009년 리모델링)'
    ceiling_height_m: Optional[float] = None
    efficiency_ratio: Optional[float] = None      # 전용률 %
    parking_total: Optional[int] = None
    parking_terms_raw: Optional[str] = None
    features_raw: Optional[str] = None            # 특장점

    # 자식 컬렉션
    floors: list[FloorAvailability] = Field(default_factory=list)
    rents: list[RentTerm] = Field(default_factory=list)
    images: list[BuildingImage] = Field(default_factory=list)

    # 메타
    extraction_method: str = "rule_table"        # rule_table | section_text | vision | ocr
    confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    """PDF 한 건 (멱등 키)."""
    broker: BrokerCode
    filename: str
    file_sha256: str
    source_month: Optional[str] = None
    page_count: int
    buildings: list[BuildingExtraction] = Field(default_factory=list)
