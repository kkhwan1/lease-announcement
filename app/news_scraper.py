# -*- coding: utf-8 -*-
"""뉴스 본문·og:image 스크래핑 (requests + BeautifulSoup).

realestate_info_news/utils/news_scraper.py 로직을 상업용 부동산
파이프라인에 맞게 이식. og:image 추출 기능을 추가했다.
"""

import html
import re

import requests
from bs4 import BeautifulSoup


# 요청 헤더 (봇 차단 방지)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    # brotli 제외 — requests가 디코드 못 해 본문 깨짐
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

_REQUEST_TIMEOUT = 5  # 초


def extract_title(soup: BeautifulSoup):
    """soup에서 기사 제목 추출 (우선순위 순).

    네이버 API title이 47자에서 잘리는 문제를 페이지 og:title로 보완.
    실패 시 None 반환 → 호출부가 API title로 폴백한다.
    """
    title = None
    # 1) 네이버 통합뉴스 정확 제목
    el = soup.select_one(".media_end_head_headline")
    if el:
        title = el.get_text(strip=True)
    # 2) og:title
    if not title:
        m = soup.find("meta", property="og:title")
        if m and m.get("content"):
            title = m["content"]
    # 3) twitter:title
    if not title:
        m = soup.find("meta", attrs={"name": "twitter:title"})
        if m and m.get("content"):
            title = m["content"]
    # 4) <title> 태그 (최후)
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        return None
    title = html.unescape(title).replace("\xa0", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return title or None


def extract_og_image(soup: BeautifulSoup):
    """soup에서 og:image URL 추출. 없으면 None."""
    m = soup.find("meta", property="og:image")
    if m and m.get("content"):
        return m["content"].strip() or None
    return None


def clean_element(element) -> None:
    """요소에서 불필요한 부분(스크립트·광고·댓글·네비 등)을 제거."""
    if not element:
        return

    for tag in element.find_all([
        "script", "style", "button", "nav", "aside", "footer", "header",
        "form", "input", "select", "textarea", "iframe", "embed", "menu",
        "noscript", "svg", "canvas", "object", "applet",
    ]):
        tag.decompose()

    # 댓글 영역
    for area in element.find_all(
        ["div", "section"],
        class_=re.compile(r"comment|reply|댓글|reply-box|comment-box", re.I),
    ):
        area.decompose()

    # 공유 버튼
    for area in element.find_all(
        ["div", "span", "a"],
        class_=re.compile(r"share|공유|sns|social|facebook|twitter|kakao", re.I),
    ):
        area.decompose()

    # 메뉴/네비게이션
    for area in element.find_all(
        ["div", "ul", "li", "section"],
        class_=re.compile(r"nav|menu|navigation|gnb|lnb|메뉴|네비|구독|rss|속보|sidebar", re.I),
    ):
        area.decompose()

    # 광고
    for area in element.find_all(
        ["div", "section"],
        class_=re.compile(r"ad|advertisement|광고|sponsor|promotion", re.I),
    ):
        area.decompose()

    # 관련뉴스/최신뉴스 섹션
    for area in element.find_all(
        ["div", "section", "ul", "ol"],
        class_=re.compile(r"related|latest|popular|news.*list|관련|최신|주요", re.I),
    ):
        area.decompose()

    # 언론사 정보 섹션
    for area in element.find_all(
        ["div", "section"],
        class_=re.compile(r"press|publisher|언론사|기자정보", re.I),
    ):
        area.decompose()


def _text_quality(text: str) -> float:
    """텍스트 품질 점수 (한글 비율·길이·문장 수 기반, 0~1)."""
    if not text or len(text) < 50:
        return 0.0
    korean = len(re.findall(r"[가-힣]", text))
    total = len(re.findall(r"[가-힣a-zA-Z0-9]", text))
    korean_ratio = korean / total if total > 0 else 0.0
    sentences = len(re.findall(r"[.!?。！？]\s*", text))
    return (
        min(len(text) / 2000, 1.0) * 0.4
        + min(korean_ratio * 2, 1.0) * 0.4
        + min(sentences / 10, 1.0) * 0.2
    )


def scrape_news_content(url: str, _title_out: dict = None):
    """뉴스 링크에서 본문 텍스트를 스크래핑한다.

    _title_out: dict가 주어지면 _title_out['title']에 og:title을 담는다
    (제목+본문을 한 번의 HTTP 요청으로 얻기 위한 내부 채널).

    실패 시 None 반환 (best-effort, 예외 전파 없음).
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # 제목 추출 — clean_element가 헤드라인을 제거하기 전에 먼저
        if _title_out is not None:
            _title_out["title"] = extract_title(soup)

        candidates = []  # (text, quality_score, source_label)

        # 방법 1: 네이버 뉴스 본문 선택자 (신형 우선)
        naver_selectors = [
            {"id": "dic_area"},
            {"id": "newsct_article"},
            {"class": re.compile(r"_article_content|newsct_article|article_content", re.I)},
            {"id": "articleBodyContents"},
            {"class": "_article_body_contents"},
            {"id": re.compile(r"articleBody", re.I)},
            {"class": re.compile(r"article.*body|body.*article", re.I)},
        ]
        for sel in naver_selectors:
            el = soup.find(["div", "article", "section"], sel)
            if el:
                clean_element(el)
                text = el.get_text(separator="\n", strip=True)
                if text and len(text) > 100:
                    candidates.append((text, _text_quality(text), "네이버뉴스"))
                    break

        # 방법 1.5: 언론사 CMS 표준 ID
        for cms_id in [
            "article-view-content-div", "news-contents", "post-content",
            "article_body", "articleCont", "news_body_area", "article-body-content",
        ]:
            el = soup.find(id=cms_id)
            if el:
                clean_element(el)
                text = el.get_text(separator="\n", strip=True)
                if text and len(text) > 100:
                    candidates.append((text, _text_quality(text), "CMS표준ID"))
                    break

        # 방법 2: <article> 태그
        art = soup.find("article")
        if art:
            clean_element(art)
            text = art.get_text(separator="\n", strip=True)
            if text and len(text) > 100:
                candidates.append((text, _text_quality(text), "article태그"))

        # 방법 3: <main> 태그
        main = soup.find("main")
        if main:
            clean_element(main)
            text = main.get_text(separator="\n", strip=True)
            if text and len(text) > 100:
                candidates.append((text, _text_quality(text), "main태그"))

        # 구조 기반 선택자를 우선, 휴리스틱(p태그/최장div)은 후순위
        _rank = {"네이버뉴스": 0, "CMS표준ID": 0, "article태그": 1, "main태그": 1,
                 "div선택자": 2, "p태그모음": 3, "최장div": 4}

        if not candidates:
            return None

        candidates.sort(key=lambda x: (_rank.get(x[2], 5), -x[1]))

        for raw_text, _q, _src in candidates:
            cleaned = _clean_content(raw_text)
            if cleaned:
                return cleaned
        return None

    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None


def _clean_content(content: str):
    """추출된 본문에서 UI·저작권·광고 라인을 제거."""
    unwanted_patterns = [
        r"Copyright.*", r"©.*", r"무단 전재.*", r"재배포.*",
        r"\[.*기자.*\]", r"기자\s*=\s*.*", r"저작권자.*",
        r"언론사홈 바로가기", r"기사 섹션 분류 안내",
        r"본문의 검색 링크는.*", r"AI 자동 인식.*", r"오분류 제보하기",
        r"▶.*기사.*보기", r"관련기사", r"인기키워드",
        r"구독하고.*메인에서.*만나보세요.*",
        r"이 기사를 본 이용자들이.*",
        r"프리미엄콘텐츠는.*",
        r"^\d{4}-\d{2}-\d{2}$",
        r"^https?://",
        r"^www\.",
        r"^#\w+$",
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ]
    lines = content.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line or len(line) <= 3:
            continue
        if re.match(r"^\d+$", line):
            continue
        skip = False
        for pat in unwanted_patterns:
            if re.search(pat, line, re.IGNORECASE):
                skip = True
                break
        if not skip:
            cleaned.append(line)

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result if len(result) >= 50 else None


def scrape_article(url: str) -> dict:
    """제목·본문·og:image를 한 번의 HTTP 요청으로 추출.

    Returns: {"title": str|None, "body": str|None, "thumbnail_url": str|None}
    실패 항목은 None (graceful).
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        if resp.status_code != 200:
            return {"title": None, "body": None, "thumbnail_url": None}

        soup = BeautifulSoup(resp.text, "lxml")
        title = extract_title(soup)
        thumbnail_url = extract_og_image(soup)
        body = scrape_news_content.__wrapped__(soup) if hasattr(scrape_news_content, "__wrapped__") else None

        # body를 별도로 추출 (soup 재사용)
        candidates = []
        for sel in [
            {"id": "dic_area"}, {"id": "newsct_article"},
            {"id": "articleBodyContents"}, {"class": "_article_body_contents"},
        ]:
            el = soup.find(["div", "article", "section"], sel)
            if el:
                clean_element(el)
                text = el.get_text(separator="\n", strip=True)
                if text and len(text) > 100:
                    candidates.append((text, _text_quality(text), "네이버뉴스"))
                    break

        art = soup.find("article")
        if art:
            clean_element(art)
            text = art.get_text(separator="\n", strip=True)
            if text and len(text) > 100:
                candidates.append((text, _text_quality(text), "article태그"))

        main = soup.find("main")
        if main:
            clean_element(main)
            text = main.get_text(separator="\n", strip=True)
            if text and len(text) > 100:
                candidates.append((text, _text_quality(text), "main태그"))

        candidates.sort(key=lambda x: ({"네이버뉴스": 0, "article태그": 1, "main태그": 1}.get(x[2], 5), -x[1]))
        body = None
        for raw_text, _q, _src in candidates:
            body = _clean_content(raw_text)
            if body:
                break

        return {"title": title, "body": body, "thumbnail_url": thumbnail_url}

    except Exception:
        return {"title": None, "body": None, "thumbnail_url": None}
