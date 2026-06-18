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
# 키워드가 텍스트 블록의 bbox와 이미지 bbox의 x축 정렬·y거리로 매칭되어
# "캡션이 가리키는 이미지"를 찾는다.
#
# 매칭 우선순위(MATCH_PRIORITY)가 낮을수록 더 구체적인 라벨로 간주하여,
# 한 이미지에 여러 키워드가 걸릴 때 더 구체적인 쪽을 채택한다.
# (예: "기준층 공용부"는 INTERIOR(공용부)와 LOBBY 모두 매칭될 수 있으나,
#  실측상 케이스퀘어 우측 사진은 공용부이므로 INTERIOR가 우선)
_SLOT_KEYWORDS: dict[ImageKind, list[str]] = {
    ImageKind.LOCATION_MAP: [
        "위치도", "약도", "location", "오시는", "교통", "지도", "map",
        "위치", "찾아오시는",
    ],
    ImageKind.FLOOR_PLAN: [
        "평면도", "floor plan", "도면", "배치도", "구획", "호실",
        "floor", "plan",
    ],
    ImageKind.INTERIOR: [
        "전용부", "공용부", "코어", "사무공간", "내부전경", "내부",
        "interior", "인테리어", "office",
    ],
    ImageKind.LOBBY: [
        "로비", "lobby", "출입구", "엘리베이터홀", "엘리베이터", "elevator",
    ],
    ImageKind.EXTERIOR: [
        "외관", "전경", "조감도", "전면", "exterior", "건물",
    ],
}

# 매칭 우선순위: 숫자가 작을수록 더 구체적인 라벨(동점 시 우선 채택).
# location_map / floor_plan은 섹션 헤더로 명확히 구분되므로 가장 높은 우선순위.
# interior(전용부·공용부)는 lobby보다 구체적인 사진 캡션이므로 우선.
_KIND_MATCH_PRIORITY: dict[ImageKind, int] = {
    ImageKind.LOCATION_MAP: 0,
    ImageKind.FLOOR_PLAN: 0,
    ImageKind.INTERIOR: 1,
    ImageKind.LOBBY: 2,
    ImageKind.EXTERIOR: 3,
}

# 캡션-이미지 매칭 파라미터 (실측 기준: 오스카·C&W 540pt 높이 페이지)
# 캡션은 이미지 "위"가 일반적이나(오스카 photo 페이지), "아래"인 경우도 허용.
# 2x2 그리드에서 캡션은 컬럼 상단에만 있으므로 위쪽 탐색 거리를 넉넉히 둔다.
_LABEL_Y_ABOVE_MAX = 240.0   # 캡션이 이미지 위에 있을 때 허용 거리(컬럼 하단 이미지까지 닿도록)
_LABEL_Y_BELOW_MAX = 40.0    # 캡션이 이미지 아래에 있을 때 허용 거리(작게)
_LABEL_X_OVERLAP_RATIO = 0.10  # x축 오버랩이 이미지 너비의 10% 이상이면 같은 컬럼 후보
# (컬럼 간격이 넓어 10%로도 좌/중/우 컬럼이 구분됨. 섹션 헤더가 이미지보다
#  살짝 왼쪽으로 치우친 경우(미래에셋 Floor Plan 등)까지 잡기 위해 낮춤)

