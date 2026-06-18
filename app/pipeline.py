"""PDF 처리 파이프라인 — 단건 PDF를 SourceDocument로 변환하는 핵심 오케스트레이터.

처리 순서:
  1. SHA256 / 중개사 / 출처월 식별 (ingest)
  2. 전 페이지 classify_page
  3. group_pages로 건물 그룹화
  4. 중개사에 맞는 어댑터로 각 그룹 extract
  5. JLL / 미지원 중개사는 경고 로그 + 빈 buildings 반환
"""
from __future__ import annotations

import logging
import tempfile
import warnings
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from app.classify_pages import classify_page
from app.group_buildings import group_pages
from app.image_extractor import extract_images
from app.ingest import compute_sha256, extract_source_month, identify_broker
from app.schemas import BrokerCode, BuildingExtraction, SourceDocument
from app.adapters.oscar import OscarTableAdapter
from app.adapters.cnw import CnWTableAdapter
from app.adapters.s1 import S1OverviewAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 중개사 코드 → 어댑터 매핑
# JLL은 Vision 필요 — 현재 범위 제외
# ---------------------------------------------------------------------------
ADAPTER_MAP = {
    BrokerCode.OSCAR: OscarTableAdapter,
    BrokerCode.CW: CnWTableAdapter,
    BrokerCode.S1: S1OverviewAdapter,
}

# 건물명으로 skip할 접두어 (목차·표지 그룹)
_SKIP_PREFIXES = ("__unknown", "__meta")


def _should_skip(building_name: str) -> bool:
    """목차/표지 그룹은 추출 대상에서 제외."""
    if not building_name:
        return True
    return any(building_name.startswith(p) for p in _SKIP_PREFIXES)


def process_pdf(
    pdf_path: str | Path,
    img_out_dir: Optional[Path] = None,
) -> SourceDocument:
    """PDF 한 건을 처리해 SourceDocument를 반환.

    Args:
        pdf_path: 처리할 PDF 파일 경로
        img_out_dir: 이미지 crop PNG를 저장할 디렉토리.
            None이면 임시 디렉토리를 사용하지 않고 이미지 메타만 추출
            (file_path=None → Storage 업로드 불가).
            호출자가 지정하면 해당 경로의 수명을 호출자가 책임진다.

    Returns:
        SourceDocument — broker/filename/sha256/source_month/page_count/buildings
    """
    pdf_path = Path(pdf_path)
    source_filename = pdf_path.name

    # 1. 메타 식별
    file_sha256 = compute_sha256(pdf_path)
    broker = identify_broker(pdf_path)
    source_month = extract_source_month(source_filename)

    logger.info("[pipeline] %s → broker=%s, month=%s", source_filename, broker, source_month)

    # 2. PDF 열기 + 전 페이지 분류
    doc = fitz.open(str(pdf_path))
    page_count = doc.page_count

    page_types: list[str] = []
    for i in range(page_count):
        pt = classify_page(doc[i])
        page_types.append(pt)
        logger.debug("  page %d: %s", i + 1, pt)

    # 3. 건물 그룹화
    groups = group_pages(doc, broker, page_types=page_types)
    logger.info("[pipeline] 건물 그룹 %d개", len(groups))

    # 4. 어댑터 선택 + 추출
    buildings: list[BuildingExtraction] = []

    adapter_cls = ADAPTER_MAP.get(broker)
    if adapter_cls is None:
        # JLL 또는 미지원 중개사 — 경고만 남기고 빈 목록 반환
        warnings.warn(
            f"[pipeline] {broker} 어댑터 미구현 — {source_filename} 건물 추출 생략",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning("[pipeline] 미지원 중개사: %s → buildings=[]", broker)
    else:
        adapter = adapter_cls()

        for group in groups:
            # 목차·표지 그룹 skip
            if _should_skip(group.building_name):
                logger.debug("[pipeline] skip 그룹: %s", group.building_name)
                continue
            try:
                extraction = adapter.extract(
                    doc, group, source_filename, source_month
                )

                # 5. 이미지 추출 — 건물별 서브 디렉토리에 crop PNG 저장
                #    img_out_dir이 지정된 경우에만 파일 저장 (Storage 업로드용)
                #    Storage 업로드는 supa_store._upsert_building_images에서 처리
                safe_name = group.building_name.replace("/", "-").replace(" ", "_")
                building_img_dir = (img_out_dir / safe_name) if img_out_dir else None
                try:
                    images = extract_images(doc, group, out_dir=building_img_dir)
                    extraction.images = images
                    logger.info(
                        "  이미지 추출: %s → %d개",
                        extraction.building_name, len(images),
                    )
                except Exception as img_exc:
                    # 이미지 추출 실패는 경고만 — 텍스트 데이터 적재는 계속
                    logger.warning(
                        "  이미지 추출 실패 (건물 적재는 계속): %s — %s",
                        group.building_name, img_exc,
                    )

                buildings.append(extraction)
                logger.info("  추출 완료: %s (floors=%d)", extraction.building_name, len(extraction.floors))
            except Exception as exc:
                logger.error("  추출 실패: %s — %s", group.building_name, exc, exc_info=True)

    doc.close()

    return SourceDocument(
        broker=broker,
        filename=source_filename,
        file_sha256=file_sha256,
        source_month=source_month,
        page_count=page_count,
        buildings=buildings,
    )
