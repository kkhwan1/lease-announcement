"""페이지 분류 — 마커 규칙으로 페이지 타입을 판정한다.

타입 목록:
  detail       — 건물 상세 (General Information + Rent 동시 존재, 오스카)
  floor_table  — 층별 공실표 (별도 페이지)
  photo        — 사진/이미지 위주 페이지
  company_intro — 회사 소개
  toc          — 목차 (Table of Contents / 지역 인덱스)
  cover        — 표지 / copyright
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# 마커 패턴
# ---------------------------------------------------------------------------

# 오스카 상세 페이지 마커
_OSCAR_DETAIL_MARKERS = [
    re.compile(r"General\s+Information", re.IGNORECASE),
    re.compile(r"Rent", re.IGNORECASE),
]

# 층별 공실표 마커
_FLOOR_TABLE_MARKERS = [
    re.compile(r"공실층|층별\s*공실|Floor\s+Availability", re.IGNORECASE),
    re.compile(r"임대\s*면적|Lease\s+Area", re.IGNORECASE),
]

# 목차/지역 인덱스 마커
_TOC_MARKERS = [
    re.compile(r"^\d{2}\.\s+(GBD|CBD|YBD|BBD)", re.MULTILINE),  # '01. GBD' 형식
    re.compile(r"Table\s+of\s+Contents", re.IGNORECASE),
    re.compile(r"목\s*차", re.IGNORECASE),
    re.compile(r"INDEX", re.IGNORECASE),
]

# 회사 소개 마커
_COMPANY_INTRO_MARKERS = [
    re.compile(r"회사\s*소개|Company\s+Profile|About\s+Us", re.IGNORECASE),
    re.compile(r"OSCAR\s*&\s*Company.*소개", re.IGNORECASE | re.DOTALL),
]

# Copyright / 표지 마커
_COVER_MARKERS = [
    re.compile(r"©\s*\d{4}|copyright", re.IGNORECASE),
    re.compile(r"All\s+Rights\s+Reserved", re.IGNORECASE),
    re.compile(r"임대\s*안내문", re.IGNORECASE),  # 표지 제목
]

# 에스원 섹션 헤더
_S1_SECTION_MARKERS = [
    re.compile(r"PROPERTY\s+OVERVIEW", re.IGNORECASE),
    re.compile(r"SPACE\s+AVAILABILITY", re.IGNORECASE),
]


def classify_page(page: "fitz.Page") -> str:
    """한 페이지를 분류해 타입 문자열을 반환한다.

    판정 우선순위:
    1. cover   — 텍스트 100자 미만 + copyright 마커
    2. toc     — 목차 마커
    3. company_intro — 회사소개 마커
    4. detail  — 오스카 상세 (General Information + Rent)
    5. floor_table — 층별 공실표 마커
    6. photo   — 이미지 면적이 페이지 70% 이상이고 텍스트 적음
    7. detail  — S1 섹션 헤더 (PROPERTY OVERVIEW / SPACE AVAILABILITY)
    8. cover   — 텍스트가 너무 적으면 표지로 간주
    9. detail  — 기본값 (파싱 시도)
    """
    text = page.get_text()
    text_len = len(text.strip())

    # 1. 텍스트가 매우 적으면 → cover 우선 검토
    if text_len < 100:
        for pat in _COVER_MARKERS:
            if pat.search(text):
                return "cover"
        # 이미지 비율 확인
        if _is_photo_page(page):
            return "photo"
        return "cover"

    # 2. 목차
    for pat in _TOC_MARKERS:
        if pat.search(text):
            return "toc"

    # 3. 회사 소개
    for pat in _COMPANY_INTRO_MARKERS:
        if pat.search(text):
            return "company_intro"

    # 4. 오스카 상세 페이지: General Information + Rent 동시
    has_general_info = _OSCAR_DETAIL_MARKERS[0].search(text)
    has_rent = _OSCAR_DETAIL_MARKERS[1].search(text)
    if has_general_info and has_rent:
        return "detail"

    # 5. 층별 공실표 (별도 페이지)
    floor_hits = sum(1 for pat in _FLOOR_TABLE_MARKERS if pat.search(text))
    if floor_hits >= 2:
        return "floor_table"

    # 6. 사진 페이지: 이미지가 대부분이고 텍스트 적음
    if text_len < 300 and _is_photo_page(page):
        return "photo"

    # 7. 에스원 섹션 헤더
    s1_hits = sum(1 for pat in _S1_SECTION_MARKERS if pat.search(text))
    if s1_hits >= 1:
        return "detail"

    # 8. copyright만 있는 페이지 → cover
    if text_len < 500:
        for pat in _COVER_MARKERS:
            if pat.search(text):
                return "cover"

    # 9. 기본값: detail (파싱 시도)
    return "detail"


def _is_photo_page(page: "fitz.Page") -> bool:
    """페이지가 이미지 위주인지 판정.

    이미지 총 면적이 페이지 면적의 50% 이상이면 photo.
    """
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return False

    image_area = 0.0
    for img in page.get_image_info():
        # PyMuPDF image_info: bbox 키가 있을 때
        bbox = img.get("bbox")
        if bbox:
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w > 120 and h > 120:  # 노이즈 임계값 (120×120px 이상만 카운트)
                image_area += w * h

    return (image_area / page_area) >= 0.5
