"""필드 단위 출처 병합 — building_field_values upsert + buildings 마스터 갱신.

설계 원칙:
- 같은 (building_id, field_name, source_document_id) 조합이 unique key.
- PDF 추출 필드(pdf_parse)와 보강 필드(building_register 등)는
  각기 다른 source_document_id를 사용해 별도 행으로 공존시킨다:
    * PDF 필드 → pdf_source_document_id (실제 PDF source_documents 행)
    * 보강 필드 → enrich_source_document_id (가상 enrich source_documents 행)
- 우선순위: PDF 먼저 채운 값은 보강이 덮지 않음 (Enricher._set_field 정책).
  "빈 필드만 보강" 원칙이므로 buildings 마스터는 NULL 컬럼만 채우면 됨.
- 빈 필드(None/빈 문자열)는 건너뜀.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)

# PDF 추출 기본 출처 레이블
_SOURCE_PDF = "pdf_parse"

# buildings 테이블에 직접 존재하는 컬럼명 목록 (field_values → 마스터 갱신 대상)
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
    # 건축물대장/지오코딩 보강 필드 (0019 마이그레이션으로 추가)
    "main_purpose",
    "building_coverage_ratio",
    "floor_area_ratio",
    "height_m",
    "land_area_sqm",
    "use_zone",
    "latitude",
    "longitude",
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


def _build_field_map(b: BuildingExtraction) -> dict[str, Any]:
    """BuildingExtraction에서 DB 컬럼명→값 매핑 생성."""
    return {
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
        # 건축물대장/지오코딩 보강 필드
        "main_purpose": b.main_purpose,
        "building_coverage_ratio": b.building_coverage_ratio,
        "floor_area_ratio": b.floor_area_ratio,
        "height_m": b.height_m,
        "land_area_sqm": b.land_area_sqm,
        "use_zone": b.use_zone,
        "latitude": b.latitude,
        "longitude": b.longitude,
    }


def merge_fields(
    client,  # supabase.Client
    building_id: str,
    b: BuildingExtraction,
    pdf_source_document_id: str,
    broker_id: str,
    enrich_source_document_id: Optional[str] = None,
) -> None:
    """BuildingExtraction의 필드별 값을 building_field_values에 출처별로 upsert.

    PDF 필드와 보강 필드를 별도 source_document_id로 분리해 각각 행을 생성:
    - pdf_parse 출처 → pdf_source_document_id 행
    - building_register 등 보강 출처 → enrich_source_document_id 행
      (enrich_source_document_id=None이면 보강 필드는 PDF 행에 합산)

    upsert 키: (building_id, field_name, source_document_id) → 멱등 보장.
    완료 후 buildings 마스터의 NULL 컬럼도 채움.
    """
    source_month_date = _source_month_to_date(b.source_month)
    field_map = _build_field_map(b)

    # 필드를 출처 유형별로 분류
    pdf_rows: list[dict[str, Any]] = []
    enrich_rows: list[dict[str, Any]] = []

    for field_name, raw_val in field_map.items():
        str_val = _to_str(raw_val)
        if str_val is None:
            continue  # 빈 필드 건너뜀

        source_type = b.field_sources.get(field_name, _SOURCE_PDF)

        row: dict[str, Any] = {
            "building_id": building_id,
            "field_name": field_name,
            "value": str_val,
            "broker_id": broker_id,
            "confidence": b.confidence,
            "is_active": True,
            "notes": source_type,  # 출처 유형 기록 (조회 편의)
        }
        if source_month_date:
            row["source_month"] = source_month_date

        if source_type == _SOURCE_PDF:
            row["source_document_id"] = pdf_source_document_id
            pdf_rows.append(row)
        else:
            # building_register / geocoding 등 보강 출처
            if enrich_source_document_id:
                row["source_document_id"] = enrich_source_document_id
                enrich_rows.append(row)
            else:
                # enrich source 없으면 PDF 행에 함께 적재 (fallback)
                row["source_document_id"] = pdf_source_document_id
                pdf_rows.append(row)

    # PDF 출처 행 upsert
    if pdf_rows:
        client.table("building_field_values").upsert(
            pdf_rows,
            on_conflict="building_id,field_name,source_document_id",
        ).execute()
        logger.debug(
            "building_id=%s: pdf_parse 필드 %d개 upsert", building_id, len(pdf_rows)
        )

    # 보강 출처 행 upsert (enrich_source_document_id 있을 때만)
    if enrich_rows:
        enrich_source_labels = {r["notes"] for r in enrich_rows}
        client.table("building_field_values").upsert(
            enrich_rows,
            on_conflict="building_id,field_name,source_document_id",
        ).execute()
        logger.debug(
            "building_id=%s: enrich 필드 %d개 upsert (출처=%s)",
            building_id, len(enrich_rows), enrich_source_labels,
        )

    # buildings 마스터 갱신 (NULL 컬럼만 채움)
    _update_building_master(client, building_id, field_map)


def _update_building_master(
    client,
    building_id: str,
    field_map: dict[str, Any],
) -> None:
    """buildings 테이블의 NULL 컬럼을 이번 추출/보강값으로 채움.

    원칙: 기존 값 있는 컬럼은 건드리지 않음.
    PDF와 enrich 모두 "빈 곳 채우기"라 충돌 없음 — Enricher._set_field가
    이미 PDF 값 있는 필드는 건드리지 않으므로 여기서는 단순 NULL 체크만 한다.
    """
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
        # district는 enum 객체일 수 있음 → .value 추출
        if col == "district" and hasattr(new_val, "value"):
            new_val = new_val.value
        # NULL 컬럼만 채움 (PDF/API 출처 무관하게 동일 원칙)
        if current.get(col) is None:
            update_payload[col] = new_val

    if update_payload:
        client.table("buildings").update(update_payload).eq("id", building_id).execute()
        logger.debug(
            "buildings 마스터 갱신: id=%s, 필드=%s",
            building_id, list(update_payload.keys()),
        )
