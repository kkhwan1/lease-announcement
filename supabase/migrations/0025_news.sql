-- 0025_news.sql
-- 부동산 뉴스 피드. 네이버 뉴스 검색 API로 수집해 섹터별로 분류 저장.
-- 수집기(Python)는 service_role로 쓰기, anon은 SELECT만(0020 패턴 합류).
-- 웹은 v_news_feed 뷰만 읽음 — 네이버 키는 웹에 일절 없음(수집기 전용).

begin;

create table if not exists news_articles (
    id            uuid primary key default gen_random_uuid(),
    -- 섹터 코드: office/lease/retail/hotel/logistics ('전체'는 파생 탭, 미저장)
    sector        text        not null,
    title         text        not null,
    description   text,                     -- 네이버 description (태그 제거 후)
    body          text,                     -- 원문 스크래핑 본문 일부(best-effort)
    press         text,                     -- 언론사명(originallink 도메인 추정)
    thumbnail_url text,                      -- 원문 og:image(best-effort)
    original_link text,                      -- 원본 언론사 기사 URL(네이버 originallink)
    naver_link    text        not null,      -- 네이버 뉴스 URL(폴백, 항상 존재)
    -- 멱등 키: sha256(정규화 originallink or link). 재수집/섹터중복 시 중복 행 0.
    link_hash     text        not null unique,
    published_at  timestamptz,               -- 네이버 pubDate(RFC1123) 파싱
    fetched_at    timestamptz not null default now()
);

comment on table news_articles is
    '부동산 뉴스 피드(네이버 검색 API 수집). 기사당 1행, 첫 분류 섹터 유지.';

-- 탭별 최신순 조회 최적화. '전체' 탭은 published_at desc만 사용.
create index if not exists idx_news_sector_published
    on news_articles (sector, published_at desc);

-- RLS: anon SELECT만 (0020 화이트리스트 합류). 쓰기 정책 없음 = anon 쓰기 차단.
alter table news_articles enable row level security;
create policy "anon read news_articles"
    on news_articles for select to anon using (true);

-- 웹 화면 전용 뷰. security_invoker=on → 조회자(anon) RLS 상속(0021 컨벤션).
-- 노출 컬럼 화이트리스트(fetched_at 숨김) + display_link 폴백을 DB에서 계산.
create or replace view v_news_feed
with (security_invoker = on) as
select
    id,
    sector,
    title,
    description,
    press,
    thumbnail_url,
    coalesce(original_link, naver_link) as display_link,
    published_at
from news_articles;

commit;
