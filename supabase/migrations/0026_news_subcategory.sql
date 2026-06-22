-- 0026_news_subcategory.sql
-- 뉴스 2축 분류 개편: sector(자산타입) × subcategory(동향 유형).
-- sector는 office/retail/hotel/logistics/datacenter (lease 제거, datacenter 추가 — 수집기에서 처리).
-- subcategory: tenant(임차동향)/landlord(임대동향)/deal(매매·투자)/general(일반).

begin;

alter table news_articles
    add column if not exists subcategory text;

comment on column news_articles.subcategory is
    '동향 소분류: tenant(임차)/landlord(임대)/deal(매매·투자)/general(일반).';

-- 탭별(섹터×서브) 최신순 조회 최적화
create index if not exists idx_news_sector_sub_published
    on news_articles (sector, subcategory, published_at desc);

-- 뷰에 subcategory 노출 추가 (컬럼 중간 삽입이라 drop+create 필요)
drop view if exists v_news_feed;
create view v_news_feed
with (security_invoker = on) as
select
    id,
    sector,
    subcategory,
    title,
    description,
    press,
    thumbnail_url,
    coalesce(original_link, naver_link) as display_link,
    published_at
from news_articles;

commit;
