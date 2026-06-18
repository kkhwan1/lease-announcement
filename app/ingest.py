"""PDF 입력 + 멱등 처리 — SHA256 해시, 중개사 식별, 출처월 추출.

멱등성: 같은 PDF를 재처리해도 동일한 sha256를 반환 → DB upsert 키로 활용.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from app.schemas import BrokerCode


# ---------------------------------------------------------------------------
# SHA256
# ---------------------------------------------------------------------------

def compute_sha256(pdf_path: str | Path) -> str:
    """PDF 파일의 SHA256 hex digest 반환 (멱등 키)."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 중개사 식별
# ---------------------------------------------------------------------------

# 파일명 패턴 → BrokerCode (우선순위 순)
_FILENAME_PATTERNS: list[tuple[re.Pattern, BrokerCode]] = [
    (re.compile(r"오스카앤컴퍼니|oscar", re.IGNORECASE), BrokerCode.OSCAR),
    (re.compile(r"에스원|s1[\s_-]|s-one", re.IGNORECASE), BrokerCode.S1),
    (re.compile(r"JLL", re.IGNORECASE), BrokerCode.JLL),
    (re.compile(r"C&W|Cushman|cushwake|c_w", re.IGNORECASE), BrokerCode.CW),
]

# 첫 페이지 텍스트 키워드 → BrokerCode
_COPYRIGHT_PATTERNS: list[tuple[re.Pattern, BrokerCode]] = [
    (re.compile(r"OSCAR\s*&\s*Company|오스카앤컴퍼니", re.IGNORECASE), BrokerCode.OSCAR),
    (re.compile(r"에스원|S-ONE|s1\s+real", re.IGNORECASE), BrokerCode.S1),
    (re.compile(r"Jones\s+Lang\s+LaSalle|JLL", re.IGNORECASE), BrokerCode.JLL),
    (re.compile(r"Cushman\s*&\s*Wakefield|cushwake|C&W", re.IGNORECASE), BrokerCode.CW),
]


def identify_broker(pdf_path: str | Path) -> BrokerCode:
    """파일명 패턴 + 첫 페이지 copyright 텍스트로 중개사 코드 식별.

    1차: 파일명 패턴 (가장 빠름)
    2차: 첫 페이지 텍스트 (파일명 불분명 시 폴백)
    미식별 시 OSCAR 기본값 반환 (오스카 PDF가 주 처리 대상)
    """
    filename = Path(pdf_path).name

    # 1차: 파일명 패턴
    for pattern, code in _FILENAME_PATTERNS:
        if pattern.search(filename):
            return code

    # 2차: 첫 페이지 텍스트
    try:
        doc = fitz.open(str(pdf_path))
        first_page_text = doc[0].get_text() if doc.page_count > 0 else ""
        # 마지막 페이지(copyright 페이지)도 추가 확인
        last_page_text = doc[-1].get_text() if doc.page_count > 1 else ""
        doc.close()
        combined = first_page_text + "\n" + last_page_text
        for pattern, code in _COPYRIGHT_PATTERNS:
            if pattern.search(combined):
                return code
    except Exception:
        pass

    # 미식별: ETC 대신 OSCAR를 기본으로 (주 처리 대상)
    return BrokerCode.OSCAR


# ---------------------------------------------------------------------------
# 출처월 추출
# ---------------------------------------------------------------------------

# 영문 월명 → 번호 매핑
_MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def extract_source_month(filename: str) -> Optional[str]:
    """파일명에서 발행월을 'YYYY-MM' 형식으로 추출.

    지원 형식:
    - '2026.06' → '2026-06'
    - 'June', '2026_June', '2026.June' → '2026-06'
    - '2026-06'은 그대로
    """
    name = Path(filename).stem  # 확장자 제거

    # 'YYYY.MM' 또는 'YYYY-MM' 또는 'YYYY_MM' 패턴
    m = re.search(r"(20\d{2})[.\-_](\d{2})(?!\d)", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # 'YYYY_Month' 또는 'YYYY.Month' 또는 'YYYY Month'
    m = re.search(
        r"(20\d{2})[.\-_\s]?"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
        name, re.IGNORECASE
    )
    if m:
        year = m.group(1)
        month_num = _MONTH_NAMES[m.group(2).lower()]
        return f"{year}-{month_num}"

    # 단독 월명 ('June')
    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\b",
        name, re.IGNORECASE
    )
    if m:
        # 연도 별도 탐색
        year_m = re.search(r"(20\d{2})", name)
        month_num = _MONTH_NAMES[m.group(1).lower()]
        if year_m:
            return f"{year_m.group(1)}-{month_num}"
        return f"????-{month_num}"  # 연도 불명

    return None
