# -*- coding: utf-8 -*-
"""네이버 뉴스 검색 API 호출 + 섹터/소분류 분류 + 수집 파이프라인.

2축 분류:
  1축 sector   — classify_sector(title, desc) -> str|None
  2축 subcategory — classify_subcategory(title, desc) -> str
"""

from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import time
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse, urlunparse

import httpx

from app.news_keywords import (
    EXCLUDE_TERMS, SECTOR_INCLUDE, SECTOR_QUERIES, SUBCATEGORY_KEYWORDS,
)
from app.news_scraper import scrape_article

logger = logging.getLogger(__name__)

_NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

# 도메인→언론사명 축약 매핑 (best-effort)
_DOMAIN_PRESS_MAP: dict[str, str] = {
    "n.news.naver.com": "네이버뉴스",
    "news.naver.com": "네이버뉴스",
    "www.edaily.co.kr": "이데일리",
    "edaily.co.kr": "이데일리",
    "www.hankyung.com": "한국경제",
    "hankyung.com": "한국경제",
    "www.mk.co.kr": "매일경제",
    "mk.co.kr": "매일경제",
    "www.chosun.com": "조선일보",
    "chosun.com": "조선일보",
    "www.joongang.co.kr": "중앙일보",
    "joongang.co.kr": "중앙일보",
    "www.donga.com": "동아일보",
    "donga.com": "동아일보",
    "www.hani.co.kr": "한겨레",
    "hani.co.kr": "한겨레",
    "biz.chosun.com": "조선비즈",
    "www.bizwatch.co.kr": "비즈워치",
    "bizwatch.co.kr": "비즈워치",
    "www.newspim.com": "뉴스핌",
    "newspim.com": "뉴스핌",
    "www.thebell.co.kr": "더벨",
    "thebell.co.kr": "더벨",
    "www.fn.co.kr": "파이낸셜뉴스",
    "fn.co.kr": "파이낸셜뉴스",
    "www.inews24.com": "아이뉴스24",
    "www.mt.co.kr": "머니투데이",
    "mt.co.kr": "머니투데이",
    "news.mt.co.kr": "머니투데이",
    "www.sedaily.com": "서울경제",
    "sedaily.com": "서울경제",
    "www.news1.kr": "뉴스1",
    "news1.kr": "뉴스1",
    "www.yna.co.kr": "연합뉴스",
    "yna.co.kr": "연합뉴스",
    "www.newsis.com": "뉴시스",
    "newsis.com": "뉴시스",
}

# 제목에 섹터 키워드가 없으면 드롭 — 본문 곁다리 언급으로 인한 오분류 차단.
# hotel/logistics/datacenter/retail: 자영업·기술·기업 기사가 본문에 섹터어를
# 스쳐도 제목 무관하면 제외(예: "헬스장 지하상가 샐러드빵" → retail 아님).
_TITLE_KW_REQUIRED_SECTORS = {"hotel", "logistics", "datacenter", "retail"}


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def clean_html(text: str) -> str:
    """html.unescape + HTML 태그 제거."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pubdate(s: str) -> Optional[str]:
    """RFC 2822 날짜 문자열 → ISO 8601. 실패 시 None."""
    try:
        dt = parsedate_to_datetime(s)
        return dt.isoformat()
    except Exception:
        return None


def normalize_url(url: str) -> str:
    """URL 정규화: 쿼리스트링 제거 + 소문자 호스트."""
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc.lower(), p.path, "", "", ""))
    except Exception:
        return url.lower()


def link_hash(url: str) -> str:
    """정규화된 URL의 SHA-256 헥스다이제스트 (멱등 키)."""
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def press_from_url(url: str) -> Optional[str]:
    """URL 도메인에서 언론사명 추정 (best-effort)."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if domain in _DOMAIN_PRESS_MAP:
            return _DOMAIN_PRESS_MAP[domain]
        full = f"www.{domain}"
        if full in _DOMAIN_PRESS_MAP:
            return _DOMAIN_PRESS_MAP[full]
        parts = domain.split(".")
        for i in range(1, len(parts)):
            short = ".".join(parts[i:])
            if short in _DOMAIN_PRESS_MAP:
                return _DOMAIN_PRESS_MAP[short]
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1축: 섹터 분류
# ---------------------------------------------------------------------------

def classify_sector(title: str, desc: str) -> Optional[str]:
    """제목+설명에서 섹터를 분류한다.

    EXCLUDE_TERMS 중 하나라도 걸리면 None(드롭).
    SECTOR_INCLUDE core(1.0점)/general(0.5점) 가중 스코어 최고 섹터 반환.

    정밀도 규칙 (제목에 core 매칭 없을 때):
    1. 최소 스코어 1.5 필요
    2. 설명에 core 최소 1개 필요 (general 단독 1.5 달성 차단)
    3. hotel/logistics/datacenter: 제목에 섹터 키워드 없으면 드롭
       (로펌·AI 기사 설명 곁다리 언급 차단)
    """
    title_lower = title.lower()
    desc_lower = desc.lower()
    full_text = f"{title_lower} {desc_lower}"

    # 배제 키워드 체크
    for term in EXCLUDE_TERMS:
        if term.lower() in full_text:
            return None

    scores: dict[str, float] = {}
    title_core_hits: dict[str, int] = {}

    for sector, kw_dict in SECTOR_INCLUDE.items():
        score = 0.0
        title_core = 0
        for kw in kw_dict.get("core", []):
            k = kw.lower()
            if k in title_lower:
                score += 1.0
                title_core += 1
            elif k in desc_lower:
                score += 1.0
        for kw in kw_dict.get("general", []):
            if kw.lower() in full_text:
                score += 0.5
        if score > 0:
            scores[sector] = score
            title_core_hits[sector] = title_core

    if not scores:
        return None

    best = max(scores, key=lambda s: scores[s])
    best_score = scores[best]

    # 제목에 core 매칭 없을 때 추가 검증
    if title_core_hits.get(best, 0) == 0:
        # 1) 최소 스코어
        if best_score < 1.5:
            return None
        # 2) 설명부 core 최소 1개 (general 단독 조합 차단)
        desc_core_hits = sum(
            1 for kw in SECTOR_INCLUDE[best].get("core", [])
            if kw.lower() in desc_lower
        )
        if desc_core_hits == 0:
            return None
        # 3) hotel/logistics/datacenter: 제목에 섹터 키워드 필수
        if best in _TITLE_KW_REQUIRED_SECTORS:
            title_any = sum(
                1 for kw in (
                    SECTOR_INCLUDE[best].get("core", [])
                    + SECTOR_INCLUDE[best].get("general", [])
                )
                if kw.lower() in title_lower
            )
            if title_any == 0:
                return None

    return best


