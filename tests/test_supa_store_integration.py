"""통합 검증: store_document 적재 + 멱등 + Entity Resolution.

실행:
  .venv/bin/python tests/test_supa_store_integration.py

검증 시나리오:
  1. 케이스퀘어 강남 II 1건 적재 → buildings 1행, field_values 다수행, floor_availabilities 2행
  2. 같은 건 2회 적재 → 중복 0
  3. 다른 중개사(CW) 같은 주소 건물 적재 → buildings 1행 유지, field_values 출처 2건 확인
"""
from __future__ import annotations

import hashlib
import sys
import os

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.schemas import (
    BrokerCode, BuildingExtraction, BusinessDistrict, AvailabilityKind,
    FloorAvailability, RentTerm, SourceDocument,
)
from app.supa_store import get_client, store_document


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_casesquare_oscar() -> tuple[SourceDocument, list[BuildingExtraction]]:
    """케이스퀘어 강남 II — OSCAR 중개사 추출 결과."""
    b = BuildingExtraction(
        broker=BrokerCode.OSCAR,
        source_filename="OSCAR_2026-06.pdf",
        source_month="2026-06",
        page_range=[3, 4],
        building_name="케이스퀘어 강남 II",
        building_name_raw="케이스퀘어 강남 II",
        address_road="서울특별시 강남구 강남대로 374",
        address_raw="서울 강남구 강남대로 374",
        address_match_key="강남대로374",
        district=BusinessDistrict.GBD,
        station_area="강남역",
        floors_above=20,
        floors_below=3,
        scale_raw="B3 / 20F",
        gross_area_sqm=28000.0,
        gross_area_pyeong=8470.0,
        exclusive_area_sqm=15400.0,
        completed_year=2010,
        efficiency_ratio=55.0,
        parking_total=280,
        floors=[
            FloorAvailability(
                floor_label="18층",
                floor_number=18,
                exclusive_area_sqm=628.33,
                exclusive_area_pyeong=190.07,
                availability_kind=AvailabilityKind.IMMEDIATE,
                availability_raw="즉시",
                area_raw={"전용": "628.33㎡", "입주": "즉시"},
            ),
            FloorAvailability(
                floor_label="Total",
                is_total_row=True,
                exclusive_area_sqm=628.33,
                exclusive_area_pyeong=190.07,
                availability_kind=AvailabilityKind.UNKNOWN,
                area_raw={"전용": "628.33㎡"},
            ),
        ],
        rents=[
            RentTerm(
                scope_label="기준층",
                deposit_per_pyeong=2000000.0,
                rent_per_pyeong=90000.0,
                maintenance_per_pyeong=35000.0,
                terms_raw={"보증금": "200만원/평", "임대료": "9만원/평"},
            )
        ],
        extraction_method="rule_table",
        confidence=0.95,
        field_sources={
            "gross_area_sqm": "pdf_parse",
            "floors_above": "pdf_parse",
            "completed_year": "pdf_parse",
        },
    )
    sha = hashlib.sha256(b"OSCAR_2026-06_test_v1").hexdigest()
    doc = SourceDocument(
        broker=BrokerCode.OSCAR,
        filename="OSCAR_2026-06.pdf",
        file_sha256=sha,
        source_month="2026-06",
        page_count=10,
    )
    return doc, [b]


def _make_casesquare_cnw() -> tuple[SourceDocument, list[BuildingExtraction]]:
    """케이스퀘어 강남 II — CW 중개사 추출 결과 (같은 주소, 다른 건물명 표기)."""
    b = BuildingExtraction(
        broker=BrokerCode.CW,
        source_filename="CW_2026-06.pdf",
        source_month="2026-06",
        page_range=[5],
        building_name="케이스퀘어강남2",  # 다른 표기
        building_name_raw="케이스퀘어강남2",
        address_road="서울특별시 강남구 강남대로 374",
        address_raw="강남대로 374",
        address_match_key="강남대로374",  # 동일 주소 매칭키 → 같은 building
        district=BusinessDistrict.GBD,
        floors_above=20,
        floors_below=3,
        gross_area_sqm=28100.0,  # 소수점 차이 허용
        floors=[
            FloorAvailability(
                floor_label="18F",
                floor_number=18,
                exclusive_area_sqm=628.0,
                availability_kind=AvailabilityKind.IMMEDIATE,
                availability_raw="즉시입주",
                area_raw={"전용": "628㎡"},
            ),
        ],
        rents=[
            RentTerm(
                scope_label="전층",
                deposit_per_pyeong=1900000.0,
                rent_per_pyeong=88000.0,
                terms_raw={"보증금": "190만/평"},
            )
        ],
        extraction_method="rule_table",
        confidence=0.90,
        field_sources={"gross_area_sqm": "pdf_parse"},
    )
    sha = hashlib.sha256(b"CW_2026-06_test_v1").hexdigest()
    doc = SourceDocument(
        broker=BrokerCode.CW,
        filename="CW_2026-06.pdf",
        file_sha256=sha,
        source_month="2026-06",
        page_count=8,
    )
    return doc, [b]


# ---------------------------------------------------------------------------
# 검증 헬퍼
# ---------------------------------------------------------------------------