# 이 코퍼스(오스카·C&W)의 캡션은 거의 항상 이미지 "위"에 있다.
# 섹션 헤더("Location")가 바로 위 이미지(외관)로 새는 것을 막기 위해
# "아래" 캡션에는 큰 페널티를 줘 "위" 캡션을 강하게 우선한다.
_LABEL_BELOW_PENALTY = 1000.0


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _collect_text_labels(page: fitz.Page) -> list[tuple[ImageKind, tuple[float, float, float, float]]]:
    """페이지 텍스트 블록에서 슬롯 키워드를 찾아 (kind, bbox) 목록 반환.

    bbox는 (x0, y0, x1, y1) — 텍스트 블록 좌표.

    **줄(line) 단위**로 처리한다. PyMuPDF는 "Location/Floor Plan/Rent"나
    "로비 ... 기준층 공용부"처럼 가로로 나란한 캡션을 한 블록으로 합치므로,
    블록 단위로 보면 캡션 bbox가 페이지 전체 폭을 덮어 좌우 컬럼을 구분할 수 없다.
    줄 단위로 보면 각 캡션이 자기 위치의 좁은 bbox를 가져 x축 정렬 매칭이 정확해진다.

    한 줄에서 여러 kind 키워드가 잡히면(예: "기준층 공용부" → INTERIOR),
    _KIND_MATCH_PRIORITY가 가장 낮은(=가장 구체적인) kind 하나만 채택한다.
    """
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return []

    labels: list[tuple[ImageKind, tuple[float, float, float, float]]] = []

    for block in blocks:
        if block.get("type") != 0:  # 0 = 텍스트 블록
            continue
        for line in block.get("lines", []):
            line_bbox = tuple(line.get("bbox", (0, 0, 0, 0)))
            line_text = "".join(
                sp.get("text", "") for sp in line.get("spans", [])
            ).strip().lower()
            if not line_text:
                continue

            # 이 줄이 매칭하는 모든 kind를 모은 뒤, 우선순위가 가장 높은 것만 채택
            matched: list[ImageKind] = []
            for kind, keywords in _SLOT_KEYWORDS.items():
                for kw in keywords:
                    if kw.lower() in line_text:
                        matched.append(kind)
                        break  # 같은 kind는 한 번만
            if matched:
                best_kind = min(matched, key=lambda k: _KIND_MATCH_PRIORITY.get(k, 99))
                labels.append((best_kind, line_bbox))

    return labels


def _label_match_score(
    img_bbox: tuple[float, float, float, float],
    label_bbox: tuple[float, float, float, float],
) -> Optional[float]:
    """캡션(label)이 이미지를 가리키는지 판단하고 매칭 점수를 반환.

    매칭 조건:
    - x축: 캡션과 이미지의 x범위가 이미지 너비의 _LABEL_X_OVERLAP_RATIO 이상 겹쳐야
      같은 컬럼(왼쪽/오른쪽 사진)으로 간주.
    - y축: 캡션이 이미지 위쪽(_LABEL_Y_ABOVE_MAX 이내), 아래쪽(_LABEL_Y_BELOW_MAX 이내),
      또는 수직으로 겹치면 후보.

    점수(작을수록 좋음) = x중심 거리 + y거리. 2x2 그리드에서 왼쪽/오른쪽 캡션을
    구분하기 위해 x중심 거리를 1차로 중시한다.

    매칭 불가 시 None.
    """
    ix0, iy0, ix1, iy1 = img_bbox
    lx0, ly0, lx1, ly1 = label_bbox
    iw = ix1 - ix0
    if iw <= 0:
        return None

    # x축 정렬 — 같은 컬럼(왼쪽/오른쪽 사진)인지 판정.
    # 캡션(섹션 헤더 "Location" 등)이 이미지보다 훨씬 좁을 수 있으므로
    # 세 조건 중 하나라도 만족하면 같은 컬럼으로 본다:
    #  (a) x겹침이 이미지 너비의 _LABEL_X_OVERLAP_RATIO 이상
    #  (b) 캡션 중심 x가 이미지 x범위 안 (좁은 캡션이 이미지 위에 얹힌 경우)
    #  (c) 이미지 중심 x가 캡션 x범위 안 (이미지가 캡션보다 좁은 경우)
    img_cx = (ix0 + ix1) / 2.0
    lbl_cx = (lx0 + lx1) / 2.0
    overlap_x = max(0.0, min(ix1, lx1) - max(ix0, lx0))
    same_column = (
        overlap_x / iw >= _LABEL_X_OVERLAP_RATIO
        or (ix0 <= lbl_cx <= ix1)
        or (lx0 <= img_cx <= lx1)
    )
    if not same_column:
        return None

    # y축 위치 판정
    if ly1 <= iy0:
        # 캡션이 이미지 위
        y_dist = iy0 - ly1
        if y_dist > _LABEL_Y_ABOVE_MAX:
            return None
    elif ly0 >= iy1:
        # 캡션이 이미지 아래 — 이 코퍼스에선 드물어 큰 페널티 부여
        y_dist = (ly0 - iy1) + _LABEL_BELOW_PENALTY
        if (ly0 - iy1) > _LABEL_Y_BELOW_MAX:
            return None
    else:
        # 캡션이 이미지와 수직 겹침 (이미지 안/걸침)
        y_dist = 0.0

    # x중심 거리 — 좌우 컬럼 구분용 (1차 가중)
    x_center_dist = abs(img_cx - lbl_cx)

    return x_center_dist + y_dist


