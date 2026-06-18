"""PDF 페이지에서 건물 사진을 추출한다 (Vision 미사용, 규칙 기반).

흐름:
1) PageGroup의 page_indices를 순회
2) page.get_image_info(xrefs=True)로 이미지 표시영역 수집
3) 노이즈 필터 3단계 적용 (크기·반복 xref·면적 비율)
4) 텍스트 블록 키워드로 슬롯 분류 (location_map/floor_plan/exterior/lobby/interior)
5) out_dir 지정 시 crop PNG 저장, 없으면 메타만 반환

실측 기반 노이즈 기준:
- C&W PDF: 필터 전 4352개 수준의 아이콘·배경 타일 존재
- width < 120 또는 height < 120 → 아이콘/로고/배경
- 같은 xref 한 페이지에 5회 이상 → 배경 패턴 타일
- 페이지 면적의 0.5% 미만 → 장식 요소
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import fitz  # PyMuPDF

from app.schemas import BuildingImage, ImageKind
from app.group_buildings import PageGroup

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# 노이즈 필터 상수 (실측 기준)
# ---------------------------------------------------------------------------

# 최소 표시 크기 (PDF 포인트 단위, 72dpi 기준). 120px ≈ 120pt(96dpi 환산)
# 오스카·C&W 실측: 아이콘/로고는 대부분 30~80pt 범위
_MIN_WIDTH_PT = 120.0
_MIN_HEIGHT_PT = 120.0

# 같은 xref가 한 페이지에 반복될 때 배경 패턴으로 판정하는 임계값
_MAX_XREF_REPEAT = 5

# 페이지 면적 대비 최소 비율 (0.5%)
_MIN_AREA_RATIO = 0.005

# ---------------------------------------------------------------------------
# 슬롯 분류 키워드 (한국어 + 영어)
# ---------------------------------------------------------------------------

# 각 ImageKind에 매핑할 키워드 목록.
# 키워드가 텍스트 블록의 bbox y-좌표와 함께 사용되어 "근처 이미지"를 찾는다.
_SLOT_KEYWORDS: dict[ImageKind, list[str]] = {
    ImageKind.LOCATION_MAP: [
        "location", "위치도", "위치", "지도", "map", "오시는", "교통",
    ],
    ImageKind.FLOOR_PLAN: [
        "floor plan", "평면도", "floor", "plan", "호실", "구획",
    ],
    ImageKind.LOBBY: [
        "로비", "lobby",
    ],
    ImageKind.INTERIOR: [
        "전용부", "내부", "interior", "인테리어",
    ],
    ImageKind.EXTERIOR: [
        "외관", "전경", "exterior", "조감도", "전면",
    ],
}

# 텍스트 블록과 이미지 bbox의 y축 허용 오차 (이미지가 텍스트 블록 아래 가까이 있으면 연결)
_LABEL_Y_PROXIMITY = 120.0  # PDF 포인트
_LABEL_X_OVERLAP_RATIO = 0.3  # x축 오버랩이 이미지 너비의 30% 이상이면 같은 컬럼으로 간주


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _collect_text_labels(page: fitz.Page) -> list[tuple[ImageKind, tuple[float, float, float, float]]]:
    """페이지 텍스트 블록에서 슬롯 키워드를 찾아 (kind, bbox) 목록 반환.

    bbox는 (x0, y0, x1, y1) — 텍스트 블록 좌표.
    """
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return []

    labels: list[tuple[ImageKind, tuple[float, float, float, float]]] = []

    for block in blocks:
        if block.get("type") != 0:  # 0 = 텍스트 블록
            continue
        block_bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
        # 블록의 모든 줄 텍스트를 합침
        block_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                block_text += span.get("text", "")
        block_text_lower = block_text.strip().lower()
        if not block_text_lower:
            continue

        for kind, keywords in _SLOT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in block_text_lower:
                    labels.append((kind, block_bbox))
                    break  # 같은 블록에서 한 kind만 매칭

    return labels


def _classify_image_kind(
    img_bbox: tuple[float, float, float, float],
    labels: list[tuple[ImageKind, tuple[float, float, float, float]]],
    is_largest: bool,
) -> ImageKind:
    """이미지 bbox와 텍스트 레이블 bbox를 비교해 ImageKind 결정.

    우선순위:
    1) 텍스트 레이블이 이미지 바로 위(또는 근처)에 있고 x축이 겹치면 해당 kind
    2) 매칭 없으면서 가장 큰 이미지 → EXTERIOR 추정
    3) 나머지 → OTHER
    """
    ix0, iy0, ix1, iy1 = img_bbox
    iw = ix1 - ix0

    for kind, lbbox in labels:
        lx0, ly0, lx1, ly1 = lbbox

        # y축: 레이블이 이미지 위쪽에 있고 간격이 _LABEL_Y_PROXIMITY 이내
        label_above = (ly1 <= iy0) and (iy0 - ly1 <= _LABEL_Y_PROXIMITY)
        # 또는 레이블이 이미지와 같은 y범위 내 (수직으로 겹침)
        label_overlap_y = not (ly1 < iy0 or ly0 > iy1)

        if not (label_above or label_overlap_y):
            continue

        # x축 오버랩 계산
        overlap_x = max(0.0, min(ix1, lx1) - max(ix0, lx0))
        if iw > 0 and overlap_x / iw >= _LABEL_X_OVERLAP_RATIO:
            return kind

    # 텍스트 기반 매칭 실패 시 — 가장 큰 이미지는 외관으로 추정
    if is_largest:
        return ImageKind.EXTERIOR

    return ImageKind.OTHER


def _filter_noise(
    img_info_list: list[dict],
    page_area: float,
) -> list[dict]:
    """노이즈 이미지를 제거하고 실제 사진만 반환.

    필터 기준:
    1. 표시영역 width < 120 또는 height < 120 (아이콘/로고/배경 타일)
    2. 같은 xref가 한 페이지에 5회 이상 반복 (배경 패턴)
    3. 페이지 면적의 0.5% 미만 (장식 요소)
    """
    # 먼저 xref 반복 횟수 집계
    xref_counts = Counter(info.get("xref", 0) for info in img_info_list)
    repeated_xrefs = {xref for xref, cnt in xref_counts.items() if cnt >= _MAX_XREF_REPEAT}

    filtered: list[dict] = []
    for info in img_info_list:
        bbox = info.get("bbox", (0, 0, 0, 0))
        x0, y0, x1, y1 = bbox
        w = x1 - x0
        h = y1 - y0
        area = w * h
        xref = info.get("xref", 0)

        # 필터 1: 최소 크기
        if w < _MIN_WIDTH_PT or h < _MIN_HEIGHT_PT:
            continue

        # 필터 2: 반복 xref (배경 패턴)
        if xref in repeated_xrefs:
            continue

        # 필터 3: 최소 면적 비율
        if page_area > 0 and area / page_area < _MIN_AREA_RATIO:
            continue

        filtered.append(info)

    return filtered


def _crop_and_save(
    page: fitz.Page,
    rect: fitz.Rect,
    out_path: Path,
    zoom: float = 2.0,
) -> None:
    """페이지에서 rect 영역을 crop해 PNG로 저장.

    zoom=2.0 → 144dpi (72dpi 기본의 2배, 선명도 확보)
    """
    mat = fitz.Matrix(zoom, zoom)
    clip = fitz.Rect(rect)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    pix.save(str(out_path))


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def extract_images(
    doc: fitz.Document,
    page_group: PageGroup,
    out_dir: Optional[Path] = None,
) -> list[BuildingImage]:
    """PageGroup 내 모든 페이지에서 건물 사진을 추출한다.

    Args:
        doc: PyMuPDF Document (열린 상태)
        page_group: 추출 대상 페이지 묶음 (PageGroup)
        out_dir: crop PNG를 저장할 디렉토리. None이면 파일 저장 없이 메타만 반환.

    Returns:
        BuildingImage 목록 (노이즈 제거 후 실제 건물 사진만)

    노이즈 필터 실측 기준:
    - C&W PDF p7-8: 필터 전 140~168개 → 필터 후 0~2개 (배경/아이콘 제거)
    - 오스카 케이스퀘어 p3-5: 필터 전 28~168개 → 필터 후 3~4개 (실제 사진만)
    """
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    results: list[BuildingImage] = []

    for page_idx in page_group.page_indices:
        if page_idx < 0 or page_idx >= doc.page_count:
            continue

        page = doc[page_idx]
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height
        page_number = page_idx + 1  # 1-based 페이지 번호 (사용자 표기용)

        # 이미지 표시영역 수집
        try:
            img_info_list = page.get_image_info(xrefs=True)
        except Exception:
            continue

        if not img_info_list:
            continue

        # 노이즈 필터 적용
        raw_count = len(img_info_list)
        filtered = _filter_noise(img_info_list, page_area)
        filtered_count = len(filtered)

        # 디버그 출력 (노이즈 필터 전후 비교)
        print(
            f"  Page {page_number}: 필터 전 {raw_count}개 → 필터 후 {filtered_count}개"
        )

        if not filtered:
            continue

        # 텍스트 레이블 수집 (슬롯 분류용)
        labels = _collect_text_labels(page)

        # 면적 기준으로 가장 큰 이미지 xref 파악
        def _img_area(info: dict) -> float:
            bbox = info.get("bbox", (0, 0, 0, 0))
            return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

        max_area = max(_img_area(info) for info in filtered)

        for idx, info in enumerate(filtered):
            bbox_raw = info.get("bbox", (0, 0, 0, 0))
            x0, y0, x1, y1 = bbox_raw
            w = int(round(x1 - x0))
            h = int(round(y1 - y0))

            img_bbox = (x0, y0, x1, y1)
            is_largest = abs(_img_area(info) - max_area) < 1.0  # 면적이 최대인 이미지

            kind = _classify_image_kind(img_bbox, labels, is_largest)

            # crop PNG 저장 (out_dir 지정 시)
            file_path: Optional[str] = None
            if out_dir is not None:
                safe_name = page_group.building_name.replace("/", "-").replace(" ", "_")
                fname = f"{safe_name}_p{page_number}_{idx}_{kind.value}.png"
                fpath = out_dir / fname
                try:
                    rect = fitz.Rect(x0, y0, x1, y1)
                    _crop_and_save(page, rect, fpath)
                    file_path = str(fpath)
                except Exception as e:
                    print(f"    경고: crop 저장 실패 ({fname}): {e}")

            results.append(
                BuildingImage(
                    kind=kind,
                    page_number=page_number,
                    bbox=[x0, y0, x1, y1],
                    width_px=w,
                    height_px=h,
                    file_path=file_path,
                )
            )

    return results
