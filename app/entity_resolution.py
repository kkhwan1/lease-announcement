"""Entity Resolution — 건물 중복 판정 모듈.

우선순위:
1. 주소 매칭키(address_match_key) 동일 → 즉시 동일 건물 (건물명 달라도 OK)
2. 건물명 fuzzy 유사도:
   - ≥ 0.92 → 자동 매칭
   - 0.80 ~ 0.92 → merge_candidates 큐 등록 후 신규 취급
   - < 0.80 → 신규 건물

반환 tuple: (building_id: str, is_new: bool, status: str)
  status: 'matched_address' | 'matched_name' | 'new' | 'queued'
"""
from __future__ import annotations

import logging
from typing import Optional

from rapidfuzz import fuzz

from app.normalize import building_match_key, address_match_key
from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)

# Entity Resolution 임계값 (사용자 결정 2026-06-18)
_THRESHOLD_AUTO = 0.92   # 이상 → 자동 매칭
_THRESHOLD_QUEUE = 0.80  # 이상 → 큐 등록 (회색지대)


def compute_match_key(b: BuildingExtraction) -> str:
    """건물 1차 식별 키 — 주소 우선(사용자 결정), 없으면 건물명.

    주소가 있으면 'addr:강남대로374', 없으면 'name:케이스퀘어강남2' 형태로
    네임스페이스를 구분해 주소키와 이름키가 우연히 겹치지 않게 한다.
    """
    addr = b.address_match_key or (address_match_key(b.address_raw) if b.address_raw else "")
    if addr:
        return f"addr:{addr}"
    name_key = building_match_key(b.building_name)
    return f"name:{name_key}" if name_key else ""


def resolve_building(
    client,  # supabase.Client
    b: BuildingExtraction,
    source_document_id: Optional[str] = None,
) -> tuple[str, bool, str]:
    """건물 중복 판정 후 building_id 반환.

    Args:
        client: Supabase Python 클라이언트
        b: 추출된 BuildingExtraction
        source_document_id: merge_candidates 출처 추적용 (선택)

    Returns:
        (building_id, is_new, status)
        - status: 'matched_address' | 'matched_name' | 'new' | 'queued'
    """
    # ── 1차: match_key(주소 우선)로 건물 검색 ────────────────────────────
    mkey = compute_match_key(b)
    if mkey:
        result = (
            client.table("buildings")
            .select("id, name")
            .eq("match_key", mkey)
            .limit(1)
            .execute()
        )
        if result.data:
            building_id = result.data[0]["id"]
            logger.debug("match_key 매칭: %s → building_id=%s", mkey, building_id)
            # 주소 기반 키면 'matched_address', 이름 기반이면 'matched_name'
            status = "matched_address" if mkey.startswith("addr:") else "matched_name"
            return building_id, False, status

    # ── 2차: 건물명 fuzzy 유사도 검색 (주소 다른 동일 건물 보강) ──────────
    match_key = building_match_key(b.building_name)
    if match_key:
        # buildings 테이블 전체를 가져와 fuzzy 비교 (건물 수가 적어 허용)
        all_buildings = (
            client.table("buildings")
            .select("id, name")
            .execute()
        )

        best_id: Optional[str] = None
        best_score: float = 0.0
        best_name: str = ""

        for row in (all_buildings.data or []):
            candidate_key = building_match_key(row["name"])
            # token_set_ratio: 순서 무관 + 부분 집합 포함 유사도 (임대안내문에 적합)
            score = fuzz.token_set_ratio(match_key, candidate_key) / 100.0
            if score > best_score:
                best_score = score
                best_id = row["id"]
                best_name = row["name"]

        logger.debug(
            "건물명 fuzzy 검색: %s → best='%s' (%.3f)",
            b.building_name, best_name, best_score,
        )

        if best_score >= _THRESHOLD_AUTO and best_id:
            return best_id, False, "matched_name"

        if best_score >= _THRESHOLD_QUEUE and best_id:
            # 회색지대: 신규 건물 생성 후 merge_candidates 큐 등록
            new_id = _insert_building(client, b)
            _register_merge_candidate(
                client,
                building_id_a=best_id,
                building_id_b=new_id,
                similarity_score=best_score,
                source_document_id=source_document_id,
                reason=f"주소 불일치 + 이름 유사도 {best_score:.3f} ({b.building_name!r} vs {best_name!r})",
            )
            return new_id, True, "queued"

    # ── 신규 건물 생성 ─────────────────────────────────────────────────────
    new_id = _insert_building(client, b)
    return new_id, True, "new"


def _insert_building(client, b: BuildingExtraction) -> str:
    """buildings 테이블에 신규 행 삽입 후 id 반환."""
    payload = {
        "name": b.building_name,
        "name_raw": b.building_name_raw or b.building_name,
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
        "match_key": compute_match_key(b) or None,
    }
    # None 값은 DB 기본값에 맡김 (불필요한 null 전송 최소화)
    payload = {k: v for k, v in payload.items() if v is not None}

    mkey = payload.get("match_key")
    if mkey:
        # match_key 충돌 시(동일 건물 재등장) 기존 행 반환 — 멱등.
        result = client.table("buildings").upsert(
            payload, on_conflict="match_key", ignore_duplicates=True,
        ).execute()
        if result.data:
            return result.data[0]["id"]
        # ignore_duplicates로 data가 비면 기존 행 조회
        existing = (
            client.table("buildings").select("id").eq("match_key", mkey).limit(1).execute()
        )
        if existing.data:
            return existing.data[0]["id"]

    result = client.table("buildings").insert(payload).execute()
    if not result.data:
        raise RuntimeError(f"buildings 삽입 실패: {b.building_name}")
    return result.data[0]["id"]


def _register_merge_candidate(
    client,
    building_id_a: str,
    building_id_b: str,
    similarity_score: float,
    source_document_id: Optional[str],
    reason: str,
) -> None:
    """merge_candidates 큐 등록. (a < b) 정렬로 중복 방지."""
    # UUID 문자열 비교로 a < b 정렬 보장
    id_a, id_b = sorted([building_id_a, building_id_b])
    payload = {
        "building_id_a": id_a,
        "building_id_b": id_b,
        "similarity_score": round(similarity_score, 4),
        "match_reason": reason,
        "status": "pending",
    }
    if source_document_id:
        payload["detected_in_doc_id"] = source_document_id

    # upsert: 같은 쌍이 이미 있으면 무시
    client.table("merge_candidates").upsert(
        payload,
        on_conflict="building_id_a,building_id_b",
        ignore_duplicates=True,
    ).execute()
    logger.info("merge_candidates 큐 등록: %s ↔ %s (%.3f)", id_a, id_b, similarity_score)