def _count(client, table: str, **filters) -> int:
    q = client.table(table).select("id", count="exact")
    for col, val in filters.items():
        q = q.eq(col, val)
    r = q.execute()
    return r.count or 0


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"  FAIL: {msg}")
        sys.exit(1)
    print(f"  OK  : {msg}")


# ---------------------------------------------------------------------------
# 테스트 실행
# ---------------------------------------------------------------------------

def run_tests():
    client = get_client()
    oscar_doc, oscar_buildings = _make_casesquare_oscar()
    cnw_doc, cnw_buildings = _make_casesquare_cnw()

    # ── 사전 정리: 테스트 SHA로 기존 데이터 삭제 ────────────────────────
    print("\n[사전 정리] 기존 테스트 데이터 삭제...")
    for sha in (oscar_doc.file_sha256, cnw_doc.file_sha256):
        existing = (
            client.table("source_documents")
            .select("id")
            .eq("file_sha256", sha)
            .execute()
        )
        for row in (existing.data or []):
            client.table("source_documents").delete().eq("id", row["id"]).execute()

    # buildings.identity_key = '강남대로374' 삭제
    bld_result = (
        client.table("buildings")
        .select("id")
        .eq("identity_key", "강남대로374")
        .execute()
    )
    for row in (bld_result.data or []):
        client.table("buildings").delete().eq("id", row["id"]).execute()
    print(f"  정리 완료: buildings {len(bld_result.data or [])}행 삭제\n")

    # ── 시나리오 1: OSCAR 1건 적재 ──────────────────────────────────────
    print("[시나리오 1] 케이스퀘어 강남 II (OSCAR) 1건 적재")
    result1 = store_document(oscar_doc, oscar_buildings, client=client)
    print(f"  result={result1}")

    # buildings 1행
    bld_rows = client.table("buildings").select("id, name, identity_key").eq("identity_key", "강남대로374").execute()
    _assert(len(bld_rows.data) == 1, f"buildings 1행 (got {len(bld_rows.data)})")
    building_id = bld_rows.data[0]["id"]
    print(f"  building_id={building_id}")

    # building_field_values에 pdf_parse 출처 행 존재
    fv_count = _count(client, "building_field_values", building_id=building_id)
    _assert(fv_count > 0, f"building_field_values {fv_count}행 존재")

    # listing_snapshot 1건
    ls_rows = client.table("listing_snapshots").select("id").eq("building_id", building_id).execute()
    _assert(len(ls_rows.data) == 1, f"listing_snapshots 1행 (got {len(ls_rows.data)})")
    ls_id = ls_rows.data[0]["id"]

    # floor_availabilities 2행 (18층 + Total)
    fa_count = _count(client, "floor_availabilities", listing_snapshot_id=ls_id)
    _assert(fa_count == 2, f"floor_availabilities 2행 (got {fa_count})")

    # ── 시나리오 2: 동일 PDF 2회 적재 → 중복 0 ──────────────────────────
    print("\n[시나리오 2] 동일 PDF 2회 적재 → 중복 0")
    result2 = store_document(oscar_doc, oscar_buildings, client=client)
    print(f"  result={result2}")

    bld_count_after = len(
        client.table("buildings").select("id").eq("identity_key", "강남대로374").execute().data
    )
    _assert(bld_count_after == 1, f"buildings 여전히 1행 (got {bld_count_after})")

    ls_count_after = len(
        client.table("listing_snapshots").select("id").eq("building_id", building_id).execute().data
    )
    _assert(ls_count_after == 1, f"listing_snapshots 여전히 1행 (got {ls_count_after})")

    fa_count_after = _count(client, "floor_availabilities", listing_snapshot_id=ls_id)
    _assert(fa_count_after == 2, f"floor_availabilities 여전히 2행 (got {fa_count_after})")

    # ── 시나리오 3: CW 중개사 같은 주소 건물 적재 ───────────────────────
    print("\n[시나리오 3] CW 중개사 같은 주소(강남대로374) 건물 적재")
    result3 = store_document(cnw_doc, cnw_buildings, client=client)
    print(f"  result={result3}")

    # buildings 여전히 1행 (주소 매칭키로 동일 건물 인식)
    bld_count_final = len(
        client.table("buildings").select("id").eq("identity_key", "강남대로374").execute().data
    )
    _assert(bld_count_final == 1, f"buildings 1행 유지 (got {bld_count_final})")

    # building_field_values에 출처 2건 (OSCAR + CW source_document_id)
    fv_rows = (
        client.table("building_field_values")
        .select("source_document_id")
        .eq("building_id", building_id)
        .eq("field_name", "gross_area_sqm")
        .execute()
    )
    source_ids = {r["source_document_id"] for r in (fv_rows.data or [])}
    _assert(len(source_ids) == 2, f"gross_area_sqm 출처 2건 (got {len(source_ids)})")

    # listing_snapshots: OSCAR + CW 2건 (broker 다름)
    ls_count_final = len(
        client.table("listing_snapshots").select("id").eq("building_id", building_id).execute().data
    )
    _assert(ls_count_final == 2, f"listing_snapshots 2건 (broker 별) (got {ls_count_final})")

    print("\n모든 시나리오 통과.")


if __name__ == "__main__":
    run_tests()