# ---------------------------------------------------------------------------
# 2축: 소분류 분류
# ---------------------------------------------------------------------------

def classify_subcategory(title: str, desc: str) -> str:
    """제목+설명에서 subcategory를 분류한다.

    SUBCATEGORY_KEYWORDS의 tenant/landlord/deal 스코어 계산:
    - 제목 매칭: 2.0점, 설명 매칭: 1.0점
    최고 subcategory 반환. 동점 시 deal > landlord > tenant 우선.
    셋 다 0이면 "general".
    """
    title_lower = title.lower()
    desc_lower = desc.lower()

    scores: dict[str, float] = {sub: 0.0 for sub in SUBCATEGORY_KEYWORDS}
    for sub, keywords in SUBCATEGORY_KEYWORDS.items():
        for kw in keywords:
            k = kw.lower()
            if k in title_lower:
                scores[sub] += 2.0
            elif k in desc_lower:
                scores[sub] += 1.0

    # 동점 우선순위: deal > landlord > tenant
    _priority = ["deal", "landlord", "tenant"]
    best_score = max(scores.values())
    if best_score == 0.0:
        return "general"

    for sub in _priority:
        if scores[sub] == best_score:
            return sub

    return "general"


# ---------------------------------------------------------------------------
# 네이버 API 호출
# ---------------------------------------------------------------------------

def fetch_naver_news(query: str, display: int = 100, sort: str = "date") -> list[dict]:
    """네이버 뉴스 검색 API 호출 → items 리스트 반환.

    실패 시 [] 반환 (호출부가 드롭).
    환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필수.
    """
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정 — 검색어 '%s' 건너뜀", query)
        return []

    params = {"query": query, "display": min(display, 100), "sort": sort}
    try:
        resp = httpx.get(
            _NAVER_NEWS_URL,
            params=params,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning("네이버 API HTTP %s (query=%s)", resp.status_code, query)
            return []
        return resp.json().get("items", [])
    except Exception as exc:
        logger.warning("네이버 API 호출 예외 (query=%s): %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# 전체 수집
# ---------------------------------------------------------------------------

def collect_all(pages: int = 1, scrape_body: bool = True) -> list[dict]:
    """섹터 × 검색어 루프로 기사를 수집하고 news_articles row dict 목록을 반환.

    각 row에 sector(1축) + subcategory(2축)가 모두 채워진다.
    """
    rows: list[dict] = []
    seen_hashes: set[str] = set()

    for sector, queries in SECTOR_QUERIES.items():
        for query in queries:
            for _page in range(pages):
                items = fetch_naver_news(query, display=100, sort="date")
                if not items:
                    break

                for item in items:
                    title_raw = clean_html(item.get("title", ""))
                    desc_raw = clean_html(item.get("description", ""))
                    naver_link = item.get("link", "")
                    original_link = item.get("originallink", "") or naver_link

                    if not naver_link:
                        continue

                    # 1축 섹터 분류 (None이면 드롭)
                    assigned_sector = classify_sector(title_raw, desc_raw)
                    if assigned_sector is None:
                        continue

                    # link_hash 중복 제거
                    lh = link_hash(naver_link)
                    if lh in seen_hashes:
                        continue
                    seen_hashes.add(lh)

                    # 본문·og:image 스크래핑 (best-effort)
                    scraped_title = None
                    body = None
                    thumbnail_url = None
                    if scrape_body and original_link:
                        try:
                            result = scrape_article(original_link)
                            scraped_title = result.get("title")
                            body = result.get("body")
                            thumbnail_url = result.get("thumbnail_url")
                        except Exception:
                            pass

                    final_title = scraped_title or title_raw

                    # 2축 소분류 분류 (API title 기준 — 스크래핑 전 확정)
                    assigned_sub = classify_subcategory(title_raw, desc_raw)

                    row: dict = {
                        "sector": assigned_sector,
                        "subcategory": assigned_sub,
                        "title": final_title,
                        "description": desc_raw or None,
                        "body": body or None,
                        "press": press_from_url(original_link),
                        "thumbnail_url": thumbnail_url or None,
                        "original_link": original_link or None,
                        "naver_link": naver_link,
                        "link_hash": lh,
                        "published_at": parse_pubdate(item.get("pubDate", "")),
                    }
                    rows.append(row)

                time.sleep(0.1)

    logger.info("collect_all 완료: 총 %d건 수집 (scrape_body=%s)", len(rows), scrape_body)
    return rows
