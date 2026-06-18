-- 0012_views.sql
-- 검색 뷰: v_current_vacancies
-- is_latest 스냅샷 + 층별공실 + 임대조건 평탄화.
-- "GBD, 전용 100~300㎡, 임대료 ≤ X, 즉시입주" 질의 대응.
-- 성능 문제 발생 시 MATERIALIZED VIEW로 전환 (refresh 전략 별도 결정).

begin;

-- security_invoker: 조회자 권한/RLS로 실행 (기반 테이블 RLS 적용 보장)
create or replace view v_current_vacancies
with (security_invoker = true)
as
select
    -- 건물 마스터
    b.id                        as building_id,
    b.name                      as building_name,
    b.district,
    b.address_road,
    b.station_area,
    b.floors_above,
    b.floors_below,
    b.gross_area_sqm,
    b.gross_area_pyeong,
    b.ev_count,
    b.completed_year,
    b.ceiling_height_m,
    b.efficiency_ratio,
    b.parking_total,
    b.features_raw,

    -- 스냅샷 (최신 1건)
    ls.id                       as snapshot_id,
    ls.broker_id,
    br.code                     as broker_code,
    br.name                     as broker_name,
    ls.snapshot_month,

    -- 층별 공실
    fa.id                       as floor_availability_id,
    fa.floor_label,
    fa.floor_number,
    fa.is_total_row,
    fa.exclusive_area_sqm,
    fa.exclusive_area_pyeong,
    fa.lease_area_sqm,
    fa.lease_area_pyeong,
    fa.availability_kind,
    fa.availability_raw,
    fa.available_from,

    -- 임대조건 (스냅샷당 첫 번째 조건, scope_label 기준 정렬)
    rt.scope_label              as rent_scope_label,
    rt.deposit_per_pyeong,
    rt.deposit_per_sqm,
    rt.rent_per_pyeong,
    rt.rent_per_sqm,
    rt.maintenance_per_pyeong,
    rt.maintenance_per_sqm,

    -- 출처 문서
    sd.filename                 as source_filename,
    sd.issue_period             as source_period

from buildings b
join listing_snapshots ls
    on ls.building_id = b.id
    and ls.is_latest  = true
join brokers br
    on br.id = ls.broker_id
join floor_availabilities fa
    on fa.listing_snapshot_id = ls.id
    and not fa.is_total_row     -- Total/계 행 제외
left join lateral (
    -- 스냅샷별 대표 임대조건 1건 (scope_label nulls last 정렬)
    select
        rt2.scope_label,
        rt2.deposit_per_pyeong,
        rt2.deposit_per_sqm,
        rt2.rent_per_pyeong,
        rt2.rent_per_sqm,
        rt2.maintenance_per_pyeong,
        rt2.maintenance_per_sqm
    from rent_terms rt2
    where rt2.listing_snapshot_id = ls.id
    order by rt2.scope_label nulls last
    limit 1
) rt on true
left join source_documents sd
    on sd.id = ls.source_document_id
;

-- 뷰에는 RLS 직접 설정 불가 — 기반 테이블 RLS가 적용됨.
-- (buildings, listing_snapshots 등 모두 authenticated 정책 적용 완료)

commit;