def _classify_image_kind(
    img_bbox: tuple[float, float, float, float],
    labels: list[tuple[ImageKind, tuple[float, float, float, float]]],
    is_largest: bool,
    page_dominant_kind: Optional[ImageKind] = None,
) -> ImageKind:
    """이미지 bbox와 텍스트 레이블 bbox를 비교해 ImageKind 결정.

    알고리즘:
    1) 모든 캡션 중 이미지와 매칭되는 것들을 점수화(x중심 거리 + y거리, 작을수록 좋음).
    2) 점수가 가장 좋은(가장 가까운) 캡션의 kind 채택.
       동점이면 _KIND_MATCH_PRIORITY가 낮은(구체적인) kind 우선.
    3) 매칭 없으면서 가장 큰 이미지 → EXTERIOR 추정 (외관은 보통 가장 큼).
    4) 캡션이 못 닿은 사진이지만 페이지에 사진형 캡션 하나만 있으면(page_dominant_kind)
       그 kind 상속 (오스카 photo 페이지: "기준층 전용부" 캡션 1개 + 사진 4장).
    5) 나머지 → OTHER.
    """
    best_kind: Optional[ImageKind] = None
    best_score: Optional[float] = None

    for kind, lbbox in labels:
        score = _label_match_score(img_bbox, lbbox)
        if score is None:
            continue
        # 더 가까운 캡션, 동점이면 더 구체적인 kind 채택
        if (
            best_score is None
            or score < best_score - 1e-6
            or (
                abs(score - best_score) <= 1e-6
                and best_kind is not None
                and _KIND_MATCH_PRIORITY.get(kind, 99)
                < _KIND_MATCH_PRIORITY.get(best_kind, 99)
            )
        ):
            best_kind = kind
            best_score = score

    # 위쪽 캡션으로 확실히 매칭된 경우만 신뢰.
    # best_score가 페널티 임계(_LABEL_BELOW_PENALTY) 이상이면 "아래 캡션"만
    # 걸린 약한 매칭이므로, 가장 큰 이미지는 외관 추정을 우선한다.
    weak_below_only = best_score is not None and best_score >= _LABEL_BELOW_PENALTY

    if best_kind is not None and not weak_below_only:
        return best_kind

    # 텍스트 기반 매칭 실패(또는 약한 아래-캡션만) — 가장 큰 이미지는 외관으로 추정
    if is_largest:
        return ImageKind.EXTERIOR

    # 약한 아래-캡션 매칭이라도 외관 추정이 안 되면 그 kind라도 반환
    if best_kind is not None:
        return best_kind

    # 페이지에 사진형 캡션이 하나만 있는 경우(전용부 사진 페이지 등) 그 kind 상속
    if page_dominant_kind is not None:
        return page_dominant_kind

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

        # 페이지 지배 캡션(page_dominant_kind) 산출:
        # 페이지의 캡션 kind가 사진형(lobby/interior/exterior) 한 종류뿐이면,
        # 캡션이 못 닿은 사진(우측 컬럼 등)도 그 kind로 상속한다.
        # location_map/floor_plan(섹션 헤더) 같은 비사진형이 섞인 detail 페이지엔
        # 적용하지 않아 오분류를 막는다.
        label_kinds = {k for k, _ in labels}
        _PHOTO_KINDS = {ImageKind.LOBBY, ImageKind.INTERIOR, ImageKind.EXTERIOR}
        page_dominant_kind: Optional[ImageKind] = None
        if len(label_kinds) == 1:
            only_kind = next(iter(label_kinds))
            if only_kind in _PHOTO_KINDS:
                page_dominant_kind = only_kind

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

            kind = _classify_image_kind(
                img_bbox, labels, is_largest, page_dominant_kind=page_dominant_kind
            )

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
