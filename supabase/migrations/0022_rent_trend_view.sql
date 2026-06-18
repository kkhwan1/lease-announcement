-- 0022_rent_trend_view.sql
-- 임대료 추이: 모든 월 스냅샷 × rent_terms. building_id 필터로 월별 추이 조회.
-- is_latest 무관 — 과거 월 스냅샷도 포함해 시계열을 만든다.

begin;

create or replace view v_rent_trend
with (security_invoker = on) as
select
    ls.building_id,
    br.code            as broker,
    ls.snapshot_month,
    rt.scope_label,
    rt.rent_per_pyeong,
    rt.maintenance_per_pyeong,
    rt.deposit_per_pyeong
from listing_snapshots ls
join brokers br        on br.id = ls.broker_id
join rent_terms rt     on rt.listing_snapshot_id = ls.id
where rt.rent_per_pyeong is not null
order by ls.building_id, ls.snapshot_month;

commit;
