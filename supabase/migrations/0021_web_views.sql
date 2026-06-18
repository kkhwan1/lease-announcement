-- 0021_web_views.sql
-- 웹 화면 전용 평탄화 뷰. security_invoker=on → 조회자 권한(anon RLS) 상속.

begin;

-- 건물별 공실수 + 최저 평당임대료 + 대표 썸네일 + 좌표 (홈/검색 카드)
create or replace view v_buildings_summary
with (security_invoker = on) as
select
    b.id                          as building_id,
    b.name,
    b.district,
    b.address_road,
    b.latitude,
    b.longitude,
    b.completed_year,
    b.floors_above,
    b.floors_below,
    coalesce(fa.vacancy_count, 0)  as vacancy_count,
    fa.min_rent_per_pyeong,
    img.thumbnail_path
from buildings b
-- 공실수: floor_availabilities만 집계 (rent_terms와 분리해 곱집합 방지)
left join lateral (
    select count(*) filter (where not f.is_total_row) as vacancy_count
    from listing_snapshots ls
    join floor_availabilities f on f.listing_snapshot_id = ls.id
    where ls.building_id = b.id and ls.is_latest
) fa on true
-- 최저 평당임대료: rent_terms만 집계 (별도 LATERAL — 곱집합 방지)
left join lateral (
    select min(rt.rent_per_pyeong) filter (where rt.rent_per_pyeong > 0) as min_rent_per_pyeong
    from listing_snapshots ls
    join rent_terms rt on rt.listing_snapshot_id = ls.id
    where ls.building_id = b.id and ls.is_latest
) rterm on true
-- 대표 썸네일: 종류 우선순위 + page_number(NULL last)
left join lateral (
    select bi.storage_path as thumbnail_path
    from building_images bi
    where bi.building_id = b.id
    order by case bi.kind
        when 'exterior' then 1 when 'lobby' then 2
        when 'interior' then 3 else 9 end,
        bi.page_number nulls last
    limit 1
) img on true;

-- 지도 핀 경량 (좌표 있는 건물만)
create or replace view v_buildings_map
with (security_invoker = on) as
select building_id, name, district, latitude, longitude, vacancy_count, min_rent_per_pyeong
from v_buildings_summary
where latitude is not null and longitude is not null;

-- 상세 한 방 조회 (건물 스펙 + 건축물대장 + 특장점)
create or replace view v_building_detail
with (security_invoker = on) as
select
    b.id as building_id, b.name, b.name_raw, b.district,
    b.address_road, b.address_raw, b.station_area,
    b.latitude, b.longitude,
    b.floors_above, b.floors_below,
    b.gross_area_sqm, b.gross_area_pyeong,
    b.efficiency_ratio, b.completed_year, b.ceiling_height_m,
    b.ev_count, b.parking_total, b.features_raw,
    b.main_purpose, b.building_coverage_ratio, b.floor_area_ratio,
    b.height_m, b.land_area_sqm, b.use_zone
from buildings b;

commit;
