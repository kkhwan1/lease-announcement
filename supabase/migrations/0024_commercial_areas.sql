-- 0024_commercial_areas.sql
-- 건물별 발달상권 요약 (소상공인시장진흥공단 상가(상권)정보 API 기반)
-- 건물 1 : 상권 1 (최신값 upsert). 좌표 반경 점포 집계 결과를 담는다.
-- 건축물대장(0019)은 buildings 컬럼에 비정규화했으나, 상권은 기준월·업종분해·재조회가
-- 있는 동적 데이터라 전용 테이블로 분리한다.

create table if not exists building_commercial_areas (
    building_id   uuid primary key references buildings(id) on delete cascade,
    area_name     text,             -- 발달상권명 예: "교대역(법원.검찰청)"
    store_count   integer,          -- 총 점포수
    retail_count  integer,          -- 도소매 점포수
    service_count integer,          -- 서비스 점포수
    food_count    integer,          -- 외식 점포수
    radius_m      integer,          -- 집계 반경(m)
    base_period   text,             -- 데이터 기준 예: "2022.12"
    data_source   text default '소상공인시장진흥공단',
    updated_at    timestamptz default now()
);

comment on table building_commercial_areas is '건물 좌표 반경 발달상권 요약 (소상공인 상가정보 API)';

alter table building_commercial_areas enable row level security;

-- 0020 공개 읽기 패턴: anon SELECT-only (쓰기는 service_role CLI만)
drop policy if exists "anon read commercial" on building_commercial_areas;
create policy "anon read commercial"
    on building_commercial_areas
    for select
    to anon
    using (true);
