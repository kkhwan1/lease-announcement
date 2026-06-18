-- 0008_floor_availabilities.sql
-- 층별 공실 테이블 (사용자 1순위 데이터).
-- listing_snapshot 1건 : floor_availabilities N건.
-- is_total_row: 'Total'/'계' 집계 행 구분 플래그.
-- 범위검색 부분 인덱스: where not is_total_row (집계 행 제외 실데이터만).

begin;

create table floor_availabilities (
    id                      uuid            primary key default gen_random_uuid(),
    listing_snapshot_id     uuid            not null references listing_snapshots(id) on delete cascade,

    -- 층 식별
    floor_label             text            not null,   -- 원문 ('18층', 'B1', '기준층')
    floor_number            integer,                    -- 정수 파싱 결과 (정렬/범위검색용)
    is_total_row            boolean         not null default false,  -- Total/계 행 여부

    -- 면적 (㎡ 정규화 + 평 원문 병존)
    exclusive_area_sqm      numeric(12,2),  -- 전용면적 ㎡
    exclusive_area_pyeong   numeric(12,2),  -- 전용면적 평 (원문)
    lease_area_sqm          numeric(12,2),  -- 임대면적 ㎡
    lease_area_pyeong       numeric(12,2),  -- 임대면적 평 (원문)

    -- 입주 가능 시점
    availability_kind       availability_kind not null default 'unknown',
    availability_raw        text,           -- '즉시', '협의 후 1개월' 원문
    available_from          date,           -- by_date 케이스의 파싱된 날짜

    -- 원문 보존
    area_raw                jsonb           not null default '{}',  -- 원본 셀 전체

    created_at              timestamptz     not null default now(),
    updated_at              timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_floor_availabilities_updated_at
    before update on floor_availabilities
    for each row execute function touch_updated_at();

-- 스냅샷 기준 조회 (1:N 조인 최적화)
create index idx_floor_avail_snapshot
    on floor_availabilities (listing_snapshot_id);

-- 범위검색 부분 인덱스: 실데이터 행만 (Total 행 제외)
-- "전용 100~300㎡, 즉시입주" 조건 검색에 사용
create index idx_floor_avail_area_kind
    on floor_availabilities (exclusive_area_sqm, availability_kind)
    where not is_total_row;

-- 층번호 범위 검색 (특정 층 이상/이하 조건)
create index idx_floor_avail_floor_number
    on floor_availabilities (listing_snapshot_id, floor_number)
    where floor_number is not null and not is_total_row;

-- RLS
alter table floor_availabilities enable row level security;

create policy "authenticated 읽기/쓰기" on floor_availabilities
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
