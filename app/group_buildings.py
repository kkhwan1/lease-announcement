"""건물 단위 페이지 그룹핑 — 연속 페이지의 건물명이 같으면 한 그룹으로 묶는다.

핵심 휴리스틱:
- 오스카: 18~20pt 가장 큰 폰트의 텍스트 span이 건물명
- 건물명 추출 실패 페이지(사진 등)는 직전 그룹에 귀속
- 새 건물 그룹은 page_type=='detail' 페이지에서만 시작 (목차·사진 오염 방지)

수정 이력:
- 2026-06-18: 비정상 폰트(2^32pt) 아티팩트 필터, detail 페이지 gating,
              건물명 유효성 검사, C&W 건물명 주소 분리 (_strip_cw_address)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import fitz  # PyMuPDF

from app.schemas import BrokerCode
from app.normalize import normalize_building_name

if TYPE_CHECKING:
    pass


@dataclass
class PageGroup:
    """한 건물에 속하는 연속 페이지들의 묶음."""
    building_name: str
    page_indices: list[int] = field(default_factory=list)  # 0-based 페이지 인덱스
    page_types: list[str] = field(default_factory=list)     # classify_page 결과


# ---------------------------------------------------------------------------
# 폰트 크기 기반 건물명 추출
# ---------------------------------------------------------------------------

# 건물명 후보 폰트 크기 범위 (단위: pt)
# S1 PDF 아티팩트: 일부 span이 4294967296pt(=2^32) 같은 비현실적 크기를 가짐 → 상한 제한
_MIN_FONT_SIZE_FOR_NAME = 14.0
_MAX_FONT_SIZE_FOR_NAME = 500.0  # 합리적 최대치 (실제 건물명은 보통 16~40pt)

# 건물명으로 판정하지 않을 키워드 (헤더/푸터/페이지번호 등)
_EXCLUDE_KEYWORDS = {
    "General Information", "Floor", "Rent", "Total", "Page",
    "OSCAR", "오스카", "Copyright", "Exclusive", "Lease", "Area",
    "B/D", "GBD", "CBD", "YBD", "BBD",
    # C&W 목차/구역 헤더
    "LEASING PACKAGE", "BUSINESS DISTRICT", "MONTHLY PICK",
    "Central Business District", "Gangnam Business District",
    "Yeouido Business District", "Bundang Business District",
    "LM팀", "C&W LM",
}

# 가짜 건물명 거부 패턴
_PHONE_RE = re.compile(r"\d{2,4}[.\-]\d{3,4}[.\-]\d{4}")   # 010.1234.5678
_STARTS_NUMBER_RE = re.compile(r"^[\d,.\s]+")               # 숫자/콤마로 시작 (금액·면적)

# C&W 건물명 주소 분리 — 두 단계 패턴
# 단계1: '[태그] 주소' 형태 → 태그 앞에서 자름
#   예: '세미콜론수송[전속] 서울시...' → 태그 바로 앞 공백에서 자름
_CW_TAG_THEN_ADDR = re.compile(
    r"\s*\[[^\]]*\]"                    # 공백? + [태그]
    r"\s*"                              # 공백
    r"(?="                              # 이후 주소 lookahead
    r"서울(?:특별)?시|경기도?|인천(?:광역)?시|부산(?:광역)?시"
    r"|대구(?:광역)?시|대전(?:광역)?시|광주(?:광역)?시"
    r"|울산(?:광역)?시|세종(?:특별자치)?시"
    r")"
)
# 단계2: '[태그] 없이' 공백 + 주소 형태 → 공백 앞에서 자름
#   예: '서울시티타워[전속] 서울시...' 에서 태그 제거 후 '서울시티타워 서울시...'
_CW_SPACE_THEN_ADDR = re.compile(
    r"\s+"                              # 공백 1개 이상
    r"(?="                              # 이후 주소 lookahead (행정구역 단위)
    r"서울(?:특별)?시|경기도?|인천(?:광역)?시|부산(?:광역)?시"
    r"|대구(?:광역)?시|대전(?:광역)?시|광주(?:광역)?시"
    r"|울산(?:광역)?시|세종(?:특별자치)?시"
    r")"
)


def _is_valid_building_name(name: str) -> bool:
    """건물명으로 인정할 수 있는지 검증.

    거부 조건:
    - 전화번호 패턴 포함 (010.xxxx.xxxx)
    - 금액/면적 등 숫자로 시작 (14,848.88A)
    - 한글·영문 글자 수 2자 미만
    - 권역/섹션 라벨 (Business District, LEASING PACKAGE 등)
    """
    if not name:
        return False
    s = name.strip()
    if _PHONE_RE.search(s):
        return False
    if _STARTS_NUMBER_RE.match(s):
        return False
    letters = [c for c in s if ('가' <= c <= '힣') or c.isalpha()]
    if len(letters) < 2:
        return False
    lower = s.lower()
    if any(k in lower for k in (
        "business district", "leasing package", "monthly pick",
        "lists", "team", "조직", "인원구성",
    )):
        return False
    return True


def _strip_cw_address(name: str) -> str:
    """C&W 건물명에 붙어있는 주소 부분 제거.

    예: '세미콜론수송[전속] 서울시종로구율곡로 2길19'
        → '세미콜론수송'
    주소 분리 후 [전속] 등 태그도 정리한다.
    cnw.py 어댑터에서 원문 주소를 별도 처리하므로 여기서는 건물명만 반환.
    """
    m = _CW_ADDRESS_SUFFIX.search(name)
    if m and m.start() > 0:
        name = name[: m.start()]
    # 남은 [전속], [단독전속] 태그 제거
    name = re.sub(r"\s*\[[^\]]*\]\s*$", "", name).strip()
    return name


def extract_building_name(page: fitz.Page) -> Optional[str]:
    """페이지에서 가장 큰 폰트 크기의 텍스트 span을 건물명으로 추출.

    변경사항 (2026-06-18):
    - 폰트 크기 상한(_MAX_FONT_SIZE_FOR_NAME=500pt) 추가: S1 PDF 아티팩트(2^32pt) 차단
    - C&W 건물명 주소 분리 (_strip_cw_address)

    반환값:
    - 건물명 문자열 (정규화됨, 주소 분리 완료)
    - 추출 불가 또는 유효성 실패 시 None
    """
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return None

    # 모든 줄(line)을 (대표 폰트 크기, y좌표, 텍스트) 로 수집.
    # 같은 줄의 span은 미리 합친다 ('케이스퀘어' span들 → 한 줄).
    lines: list[tuple[float, float, str]] = []
    for block in blocks:
        if block.get("type") != 0:  # 0 = text block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(sp.get("text", "") for sp in spans).strip()
            line_size = max((sp.get("size", 0.0) for sp in spans), default=0.0)
            bbox = line.get("bbox", (0, 0, 0, 0))
            y_top = bbox[1]

            # 폰트 크기 유효 범위 체크 (비정상 아티팩트 2^32pt 등 제거)
            if not line_text:
                continue
            if not (_MIN_FONT_SIZE_FOR_NAME <= line_size <= _MAX_FONT_SIZE_FOR_NAME):
                continue
            if any(exc.lower() in line_text.lower() for exc in _EXCLUDE_KEYWORDS):
                continue
            # 글자(한글/영문)가 하나도 없는 줄 제외
            if not any(c.isalpha() or '가' <= c <= '힣' for c in line_text):
                continue
            lines.append((line_size, y_top, line_text))

    if not lines:
        return None

    # 가장 큰 폰트 크기 기준 줄을 선택하되, **세로로 인접한 줄만** 연결한다.
    # 건물명이 '케이스퀘어'+'강남 II'처럼 2줄로 나뉘는 경우는 잇되,
    # 페이지 다른 위치의 같은 크기 글자('빌' 잔여 등)가 끼어드는 것을 방지.
    best_size = max(sz for sz, _, _ in lines)
    # 최대 크기 줄들을 y좌표 순으로 정렬
    big = sorted(
        [(y, txt) for sz, y, txt in lines if abs(sz - best_size) < 0.6],
        key=lambda x: x[0],
    )
    # 첫 줄에서 시작해, 세로 간격이 폰트 크기의 2배 이내인 연속 줄만 연결
    name_parts = [big[0][1]]
    prev_y = big[0][0]
    for y, txt in big[1:]:
        if y - prev_y <= best_size * 2.0:
            name_parts.append(txt)
            prev_y = y
        else:
            break  # 멀리 떨어진 같은 크기 글자는 건물명이 아님
    best_text = " ".join(name_parts)

    # C&W 건물명에 붙은 주소 분리
    best_text = _strip_cw_address(best_text)

    normalized = normalize_building_name(best_text)
    if not normalized:
        return None

    # 건물명 유효성 최종 검사
    return normalized if _is_valid_building_name(normalized) else None


# ---------------------------------------------------------------------------
# 페이지 그룹핑
# ---------------------------------------------------------------------------

def group_pages(
    doc: fitz.Document,
    broker: BrokerCode,
    page_types: Optional[list[str]] = None,
) -> list[PageGroup]:
    """doc의 전체 페이지를 건물 단위로 그룹핑한다.

    알고리즘:
    1. 각 페이지에서 건물명 추출 시도
    2. 이전 페이지와 건물명이 같으면 → 같은 그룹 유지
    3. 건물명이 달라지고 page_type이 'detail'이면 → 새 그룹 시작
    4. 건물명 추출 실패, 또는 non-detail 페이지 → 직전 그룹에 귀속

    핵심 개선 (2026-06-18):
    - 새 그룹은 page_type=='detail' 페이지에서만 시작
      → S1 목차, CW 지역 헤더 페이지가 새 건물 그룹을 생성하지 않음
    - extract_building_name의 폰트 크기 상한으로 2^32pt 아티팩트 차단
    - _is_valid_building_name으로 전화번호·금액 건물명 2차 차단

    Args:
        doc: PyMuPDF Document
        broker: 중개사 코드 (향후 브로커별 휴리스틱 분기용)
        page_types: 사전에 classify_page로 분류된 타입 리스트 (없으면 자체 호출 생략)

    Returns:
        PageGroup 리스트 (건물 단위, 순서 보존)
    """
    groups: list[PageGroup] = []
    current_group: Optional[PageGroup] = None
    current_name: Optional[str] = None

    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        page_type = page_types[page_idx] if page_types else "unknown"

        # toc/company_intro 페이지는 메타 그룹으로 분리 (건물 그룹에 귀속 X)
        if page_type in ("toc", "company_intro"):
            meta_group = PageGroup(
                building_name=f"__meta_{page_type}_{page_idx}",
                page_indices=[page_idx],
                page_types=[page_type],
            )
            groups.append(meta_group)
            continue

        # 핵심 보정: 'detail' 페이지에서만 새 건물 그룹을 시작한다.
        # cover/photo/floor_table 페이지는 새 그룹을 만들 수 없다.
        is_detail = (page_type == "detail")
        extracted_name = extract_building_name(page) if is_detail else None

        if is_detail and extracted_name and extracted_name != current_name:
            # 새 건물 시작 (detail + 유효한 건물명 + 이전과 다름)
            current_name = extracted_name
            current_group = PageGroup(
                building_name=extracted_name,
                page_indices=[page_idx],
                page_types=[page_type],
            )
            groups.append(current_group)
        elif current_group is not None:
            # 후속 페이지(사진/층별표/동일 건물명) → 직전 그룹에 귀속
            current_group.page_indices.append(page_idx)
            current_group.page_types.append(page_type)
        # else: 첫 건물 전 표지/목차 → 무시

    # 메타 그룹 제거 후 실제 건물 그룹만 반환
    return [
        g for g in groups
        if not g.building_name.startswith("__meta_")
    ]
