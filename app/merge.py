"""필드 단위 출처 병합 — building_field_values upsert + buildings 마스터 갱신.

설계 원칙:
- 같은 (building_id, field_name, source_document_id) 조합은 멱등 upsert.
- 빈 필드(None/빈 문자열)는 건너뜀.
- buildings 마스터는 "완전성 우선" 방식으로 갱신:
    * NULL 컬럼 → 값 있으면 무조건 채움.
    * 기존 값 있어도 → 출처가 'building_register'이면 덮어씀 (건축물대장이 더 신뢰).
- field_sources 딕셔너리에 기록된 출처 유형을 notes에 저장.
  출처 우선순위(높음→낮음): building_register > pdf_parse > manual > 기타.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)

# buildings 테이블에 직접 존재하는 컬럼명 목록 (field_values에서 마스터 갱신 대상)
_BUILDING_DIRECT_COLS = frozenset({
    "name",
    "name_raw",
    "address_road",
    "address_jibun",
    "address_raw",
    "district",
    "station_area",
    "floors_above",
    "floors_below",
    "scale_raw",
    "gross_area_sqm",
    "gross_area_pyeong",
    "exclusive_area_sqm",
    "exclusive_area_pyeong",
    "ev_count",
    "completed_year",
    "completed_raw",
    "ceiling_height_m",
    "efficiency_ratio",
    "parking_total",
    "parking_terms_raw",
    "features_raw",
})


def _to_str(val: Any) -> Optional[str]:
    """DB field_value(text) 직렬화. None/빈 값은 None 반환."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _source_month_to_date(source_month: Optional[str]) -> Optional[str]:
    """'YYYY-MM' → 'YYYY-MM-01' (DB date 타입)."""
    if not source_month:
        return None
    try:
        year, month = source_month.split("-")
        return f"{year}-{month.zfill(2)}-01"
    except ValueError:
        return None


def merge_fields(
    client,  # supabase.Client
    building_id: str,
    b: BuildingExtraction,
    source_document_id: str,
    broker_id: str,
) -> None:
    """BuildingExtraction의 필드별 값을 building_field_values에 upsert.

    - 같은 (building_id, field_name, source_document_id) → 멱등 upsert
    - 빈 필드 건너뜀
    - upsert 완료 후 buildings 마스터도 갱신
    """
    source_month_date = _source_month_to_date(b.source_month)

    # 적재 대상 필드 목록 (스키마 필드 → DB 컬럼명 1:1 매핑)
    field_map: dict[str, Any] = {
        "name": b.building_name,
        "name_raw": b.building_name_raw,
        "address_road": b.address_road,
        "address_jibun": b.address_jibun,
        "address_raw": b.address_raw,
        "district": b.district.value if b.district else None,
        "station_area": b.station_area,
        "floors_above": b.floors_above,
        "floors_below": b.floors_below,
        "scale_raw": b.scale_raw,
        "gross_area_sqm": b.gross_area_sqm,
        "gross_area_pyeong": b.gross_area_pyeong,
        "exclusive_area_sqm": b.exclusive_area_sqm,
        "exclusive_area_pyeong": b.exclusive_area_pyeong,
        "ev_count": b.ev_count,
        "completed_year": b.completed_year,
        "completed_raw": b.completed_raw,
        "ceiling_height_m": b.ceiling_height_m,
        "efficiency_ratio": b.efficiency_ratio,
        "parking_total": b.parking_total,
        "parking_terms_raw": b.parking_terms_raw,
        "features_raw": b.features_raw,
        # 건축물대장 보강 필드
        "main_purpose": b.main_purpose,
        "building_coverage_ratio": b.building_coverage_ratio,
        "floor_area_ratio": b.floor_area_ratio,
        "height_m": b.height_m,
        "land_area_sqm": b.land_area_sqm,
        "use_zone": b.use_zone,
    }

    rows_to_upsert = []
    for field_name, raw_val in field_map.items():
        str_val = _to_str(raw_val)
        if str_val is None:
            continue  # 빈 필드 건너뜀

        # field_sources에 기록된 출처 유형 (없으면 'pdf_parse')
        source_type = b.field_sources.get(field_name, "pdf_parse")

        row: dict[str, Any] = {
            "building_id": building_id,
            "field_name": field_name,
            "value": str_val,
            "source_document_id": source_document_id,
            "broker_id": broker_id,
            "confidence": b.confidence,
            "is_active": True,
            "notes": source_type,
        }
        if source_month_date:
            row["source_month"] = source_month_date

        rows_to_upsert.append(row)

    if not rows_to_upsert:
        logger.debug("building_id=%s: 적재할 필드 없음", building_id)
        return

    # 멱등 upsert: (building_id, field_name, source_document_id) 고유 인덱스 활용
    client.table("building_field_values").upsert(
        rows_to_upsert,
        on_conflict="building_id,field_name,source_document_id",
    ).execute()
    logger.debug(
        "building_id=%s: %d개 필드 upsert 완료", building_id, len(rows_to_upsert)
    )

    # buildings 마스터 갱신: 이번 건의 값을 직접 컬럼에도 반영
    _update_building_master(client, building_id, field_map, b)


def _update_building_master(
    client,
    building_id: str,
    field_map: dict[str, Any],
    b: BuildingExtraction,
) -> None:
    """buildings 테이블의 직접 컬럼을 "완전성 우선" 방식으로 갱신.

    갱신 기준:
    - NULL 컬럼 → 값이 있으면 무조건 채움 (완전성).
    - 기존 값 있어도 → field_sources가 'building_register'인 필드는 덮어씀.
      (건축물대장은 관공서 공식 데이터로 PDF보다 신뢰도 높음.)
    - 그 외 기존 값 있는 필드는 보존 (다른 PDF/출처 값 보호).
    """
    # 현재 buildings 행 조회
    result = (
        client.table("buildings")
        .select("*")
        .eq("id", building_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        logger.warning("buildings 마스터 갱신 실패: id=%s 없음", building_id)
        return

    current = result.data[0]
    update_payload: dict[str, Any] = {}

    for col in _BUILDING_DIRECT_COLS:
        new_val = field_map.get(col)
        if new_val is None:
            continue
        # district는 enum 값(str)으로 변환
        if col == "district" and hasattr(new_val, "value"):
            new_val = new_val.value

        existing_val = current.get(col)
        source_type = b.field_sources.get(col, "pdf_parse")

        # 갱신 조건:
        #   1) 기존 값 없음 (NULL) → 무조건 채움
        #   2) building_register 출처 → 기존 값 있어도 덮어씀
        if existing_val is None or source_type == "building_register":
            update_payload[col] = new_val

    if update_payload:
        client.table("buildings").update(update_payload).eq("id", building_id).execute()
        logger.debug(
            "buildings 마스터 갱신: id=%s, 필드=%s",
            building_id, list(update_payload.keys()),
        )
