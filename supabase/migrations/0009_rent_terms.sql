-- 0009_rent_terms.sql
-- 임대조건 테이블.
-- _per_pyeong: 원문 보존 (원/평 기준).
-- _per_sqm: generated stored 컬럼 (/3.305785 환산).
-- 1평 = 3.305785㎡ 고정 (계획서 확정값).

begin;

create table rent_terms (
    id                          uuid            primary key default gen_random_uuid(),
    listing_snapshot_id         uuid            not null references listing_snapshots(id) on delete cascade,

    -- 적용 범위 레이블 ('기준층', '전층', '18층' 등)
    scope_label                 text,

    -- 보증금 (원/평, 원문 보존)
    deposit_per_pyeong          numeric(15,2),
    -- 보증금 ㎡ 환산 (generated stored)
    deposit_per_sqm             numeric(15,4)
        generated always as (deposit_per_pyeong / 3.305785) stored,

    -- 임대료 (원/평/월, 원문 보존)
    rent_per_pyeong             numeric(12,2),
    -- 임대료 ㎡ 환산 (generated stored)
    rent_per_sqm                numeric(12,4)
        generated always as (rent_per_pyeong / 3.305785) stored,

    -- 관리비 (원/평/월, 원문 보존)
    maintenance_per_pyeong      numeric(12,2),
    -- 관리비 ㎡ 환산 (generated stored)
    maintenance_per_sqm         numeric(12,4)
        generated always as (maintenance_per_pyeong / 3.305785) stored,

    -- 원문 보존 (재처리 안전성)
    terms_raw                   jsonb           not null default '{}',

    created_at                  timestamptz     not null default now(),
    updated_at                  timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_rent_terms_updated_at
    before update on rent_terms
    for each row execute function touch_updated_at();

-- 스냅샷 기준 조회
create index idx_rent_terms_snapshot
    on rent_terms (listing_snapshot_id);

-- 임대료 범위 필터 인덱스 (검색 뷰에서 "임대료 ≤ X" 조건용)
create index idx_rent_terms_rent_per_sqm
    on rent_terms (rent_per_sqm)
    where rent_per_sqm is not null;

-- RLS
alter table rent_terms enable row level security;

create policy "authenticated 읽기/쓰기" on rent_terms
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
