"""정규화 유틸 — 한글 금액·면적·건물명·권역·입주시기·규모 파싱.

재사용 자산:
- _parse_korean_money: 임대안내문 자동화/app/excel_renderer.py에서 차용.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from app.schemas import AvailabilityKind, BusinessDistrict


# ---------------------------------------------------------------------------
# 한글 금액 파서 (임대안내문 자동화 프로젝트에서 차용)
# ---------------------------------------------------------------------------

_KOR_UNITS = {
    "조": 1_0000_0000_0000,
    "억": 1_0000_0000,
    "만": 1_0000,
    "천": 1_000,
    "백": 100,
}

_COMPOUND_UNITS = {
    "천만": 1_000 * 1_0000,
    "백만": 100 * 1_0000,
    "십만": 10 * 1_0000,
    "천억": 1_000 * 1_0000_0000,
    "백억": 100 * 1_0000_0000,
    "십억": 10 * 1_0000_0000,
}

_HANGUL_DIGIT = {
    "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5,
    "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9, "십": 10,
}


def parse_korean_money(s: str) -> Optional[int | float]:
    """'1억 4천만원' '1,400만원' '14,000,000원' '천만원' 같은 표기를 원 단위 정수로.

    - 단위만 단독('천만원') → 1 × 단위로 해석
    - 한자/한글 숫자('일억', '삼천만') 처리
    - S1 셀 병합 아티팩트: '8,528,000빌' 같이 끝에 한글이 붙는 경우 제거.
      단 '1억4천만'처럼 정상 한글 단위는 보존.
    - 잔여 문자가 남으면 안전하게 None
    """
    s = s.strip().rstrip("원").strip()
    if not s:
        return None

    # S1 셀 병합 아티팩트 제거: 숫자(+콤마+소수점) 뒤에 붙는 한글 글자 제거.
    # 단, '억/만/천/백/조' 같은 한글 단위 앞에 붙은 숫자는 건드리지 않는다.
    # 패턴: 숫자(콤마포함)로 끝나는 문자열 뒤에 오는 한글 1-2글자 (단위 아닌 것)
    # 예: '8,528,000빌' → '8,528,000',  '35,940,000빌딩' → '35,940,000'
    # '1억4천만' 같은 경우는 숫자 뒤 바로 한글 단위이므로 아래 로직에서 정상 처리됨
    _MONEY_ARTIFACT = re.compile(
        r"^([\d,]+(?:\.\d+)?)\s*([가-힣]{1,3})$"
    )
    m_artifact = _MONEY_ARTIFACT.match(s)
    if m_artifact:
        suffix = m_artifact.group(2)
        # 한글 단위 키워드(억/만/천/백/조)가 포함된 경우는 정상 금액 표기 → 건드리지 않음
        _KOR_UNIT_CHARS = set("조억만천백")
        if not any(ch in suffix for ch in _KOR_UNIT_CHARS):
            # '빌', '딩', '빌딩', '층' 등 아티팩트 → 숫자 부분만 추출
            s = m_artifact.group(1)

    # 공백으로 분리된 여러 숫자 토큰 처리 (C&W 셀 병합: '144,300 44,700').
    # 토큰이 모두 순수 숫자(콤마 포함)면 → 첫 번째 값만 취한다.
    # ('1억 4천만'처럼 한글 단위가 섞인 경우는 아래 일반 경로로 진행)
    tokens = s.split()
    if len(tokens) > 1 and all(re.fullmatch(r"[\d,]+(?:\.\d+)?", t) for t in tokens):
        s = tokens[0]

    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    # 순수 숫자
    try:
        v = float(s)
        return int(v) if v == int(v) else v
    except ValueError:
        pass

    # 한글 숫자를 아라비아 숫자로 치환 (단위 prefix만 1자리)
    for ko, num in _HANGUL_DIGIT.items():
        s = s.replace(ko, str(num))

    # 숫자 없는 단위 단독('천만', '억') → 앞에 1 붙임
    s = re.sub(r"^(천만|백만|십만|천억|백억|십억|[조억만천백])", r"1\1", s)

    pattern = re.compile(
        r"(\d+(?:\.\d+)?)(천만|백만|십만|천억|백억|십억|[조억만천백])"
    )
    matches = pattern.findall(s)
    if not matches:
        return None
    consumed = "".join(num + unit for num, unit in matches)
    if consumed != s:
        return None
    total = 0.0
    for num_str, unit in matches:
        mult = _COMPOUND_UNITS.get(unit) or _KOR_UNITS[unit]
        total += float(num_str) * mult
    return int(total) if total == int(total) else total


# ---------------------------------------------------------------------------
# 면적 파서
# ---------------------------------------------------------------------------

# 면적·금액 단위 환산 계수 (사용자 지정, 2026-06-18):
#   평 = ㎡ × 0.3025
#   ㎡ = 평 ÷ 0.3025  (= 평 × 3.305785…)
# 단일 진실 원천. 모든 ㎡↔평 변환은 이 상수를 사용한다.
PYEONG_PER_SQM = 0.3025
_SQM_PER_PYEONG = 1.0 / PYEONG_PER_SQM  # ≈ 3.305785


def parse_area(s: str, default_unit: str = "sqm") -> Tuple[Optional[float], Optional[float]]:
    """'628.33㎡(190.07평)' 또는 '190.07' 같은 입력에서 (㎡, 평) 분리.

    - ㎡+평 동시 → 그대로 반환 (명시 단위 우선)
    - ㎡만 → 평 = ㎡ / 3.305785
    - 평만 → ㎡ = 평 × 3.305785
    - 단위 없는 숫자만 → default_unit 기준 해석
        * default_unit='pyeong' : 한국 임대안내문 면적표(단위: 3.3㎡)는 값이 '평'
        * default_unit='sqm'    : 그 외 기본
    - 둘 다 없으면 → (None, None)
    """
    if not s:
        return None, None

    s = s.strip()

    # '628.33㎡(190.07평)' 패턴 — 단위가 명시되면 항상 그것을 신뢰
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*㎡.*?\(?\s*([\d,]+(?:\.\d+)?)\s*평\)?", s)
    if m:
        sqm = float(m.group(1).replace(",", ""))
        pyeong = float(m.group(2).replace(",", ""))
        return sqm, pyeong

    # ㎡만 있는 경우 → 평 = ㎡ × 0.3025
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*㎡", s)
    if m:
        sqm = float(m.group(1).replace(",", ""))
        return sqm, round(sqm * PYEONG_PER_SQM, 2)

    # '190.07평' 패턴 → ㎡ = 평 ÷ 0.3025
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*평", s)
    if m:
        pyeong = float(m.group(1).replace(",", ""))
        return round(pyeong / PYEONG_PER_SQM, 2), pyeong

    # 단위 없는 숫자만 → default_unit 기준
    m = re.match(r"^([\d,]+(?:\.\d+)?)$", s.strip())
    if m:
        val = float(m.group(1).replace(",", ""))
        if default_unit == "pyeong":
            return round(val / PYEONG_PER_SQM, 2), val
        return val, round(val * PYEONG_PER_SQM, 2)

    return None, None


# ---------------------------------------------------------------------------
# 건물명 정규화
# ---------------------------------------------------------------------------

# 로마숫자 ↔ 아라비아 숫자 변환 맵 (I~X)
_ROMAN_TO_ARABIC = {
    "VIII": "8", "VII": "7", "VI": "6",
    "IV": "4", "IX": "9",
    "III": "3", "II": "2",
    "I": "1", "V": "5", "X": "10",
}
_ARABIC_TO_ROMAN = {v: k for k, v in _ROMAN_TO_ARABIC.items() if len(k) > 1}
_ARABIC_TO_ROMAN.update({"1": "I", "5": "V", "10": "X"})

# 같은 음절이 연속 반복될 때 제거 ("빌딩딩" → "빌딩")
_SUFFIX_DEDUPE = re.compile(r"(빌딩|타워|딩|빌)\1+$")
# 에스원 PDF 아티팩트: 접미사 뒤에 '빌'/'딩' 한 글자가 덧붙는 경우
#   '태평로빌딩빌' → '태평로빌딩', '삼성본관빌딩빌' → '삼성본관빌딩'
_SUFFIX_ARTIFACT = re.compile(r"(빌딩|타워|센터|플라자)[빌딩]$")
# 불필요한 접미사 제거 패턴 (비교용 key에서만)
_SUFFIX_STRIP = re.compile(r"(빌딩|타워|건물|오피스|센터)$")


def normalize_building_name(s: str) -> str:
    """건물명 정규화.

    - 양쪽 공백 제거
    - 특수문자(·,. 등) 정리
    - 끝 음절 중복/아티팩트 제거 ('삼성본관빌딩빌' → '삼성본관빌딩')
    """
    if not s:
        return s
    s = s.strip()
    # 괄호 내 부가 설명 제거는 하지 않음 (건물명 일부일 수 있음)
    # 앞뒤 특수문자 정리
    s = re.sub(r"^[\s\-_·•]+|[\s\-_·•]+$", "", s)
    # 끝 음절 중복 제거 ('빌딩딩' → '빌딩')
    s = _SUFFIX_DEDUPE.sub(r"\1", s)
    # 접미사 뒤 덧붙은 한 글자 아티팩트 제거 ('빌딩빌' → '빌딩')
    s = _SUFFIX_ARTIFACT.sub(r"\1", s)
    return s


def building_match_key(s: str) -> str:
    """Entity Resolution 용 정규화 키 생성.

    - 공백·특수문자 제거
    - 소문자화
    - 로마숫자→아라비아 숫자로 통일 (비교 단순화)
    - 접미사('빌딩'/'타워') 제거
    """
    if not s:
        return ""
    key = s.strip()
    # 공백·특수문자 제거
    key = re.sub(r"[\s\-_·•.,\(\)\[\]]", "", key)
    # 로마숫자→아라비아 숫자 (긴 것부터 우선 치환)
    for roman, arabic in sorted(_ROMAN_TO_ARABIC.items(), key=lambda x: -len(x[0])):
        key = re.sub(rf"(?<![A-Z]){roman}(?![A-Z])", arabic, key)
    # 접미사 제거
    key = _SUFFIX_STRIP.sub("", key)
    return key.lower()


# ---------------------------------------------------------------------------
# 주소 정규화 (Entity Resolution 1차 키 — 사용자 결정 2026-06-18)
# ---------------------------------------------------------------------------
#
# 설계 근거: 건물명은 중개사마다 축약/확장이 제각각이라 불안정하지만,
# 주소(특히 도로명+건물번호)는 고정값이라 건물 동일성 판정의 가장 신뢰도 높은
# 키다. 따라서 Entity Resolution은 address_match_key(도로명+번호)를 1차 키로,
# building_match_key를 보조 키로 사용한다.

# 시/도 표기 통일 (축약형 → 표준형)
_SIDO_NORMALIZE = [
    (re.compile(r"^서울특별시|^서울시|^서울"), "서울특별시"),
    (re.compile(r"^부산광역시|^부산시|^부산"), "부산광역시"),
    (re.compile(r"^인천광역시|^인천시|^인천"), "인천광역시"),
    (re.compile(r"^대구광역시|^대구시|^대구"), "대구광역시"),
    (re.compile(r"^대전광역시|^대전시|^대전"), "대전광역시"),
    (re.compile(r"^광주광역시|^광주시"), "광주광역시"),
    (re.compile(r"^울산광역시|^울산시|^울산"), "울산광역시"),
    (re.compile(r"^세종특별자치시|^세종시"), "세종특별자치시"),
    (re.compile(r"^경기도|^경기"), "경기도"),
]

# 주소에서 건물명/전속 접두 표기 제거용
#   'XXX빌딩[전속] 서울시...' / '세미콜론수송[전속] 서울시...' → 시/도부터
_ADDR_PREFIX_JUNK = re.compile(
    r"^.*?(?=(?:서울|부산|인천|대구|대전|광주|울산|세종|경기|강원|충청|충북|충남|전라|전북|전남|경상|경북|경남|제주))"
)
# 지번 괄호 (역삼동) 제거
_ADDR_JIBUN_PAREN = re.compile(r"\([^)]*\)")
# 도로명 + 건물번호 패턴 (공백 유무 모두 허용): '강남대로 374', '세종대로73',
#   '율곡로 2길19', '테헤란로114길 38'.
#   도로명은 한글/영문 + (대로|로|길), 번호는 'N' 또는 'N길M'.
_ROAD_NUMBER = re.compile(
    r"([가-힣A-Za-z]+?(?:대로|로))"   # 도로명 (XX대로/XX로) — non-greedy
    r"\s*(\d+(?:길)?)"                # 첫 번호 또는 'N길'
    r"\s*(\d+)?"                      # (N길일 때) 뒤따르는 건물번호
)


def normalize_address(s: str) -> str:
    """주소 표시용 정규화.

    - 건물명/전속 접두 제거 (C&W '세미콜론수송[전속] 서울시...' → '서울시...')
    - 시/도 표준 표기로 통일 ('서울시' → '서울특별시')
    - 과도한 공백 정리
    - 지번 괄호는 보존 (표시용)
    """
    if not s:
        return ""
    addr = s.strip()
    # 건물명 접두 제거: 시/도명이 시작되는 지점부터
    m = _ADDR_PREFIX_JUNK.match(addr)
    if m and m.end() > 0 and m.end() < len(addr):
        addr = addr[m.end():]
    addr = addr.strip()
    # 시/도 표기 통일
    for pat, repl in _SIDO_NORMALIZE:
        if pat.match(addr):
            addr = pat.sub(repl, addr, count=1)
            break
    # 공백 정리
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def address_match_key(s: str) -> str:
    """Entity Resolution 1차 키 — 도로명 + 건물번호만 추출해 정규화.

    예:
      '서울특별시 강남구 강남대로 374(역삼동)' → '강남대로374'
      '서울시중구세종대로73'                    → '세종대로73'
      '세미콜론수송[전속] 서울시종로구율곡로 2길19' → '율곡로2길19'

    도로명+번호를 못 찾으면 시/도·공백·괄호 제거한 fallback 키 반환.
    """
    if not s:
        return ""
    addr = normalize_address(s)
    # 지번 괄호 제거
    addr_clean = _ADDR_JIBUN_PAREN.sub("", addr)
    # 행정구역(특별시/광역시/특별자치시/도 + 시/군/구) 접두 제거 →
    # 공백 없는 주소('서울특별시중구세종대로73')에서도 도로명 경계를 찾도록.
    addr_clean = re.sub(
        r"^(?:[가-힣]+(?:특별자치시|특별시|광역시|특별자치도|도))"  # 시/도
        r"\s*(?:[가-힣]+[시군구])?\s*(?:[가-힣]+[시군구])?",        # 시군구(최대 2단계)
        "",
        addr_clean,
    ).strip()

    m = _ROAD_NUMBER.search(addr_clean)
    if m:
        road = m.group(1)
        num1 = m.group(2) or ""
        num2 = m.group(3) or ""
        return f"{road}{num1}{num2}".replace(" ", "").lower()

    # fallback: 공백·특수문자·시군구 제거 후 소문자
    key = re.sub(r"[\s\-_·•.,\(\)\[\]]", "", addr_clean)
    return key.lower()


# ---------------------------------------------------------------------------
# 권역 분류
# ---------------------------------------------------------------------------

# 역명/주소 키워드 → BusinessDistrict 매핑
_DISTRICT_MAP: list[Tuple[BusinessDistrict, list[str]]] = [
    (BusinessDistrict.GBD, [
        "강남", "역삼", "삼성", "선릉", "테헤란",
        "학동", "논현", "신논현", "압구정", "청담",
    ]),
    (BusinessDistrict.CBD, [
        "시청", "광화문", "종각", "을지로", "명동",
        "청계천", "세종대로", "종로", "서울역",
    ]),
    (BusinessDistrict.YBD, [
        "여의도", "여의나루", "국회",
    ]),
    (BusinessDistrict.BBD, [
        "판교", "분당", "수내", "서현", "정자", "미금",
        "이매", "야탑", "판교역", "기흥",
    ]),
]


def classify_district(station_or_addr: str) -> BusinessDistrict:
    """역명/주소로 GBD/CBD/YBD/BBD/ETC 분류."""
    if not station_or_addr:
        return BusinessDistrict.ETC
    s = station_or_addr.strip()
    for district, keywords in _DISTRICT_MAP:
        for kw in keywords:
            if kw in s:
                return district
    return BusinessDistrict.ETC


# ---------------------------------------------------------------------------
# 입주시기 분류
# ---------------------------------------------------------------------------

# 날짜 패턴: '2026.12', '2026년 12월', '2027/01' 등
_DATE_PATTERNS = [
    re.compile(r"\d{4}[.\-/년]\s*\d{1,2}"),
    re.compile(r"\d{4}년"),
]


def classify_availability(s: str) -> Tuple[AvailabilityKind, str]:
    """입주시기 분류.

    - '즉시', '즉시입주' → IMMEDIATE
    - '협의', '협의후', '협의 후' → NEGOTIABLE
    - 날짜 포함 → BY_DATE
    - 그 외 → UNKNOWN
    """
    if not s:
        return AvailabilityKind.UNKNOWN, s
    raw = s.strip()
    lower = raw.replace(" ", "")

    if any(k in lower for k in ("즉시",)):
        return AvailabilityKind.IMMEDIATE, raw
    if any(k in lower for k in ("협의",)):
        return AvailabilityKind.NEGOTIABLE, raw
    for pattern in _DATE_PATTERNS:
        if pattern.search(raw):
            return AvailabilityKind.BY_DATE, raw

    return AvailabilityKind.UNKNOWN, raw


# ---------------------------------------------------------------------------
# 준공년도 파서
# ---------------------------------------------------------------------------

def parse_completed_year(s: str) -> Optional[int]:
    """준공 셀에서 4자리 연도(19xx/20xx)를 추출.

    천정고 등 다른 값이 섞여도('2.6m 2024년', '1976년(2009년 리모델링)') 올바른
    연도를 잡는다. 리모델링 연도가 함께 있으면 **원래 준공연도(가장 이른 연도)**를 반환.
    예:
      '2022년'              → 2022
      '2.6m 2024년'         → 2024   (천정고 '2.6'을 연도로 오인하지 않음)
      '1976년(2009년 리모델링)' → 1976  (준공이 우선, 리모델링 아님)
    """
    if not s:
        return None
    years = re.findall(r"(19\d{2}|20\d{2})", str(s))
    if not years:
        return None
    # 가장 이른 연도 = 최초 준공 (리모델링 연도는 보통 뒤·더 큼)
    return min(int(y) for y in years)


# ---------------------------------------------------------------------------
# 건물 규모 파서
# ---------------------------------------------------------------------------

def parse_scale(s: str) -> Tuple[Optional[int], Optional[int]]:
    """'B3 / 20F' 또는 '지하4층/지상26층' → (floors_above, floors_below).

    다양한 형식 지원:
    - 'B3 / 20F', 'B3/20F'
    - '지하3층/지상20층', '지하 3층 / 지상 20층'
    - '20F / B3'
    - '지상20층/지하3층'
    - '20층/지하3층'
    """
    if not s:
        return None, None

    s_clean = s.strip()

    # 영문 패턴: B{n} / {m}F
    # 'B3 / 20F' 또는 '20F / B3'
    m = re.search(r"B(\d+)\s*/\s*(\d+)\s*F", s_clean, re.IGNORECASE)
    if m:
        return int(m.group(2)), int(m.group(1))

    m = re.search(r"(\d+)\s*F\s*/\s*B(\d+)", s_clean, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))

    # 한글 패턴: 지하{n}층/지상{m}층
    above, below = None, None

    m_above = re.search(r"지상\s*(\d+)\s*층", s_clean)
    if m_above:
        above = int(m_above.group(1))

    m_below = re.search(r"지하\s*(\d+)\s*층", s_clean)
    if m_below:
        below = int(m_below.group(1))

    if above is not None or below is not None:
        return above, below

    # 순수 층수만 있는 경우: '20층'
    m = re.match(r"^(\d+)\s*층$", s_clean.strip())
    if m:
        return int(m.group(1)), None

    return None, None


# ---------------------------------------------------------------------------
# 주소 공백 정규화 (C&W식 공백없는 주소 → 지오코딩용)
# ---------------------------------------------------------------------------

# 시/도 명칭 (긴 것 우선 매칭). 축약형('서울시' 등)도 포함.
_SIDO_NAMES = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "강원도", "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
    "서울시", "부산시", "대구시", "인천시", "광주시", "대전시", "울산시",
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
]
# 긴 명칭 우선 매칭 (서울특별시 > 서울시 > 서울)
_SIDO_NAMES.sort(key=len, reverse=True)
_SIDO_PATTERN = "|".join(_SIDO_NAMES)

# 도로명 토큰: '구/군/시' 뒤에 이것이 이어질 때만 진짜 행정구역으로 인정
# → '달구벌대로'의 '달구'를 구로 오인하지 않음.
_ROAD_TOKEN = r"(?=[가-힣]*(?:대로|로|길|동|읍|면|가|\d))"

# 도(경기도 등) + 일반시(수원시 등) + 구(팔달구). 3단계 행정구역.
# 일반시는 '광역시/특별시/특별자치시'가 아니어야 함(그건 시/도 명칭) →
# 시 앞 글자에 '광역/특별/자치'가 붙지 않도록 (?<!광역)(?<!특별) 등으로 차단.
_DO_SI_GU_RE = re.compile(
    rf"^({_SIDO_PATTERN})\s*((?:(?!광역|특별|자치)[가-힣]){{1,3}}시)"
    rf"\s*([가-힣]{{1,3}}(?:구|군)){_ROAD_TOKEN}\s*"
)
# 시/도 직후의 구/군 (2단계).
_SIDO_GU_RE = re.compile(
    rf"^({_SIDO_PATTERN})\s*([가-힣]{{1,3}}(?:구|군)){_ROAD_TOKEN}\s*"
)


def insert_address_spacing(address: Optional[str]) -> Optional[str]:
    """C&W식 공백없는 주소에 시·도/구 사이 공백을 삽입.

    '서울특별시종로구율곡로 2길19'  → '서울특별시 종로구 율곡로 2길19'
    '서울시성동구뚝섬로17가길49'    → '서울시 성동구 뚝섬로17가길49'
    '경기도수원시팔달구권광로205'   → '경기도 수원시 팔달구 권광로205'
    이미 공백이 정상이면 그대로 반환. 구 분리가 모호하면 시/도만 띄우고
    나머지는 지오코더의 자체 파싱에 맡긴다.
    """
    if not address:
        return address
    s = address.strip()

    # 이미 시/도 뒤에 공백이 있으면(정상 주소) 손대지 않는다.
    if re.match(rf"^({_SIDO_PATTERN})\s", s):
        return s

    # 3단계: 도 + 일반시 + 구
    m3 = _DO_SI_GU_RE.match(s)
    if m3:
        sido, si, gu = m3.group(1), m3.group(2), m3.group(3)
        rest = s[m3.end():].strip()
        return f"{sido} {si} {gu} {rest}".strip()

    # 2단계: 시/도 + 구/군
    m = _SIDO_GU_RE.match(s)
    if m:
        sido, gu = m.group(1), m.group(2)
        rest = s[m.end():].strip()
        return f"{sido} {gu} {rest}".strip()

    # 구 분리 실패 시: 시/도 명칭만이라도 띄워준다 (지오코더 자체 파싱에 위임).
    m2 = re.match(rf"^({_SIDO_PATTERN})(?=[가-힣])", s)
    if m2:
        sido = m2.group(1)
        rest = s[m2.end():].strip()
        return f"{sido} {rest}".strip()
    return s


# 지번 꼬리 노이즈(필지/일원 등)와 복수지번을 정리하는 패턴
_ADDR_TAIL_NOISE_RE = re.compile(
    r"\s*(?:외\s*\d*\s*필지|외\s*일원|일원|번지|[\[(].*?[\])])\s*$"
)
# 복수지번: '278-2, 278-3, 278-57' / '278-2 외 278-3' 의 첫 지번만
_MULTI_JIBUN_RE = re.compile(r"(\d+(?:-\d+)?)(?:\s*,\s*\d+(?:-\d+)?)+")
# 동/가 + 지번이 공백 없이 붙은 경우 띄우기: '성수동2가278-2' → '성수동2가 278-2'
_DONG_JIBUN_GLUE_RE = re.compile(r"([가-힣]동\d*가?|[가-힣]+동|\d+가)(\d+(?:-\d+)?)\b")
# 도로명 + 건물번호 공백 없이 붙은 경우 띄우기: '황새울로258번길29' → '황새울로258번길 29'
_ROAD_BLDGNO_GLUE_RE = re.compile(r"((?:대로|[가-힣]로)\d*번?길)(\d+)\b")
# 건물명 접두 + [전속]/[직거래] 등 대괄호 마커가 있으면 그 뒤 시/도부터 사용
_BRACKET_BEFORE_SIDO_RE = re.compile(
    r"^.*?\][^가-힣]*(?=(?:서울|부산|인천|대구|대전|광주|울산|세종|경기|강원|충청|충북|충남|전라|전북|전남|경상|경북|경남|제주))"
)


def clean_address_for_geocoding(address: Optional[str]) -> Optional[str]:
    """지오코딩 성공률을 높이기 위한 주소 클렌징.

    원본 주소로 지오코딩이 실패할 때 폴백으로 시도할 정리된 주소를 만든다.
    - 건물명/전속 접두 제거 + 시도 표준화 (normalize_address 재사용)
    - '외2필지', '일원', '번지', '[전속]…' 등 꼬리 노이즈 제거
    - 복수지번('278-2, 278-3, 278-57')은 첫 지번만 사용
    - 동/가와 지번이 붙은 경우 띄어쓰기 ('성수동2가278-2' → '성수동2가 278-2')
    - 마지막에 insert_address_spacing으로 시/도/구 공백 보정

    Returns:
        정리된 주소. 입력이 비면 None. 원본과 동일하면 그대로 반환.
    """
    if not address:
        return None
    s = normalize_address(address)
    # 대괄호 마커([전속] 등) 뒤에 실제 시/도가 또 나오면 그 지점부터 사용
    # ('서울특별시티타워[전속] 서울시중구남대문로5가581' → '서울시중구남대문로5가581')
    mb = _BRACKET_BEFORE_SIDO_RE.match(s)
    if mb and mb.end() < len(s):
        s = s[mb.end():].strip()
        s = normalize_address(s)
    # 복수지번 → 첫 지번
    s = _MULTI_JIBUN_RE.sub(lambda m: m.group(1), s)
    # 꼬리 노이즈 반복 제거 (예: '...번지일원' 처럼 중첩될 수 있음)
    prev = None
    while prev != s:
        prev = s
        s = _ADDR_TAIL_NOISE_RE.sub("", s).strip()
    # 도로명 + 건물번호 붙음 분리 ('황새울로258번길29' → '황새울로258번길 29')
    s = _ROAD_BLDGNO_GLUE_RE.sub(r"\1 \2", s)
    # 동/가 + 지번 붙음 분리
    s = _DONG_JIBUN_GLUE_RE.sub(r"\1 \2", s)
    # 시/도 없이 일반시+구로 시작하는 경우 분리 ('성남시분당구…' → '성남시 분당구 …')
    ms = re.match(r"^((?:(?!광역|특별|자치)[가-힣]){2,3}시)([가-힣]{1,3}(?:구|군))(?=[가-힣])", s)
    if ms:
        s = f"{ms.group(1)} {ms.group(2)} {s[ms.end():].strip()}".strip()
    # 시/도/구 공백 보정
    s = insert_address_spacing(s) or s
    s = re.sub(r"\s+", " ", s).strip()
    return s or None
