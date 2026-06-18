"""Supabase 적재 진입점 — store_document().

흐름:
  1. source_documents upsert (file_sha256 멱등 키)
  2. 각 building:
     a. raw_extractions upsert (source_document_id × raw_building_name 고유)
     b. resolve_building → building_id 확정
     c. building_aliases upsert (중개사별 호칭 보존)
     d. merge_fields → building_field_values + buildings 마스터 갱신
     e. listing_snapshots upsert (building × broker × month, is_latest 강등은 DB 트리거)
     f. floor_availabilities 삽입 (스냅샷 기준 delete-insert 방식으로 멱등)
     g. rent_terms 삽입 (동일 방식)
     h. building_images upsert (storage_path 고유)
  3. source_documents.parse_status → 'parsed' 갱신

멱등 보장: 같은 PDF(file_sha256)를 2회 실행해도 중복 행 0.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any, Optional

from dotenv import load_dotenv
from supabase import create_client, Client

from app.entity_resolution import resolve_building
from app.merge import merge_fields
from app.schemas import BuildingExtraction, SourceDocument

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase 클라이언트 싱글턴
# ---------------------------------------------------------------------------

_client: Optional[Client] = None


def get_client() -> Client:
    """Supabase 클라이언트 반환 (최초 1회 초기화).

    RLS가 authenticated role만 허용하므로 service_role key를 우선 사용.
    키 이름은 Supabase 공식 명칭(SUPABASE_SERVICE_ROLE_KEY)을 우선하되,
    축약형(SUPABASE_SERVICE_KEY)도 호환. 둘 다 없으면 ANON_KEY fallback(개발용).
    """
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        # service_role key: RLS bypass — 파이프라인 서버 전용
        key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ["SUPABASE_ANON_KEY"]
        )
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _source_month_to_date(source_month: Optional[str]) -> Optional[str]:
    """'YYYY-MM' → 'YYYY-MM-01'."""
    if not source_month:
        return None
    try:
        year, month = source_month.split("-")
        return f"{year}-{month.zfill(2)}-01"
    except ValueError:
        return None


def _get_or_create_broker_id(client: Client, broker_code: str) -> str:
    """brokers 테이블에서 code로 broker_id 조회. 없으면 RuntimeError."""
    result = (
        client.table("brokers")
        .select("id")
        .eq("code", broker_code)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"brokers 테이블에 코드 '{broker_code}' 없음 — 시드 데이터 확인 필요")
    return result.data[0]["id"]


def _upsert_source_document(client: Client, source_doc: SourceDocument, broker_id: str) -> str:
    """source_documents upsert 후 id 반환. file_sha256 멱등."""
    issue_period = _source_month_to_date(source_doc.source_month)
    payload: dict[str, Any] = {
        "broker_id": broker_id,
        "filename": source_doc.filename,
        "file_sha256": source_doc.file_sha256,
        "page_count": source_doc.page_count,
        "parse_status": "parsing",
    }
    if issue_period:
        payload["issue_period"] = issue_period

    result = client.table("source_documents").upsert(
        payload,
        on_conflict="file_sha256",
    ).execute()
    if not result.data:
        raise RuntimeError(f"source_documents upsert 실패: {source_doc.filename}")
    return result.data[0]["id"]


def _upsert_raw_extraction(
    client: Client,
    source_document_id: str,
    b: BuildingExtraction,
) -> str:
    """raw_extractions upsert 후 id 반환. (source_document_id, raw_building_name) 고유.

    raw_payload는 immutable — 같은 (source_document_id, raw_building_name) 재실행 시
    ignore_duplicates=True로 기존 raw 데이터를 덮어쓰지 않는다.
    """
    raw_name = b.building_name_raw or b.building_name

    # 페이지 그룹 id: 'p001-003' 형식 (1-based 페이지 번호)
    if b.page_range:
        page_group_id = f"p{b.page_range[0]:03d}-{b.page_range[-1]:03d}"
    else:
        page_group_id = None

    payload: dict[str, Any] = {
        "source_document_id": source_document_id,
        "raw_building_name": raw_name,
        "page_range": b.page_range or [],
        "extraction_method": b.extraction_method,
        "confidence": b.confidence,
        # BuildingExtraction 전체를 JSON으로 직렬화해 raw_payload에 보존
        "raw_payload": json.loads(b.model_dump_json()),
    }
    if page_group_id:
        payload["page_group_id"] = page_group_id

    # ignore_duplicates=True: raw 원본은 재처리 시에도 덮어쓰지 않음 (immutable)
    result = client.table("raw_extractions").upsert(
        payload,
        on_conflict="source_document_id,raw_building_name",
        ignore_duplicates=True,
    ).execute()

    if result.data:
        return result.data[0]["id"]

    # ignore_duplicates=True 시 data가 비어올 수 있음 → 기존 row 조회
    existing = (
        client.table("raw_extractions")
        .select("id")
        .eq("source_document_id", source_document_id)
        .eq("raw_building_name", raw_name)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise RuntimeError(f"raw_extractions 조회 실패: {b.building_name}")
    return existing.data[0]["id"]


def _upsert_building_alias(
    client: Client,
    building_id: str,
    broker_id: str,
    alias_raw: str,
    alias_normalized: str,
) -> None:
    """building_aliases upsert. (broker_id, alias_normalized) 고유."""
    payload = {
        "building_id": building_id,
        "broker_id": broker_id,
        "alias": alias_raw,
        "alias_normalized": alias_normalized,
    }
    client.table("building_aliases").upsert(
        payload,
        on_conflict="broker_id,alias_normalized",
        ignore_duplicates=True,
    ).execute()


def _upsert_listing_snapshot(
    client: Client,
    building_id: str,
    broker_id: str,
    source_document_id: str,
    raw_extraction_id: str,
    b: BuildingExtraction,
) -> str:
    """listing_snapshots upsert 후 id 반환.

    (building_id, broker_id, snapshot_month) 고유.
    is_latest=true 강등은 DB 트리거(demote_old_latest_snapshot)가 처리.
    """
    snapshot_month = _source_month_to_date(b.source_month)
    if not snapshot_month:
        # source_month 없으면 오늘 월 1일로 fallback
        today = date.today()
        snapshot_month = f"{today.year}-{str(today.month).zfill(2)}-01"

    payload: dict[str, Any] = {
        "building_id": building_id,
        "broker_id": broker_id,
        "source_document_id": source_document_id,
        "snapshot_month": snapshot_month,
        "is_latest": True,
        "district": b.district.value if b.district else None,
        "name_snapshot": b.building_name,
        "raw_extraction_id": raw_extraction_id,
        "extraction_method": b.extraction_method,
        "confidence": b.confidence,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    result = client.table("listing_snapshots").upsert(
        payload,
        on_conflict="building_id,broker_id,snapshot_month",
    ).execute()
    if not result.data:
        raise RuntimeError(f"listing_snapshots upsert 실패: {b.building_name}")
    return result.data[0]["id"]


def _replace_floor_availabilities(
    client: Client,
    listing_snapshot_id: str,
    b: BuildingExtraction,
) -> None:
    """floor_availabilities 멱등 적재.

    기존 스냅샷의 층별 공실은 삭제 후 재삽입 (delete-insert 패턴).
    floor_availabilities.listing_snapshot_id → ON DELETE CASCADE 아니므로 수동 삭제.
    """
    if not b.floors:
        return

    # 기존 행 삭제 (재적재 멱등 보장)
    client.table("floor_availabilities").delete().eq(
        "listing_snapshot_id", listing_snapshot_id
    ).execute()

    rows = []
    for floor in b.floors:
        row: dict[str, Any] = {
            "listing_snapshot_id": listing_snapshot_id,
            "floor_label": floor.floor_label,
            "is_total_row": floor.is_total_row,
            "availability_kind": floor.availability_kind.value,
            "area_raw": floor.area_raw or {},
        }
        if floor.floor_number is not None:
            row["floor_number"] = floor.floor_number
        if floor.exclusive_area_sqm is not None:
            row["exclusive_area_sqm"] = floor.exclusive_area_sqm
        if floor.exclusive_area_pyeong is not None:
            row["exclusive_area_pyeong"] = floor.exclusive_area_pyeong
        if floor.lease_area_sqm is not None:
            row["lease_area_sqm"] = floor.lease_area_sqm
        if floor.lease_area_pyeong is not None:
            row["lease_area_pyeong"] = floor.lease_area_pyeong
        if floor.availability_raw:
            row["availability_raw"] = floor.availability_raw
        rows.append(row)

    if rows:
        client.table("floor_availabilities").insert(rows).execute()
        logger.debug(
            "listing_snapshot_id=%s: floor_availabilities %d행 삽입",
            listing_snapshot_id, len(rows),
        )


def _replace_rent_terms(
    client: Client,
    listing_snapshot_id: str,
    b: BuildingExtraction,
) -> None:
    """rent_terms 멱등 적재 (delete-insert 패턴)."""
    if not b.rents:
        return

    # 기존 행 삭제
    client.table("rent_terms").delete().eq(
        "listing_snapshot_id", listing_snapshot_id
    ).execute()

    rows = []
    for rent in b.rents:
        row: dict[str, Any] = {
            "listing_snapshot_id": listing_snapshot_id,
            "terms_raw": rent.terms_raw or {},
        }
        if rent.scope_label:
            row["scope_label"] = rent.scope_label
        if rent.deposit_per_pyeong is not None:
            row["deposit_per_pyeong"] = rent.deposit_per_pyeong
        if rent.rent_per_pyeong is not None:
            row["rent_per_pyeong"] = rent.rent_per_pyeong
        if rent.maintenance_per_pyeong is not None:
            row["maintenance_per_pyeong"] = rent.maintenance_per_pyeong
        # *_per_sqm는 DB generated 컬럼이므로 직접 삽입 안 함
        rows.append(row)

    if rows:
        client.table("rent_terms").insert(rows).execute()
        logger.debug(
            "listing_snapshot_id=%s: rent_terms %d행 삽입",
            listing_snapshot_id, len(rows),
        )


_BUCKET_NAME = "building-images"


def _ensure_bucket(client: Client) -> None:
    """'building-images' 버킷이 없으면 private 버킷으로 생성.

    멱등 — 이미 존재하면 아무것도 하지 않는다.
    """
    try:
        buckets = client.storage.list_buckets()
        existing = {b.name for b in buckets}
        if _BUCKET_NAME not in existing:
            client.storage.create_bucket(_BUCKET_NAME, options={"public": False})
            logger.info("Storage 버킷 생성: %s (private)", _BUCKET_NAME)
        else:
            logger.debug("Storage 버킷 이미 존재: %s", _BUCKET_NAME)
    except Exception as exc:
        # 버킷 생성 실패는 경고만 — 이미 존재할 경우 409가 오기도 함
        logger.warning("버킷 확인/생성 실패 (이미 있으면 무시): %s", exc)


def _upload_image_to_storage(
    client: Client,
    storage_path: str,
    local_file_path: str,
) -> bool:
    """로컬 PNG 파일을 Supabase Storage에 업로드.

    Args:
        storage_path: Storage 내 경로 (버킷 이름 제외)
        local_file_path: 로컬 crop PNG 절대경로

    Returns:
        True = 업로드 성공, False = 실패(경고 로깅)
    """
    from pathlib import Path as _Path

    local_path = _Path(local_file_path)
    if not local_path.exists():
        logger.warning("이미지 파일 없음 (업로드 건너뜀): %s", local_file_path)
        return False

    try:
        with open(local_path, "rb") as f:
            data = f.read()
        # upsert=True: 동일 경로 재실행 시 덮어씀 (멱등)
        client.storage.from_(_BUCKET_NAME).upload(
            path=storage_path,
            file=data,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
        logger.debug("Storage 업로드 완료: %s/%s", _BUCKET_NAME, storage_path)
        return True
    except Exception as exc:
        logger.warning("Storage 업로드 실패 (%s): %s", storage_path, exc)
        return False


def _upsert_building_images(
    client: Client,
    building_id: str,
    source_document_id: str,
    b: BuildingExtraction,
) -> None:
    """building_images upsert. storage_path 고유키.

    흐름:
      1) 버킷 존재 확인/생성 (최초 1회)
      2) 이미지별로 Storage 업로드 (로컬 file_path → Storage)
      3) building_images 테이블에 메타 upsert (storage_path 멱등)
    """
    if not b.images:
        return

    # 버킷이 없으면 생성 (멱등)
    _ensure_bucket(client)

    broker_code = b.broker.value
    period = (b.source_month or "unknown").replace("-", "")

    rows = []
    upload_ok = 0
    upload_skip = 0

    for img_idx, img in enumerate(b.images):
        # storage_path 규약: {broker}/{period}/{building_id}/{kind}_p{page}_{idx}.png
        # idx를 붙여 같은 페이지에 동종 이미지가 여럿 있어도 경로 충돌 방지
        storage_path = (
            f"{broker_code}/{period}/{building_id}"
            f"/{img.kind.value}_p{str(img.page_number).zfill(3)}_{img_idx:02d}.png"
        )

        # Storage 업로드 (file_path가 있는 경우만 — pipeline이 임시 dir에 저장한 PNG)
        if img.file_path:
            success = _upload_image_to_storage(client, storage_path, img.file_path)
            if success:
                upload_ok += 1
            else:
                upload_skip += 1
        else:
            # file_path 없음 = 메타만 저장 (Storage 업로드 생략)
            upload_skip += 1

        row: dict[str, Any] = {
            "building_id": building_id,
            "source_document_id": source_document_id,
            "storage_path": storage_path,
            "kind": img.kind.value,
            "page_number": img.page_number,
            "is_verified": False,
        }
        if img.bbox:
            row["bbox"] = img.bbox
        if img.width_px is not None:
            row["width_px"] = img.width_px
        if img.height_px is not None:
            row["height_px"] = img.height_px
        # file_path는 building_images 스키마 컬럼 없음 — Storage 경로는 storage_path로만 관리
        rows.append(row)

    if rows:
        client.table("building_images").upsert(
            rows,
            on_conflict="storage_path",
            ignore_duplicates=True,
        ).execute()
        logger.info(
            "building_id=%s: building_images %d행 upsert (Storage 업로드 성공=%d, 건너뜀=%d)",
            building_id, len(rows), upload_ok, upload_skip,
        )


def _mark_source_document_parsed(
    client: Client,
    source_document_id: str,
    has_error: bool = False,
) -> None:
    """source_documents.parse_status 갱신."""
    import datetime as dt
    status = "partial" if has_error else "parsed"
    client.table("source_documents").update({
        "parse_status": status,
        "parsed_at": dt.datetime.utcnow().isoformat(),
    }).eq("id", source_document_id).execute()


def _promote_raw_extraction(
    client: Client,
    raw_extraction_id: str,
    building_id: str,
) -> None:
    """raw_extractions.promoted_building_id + promoted_at 갱신."""
    import datetime as dt
    client.table("raw_extractions").update({
        "promoted_building_id": building_id,
        "promoted_at": dt.datetime.utcnow().isoformat(),
    }).eq("id", raw_extraction_id).execute()


def _get_or_create_enrich_source_doc(
    client: Client,
    broker_id: str,
    source_month: Optional[str],
) -> Optional[str]:
    """보강(enrich) 전용 가상 source_documents 행 id 반환.

    건축물대장 API 등 보강값을 building_field_values에 PDF와 분리해 저장하기
    위해 "가상 문서" 1건을 month 단위로 생성(또는 조회)한다.
    file_sha256 = 'enrich:{broker_id}:{YYYY-MM}' 으로 멱등 보장.

    broker_id가 None이면 None 반환 (enrich 행을 PDF 행에 합산).
    """
    issue_period = _source_month_to_date(source_month)
    month_label = source_month or "unknown"
    # 멱등 키: broker × month 고정 문자열 (SHA256 컬럼에 저장)
    virtual_sha = f"enrich:{broker_id}:{month_label}"

    result = (
        client.table("source_documents")
        .select("id")
        .eq("file_sha256", virtual_sha)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]

    # 없으면 생성
    payload: dict[str, Any] = {
        "broker_id": broker_id,
        "filename": f"[enrich] building_register {month_label}",
        "file_sha256": virtual_sha,
        "page_count": 0,
        "parse_status": "parsed",
    }
    if issue_period:
        payload["issue_period"] = issue_period

    ins = client.table("source_documents").insert(payload).execute()
    if not ins.data:
        logger.warning("enrich 가상 source_document 생성 실패 — enrich 필드는 PDF 행에 합산")
        return None
    enrich_doc_id = ins.data[0]["id"]
    logger.debug("enrich 가상 source_document 생성: id=%s (%s)", enrich_doc_id, virtual_sha)
    return enrich_doc_id


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def store_document(
    source_doc: SourceDocument,
    enriched_buildings: list[BuildingExtraction],
    client: Optional[Client] = None,
) -> dict[str, Any]:
    """PDF 1건 전체를 Supabase에 적재.

    Args:
        source_doc: PDF 메타 (broker, filename, file_sha256, ...)
        enriched_buildings: 추출+보강된 건물 목록
        client: 테스트에서 mock 주입 용. None이면 환경변수로 초기화.

    Returns:
        적재 결과 요약 dict {
            'source_document_id': str,
            'buildings_processed': int,
            'buildings_new': int,        # 신규 삽입
            'buildings_matched': int,    # ER 기존 매칭 (주소키/건물명)
            'buildings_queued': int,     # merge_candidates 큐 등록
            'errors': list[str],
        }
    """
    if client is None:
        client = get_client()

    errors: list[str] = []
    buildings_new = 0
    buildings_matched = 0
    buildings_queued = 0

    # ── step 1: broker_id 조회 ──────────────────────────────────────────────
    broker_code = source_doc.broker.value
    broker_id = _get_or_create_broker_id(client, broker_code)

    # ── step 2: source_documents upsert ────────────────────────────────────
    source_document_id = _upsert_source_document(client, source_doc, broker_id)
    logger.info(
        "source_document 적재: id=%s, file=%s", source_document_id, source_doc.filename
    )

    # ── step 3: 건물별 처리 ────────────────────────────────────────────────
    for b in enriched_buildings:
        try:
            er_status = _store_single_building(
                client=client,
                b=b,
                broker_id=broker_id,
                source_document_id=source_document_id,
            )
            # ER 상태별 카운터 집계
            if er_status == "new":
                buildings_new += 1
            elif er_status in ("matched_address", "matched_name"):
                buildings_matched += 1
            elif er_status == "queued":
                buildings_queued += 1
        except Exception as exc:
            msg = f"건물 '{b.building_name}' 적재 실패: {exc}"
            logger.exception(msg)
            errors.append(msg)

    # ── step 4: parse_status 갱신 ──────────────────────────────────────────
    _mark_source_document_parsed(client, source_document_id, has_error=bool(errors))

    logger.info(
        "store_document 완료: source_document_id=%s, 건물=%d건(신규=%d, 매칭=%d, 큐=%d), 오류=%d건",
        source_document_id, len(enriched_buildings),
        buildings_new, buildings_matched, buildings_queued, len(errors),
    )
    return {
        "source_document_id": source_document_id,
        "buildings_processed": len(enriched_buildings),
        "buildings_new": buildings_new,
        "buildings_matched": buildings_matched,
        "buildings_queued": buildings_queued,
        "errors": errors,
    }


def _store_single_building(
    client: Client,
    b: BuildingExtraction,
    broker_id: str,
    source_document_id: str,
) -> str:
    """건물 1채 전체 적재 흐름.

    Returns:
        er_status: 'new' | 'matched_address' | 'matched_name' | 'queued'
    """
    from app.normalize import building_match_key as bmk

    # a. raw_extractions upsert (가공 전 보존)
    raw_extraction_id = _upsert_raw_extraction(client, source_document_id, b)

    # b. Entity Resolution → building_id 확정
    building_id, is_new, status = resolve_building(
        client=client,
        b=b,
        source_document_id=source_document_id,
    )
    logger.info(
        "건물 '%s': status=%s, building_id=%s, is_new=%s",
        b.building_name, status, building_id, is_new,
    )

    # c. raw_extractions.promoted_building_id 갱신
    _promote_raw_extraction(client, raw_extraction_id, building_id)

    # d. building_aliases upsert (중개사별 호칭 보존)
    alias_raw = b.building_name_raw or b.building_name
    alias_normalized = bmk(alias_raw)
    if alias_normalized:
        _upsert_building_alias(client, building_id, broker_id, alias_raw, alias_normalized)

    # e. merge_fields → building_field_values + buildings 마스터 갱신
    # 보강 필드가 있으면 enrich 전용 가상 source_document 생성 (PDF 행과 분리)
    has_enrich_fields = any(
        src != "pdf_parse"
        for src in b.field_sources.values()
    )
    enrich_source_document_id: Optional[str] = None
    if has_enrich_fields:
        enrich_source_document_id = _get_or_create_enrich_source_doc(
            client, broker_id, b.source_month
        )

    merge_fields(
        client=client,
        building_id=building_id,
        b=b,
        pdf_source_document_id=source_document_id,
        broker_id=broker_id,
        enrich_source_document_id=enrich_source_document_id,
    )

    # f. listing_snapshots upsert
    listing_snapshot_id = _upsert_listing_snapshot(
        client=client,
        building_id=building_id,
        broker_id=broker_id,
        source_document_id=source_document_id,
        raw_extraction_id=raw_extraction_id,
        b=b,
    )

    # g. floor_availabilities (delete-insert 멱등)
    _replace_floor_availabilities(client, listing_snapshot_id, b)

    # h. rent_terms (delete-insert 멱등)
    _replace_rent_terms(client, listing_snapshot_id, b)

    # i. building_images upsert
    _upsert_building_images(client, building_id, source_document_id, b)

    # ER 상태를 호출자(store_document)에 반환 — 카운터 집계용
    return status
