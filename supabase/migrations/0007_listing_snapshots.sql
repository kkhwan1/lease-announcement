-- 0007_listing_snapshots.sql
-- 건물×중개사×월 스냅샷 테이블.
-- is_latest: 같은 (building_id, broker_id) 조합에서 최신 1건만 true.
-- 부분 유니크 인덱스(where is_latest) + demote 트리거로 보장.

begin;

create table listing_snapshots (
    id                  uuid            primary key default gen_random_uuid(),
    building_id         uuid            not null references buildings(id) on delete cascade,
    broker_id           uuid            not null references brokers(id) on delete restrict,
    source_document_id  uuid            not null references source_documents(id) on delete restrict,
    snapshot_month      date            not null,   -- 스냅샷 기준 월 (YYYY-MM-01)
    is_latest           boolean         not null default true,

    -- 스냅샷 시점의 건물 요약 (검색 편의용 비정규화)
    district            business_district,
    name_snapshot       text,           -- 스냅샷 시점 건물명

    -- 스냅샷 메타
    raw_extraction_id   uuid            references raw_extractions(id) on delete set null,
    extraction_method   data_source_type not null default 'rule_table',
    confidence          numeric(4,3)    not null default 1.0
                            check (confidence between 0 and 1),

    created_at          timestamptz     not null default now(),
    updated_at          timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_listing_snapshots_updated_at
    before update on listing_snapshots
    for each row execute function touch_updated_at();

-- 핵심: is_latest=true인 행은 (building_id, broker_id) 조합당 1건만 허용
-- WHERE 절 부분 유니크 인덱스 사용
create unique index idx_listing_snapshots_latest_unique
    on listing_snapshots (building_id, broker_id)
    where is_latest = true;

-- 월별 중복 방지 (같은 건물×중개사×월 조합은 1건)
create unique index idx_listing_snapshots_building_broker_month
    on listing_snapshots (building_id, broker_id, snapshot_month);

-- 최신 스냅샷 조회 인덱스
create index idx_listing_snapshots_building_latest
    on listing_snapshots (building_id)
    where is_latest = true;

-- 중개사별 스냅샷 이력 조회
create index idx_listing_snapshots_broker_month
    on listing_snapshots (broker_id, snapshot_month desc);


-- ───────────────────────────────────────────────
-- demote 트리거: 새 is_latest=true 삽입/갱신 시
-- 같은 (building_id, broker_id)의 기존 is_latest=true 행을 false로 강등
-- ───────────────────────────────────────────────
create or replace function demote_old_latest_snapshot()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $$
begin
    -- 새 행이 is_latest=true일 때만 강등 처리
    if new.is_latest = true then
        update listing_snapshots
        set    is_latest = false
        where  building_id = new.building_id
          and  broker_id   = new.broker_id
          and  id          != new.id       -- 자기 자신 제외
          and  is_latest   = true;
    end if;
    return new;
end;
$$;

-- INSERT와 UPDATE 모두 트리거 (upsert 패턴 대응)
create trigger trg_demote_old_latest_snapshot
    after insert or update of is_latest on listing_snapshots
    for each row execute function demote_old_latest_snapshot();


-- RLS
alter table listing_snapshots enable row level security;

create policy "authenticated 읽기/쓰기" on listing_snapshots
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
