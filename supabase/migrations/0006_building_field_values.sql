-- 0006_building_field_values.sql
-- 필드 단위 출처 병합 테이블.
-- "부족한 필드를 다른 PDF에서 채워 넣기"의 구현 기반.
-- 동일 건물×필드×출처 문서 조합이 UNIQUE → upsert 멱등 보장.
-- is_active=true 행이 현재 채택값, false는 이력 보존.

begin;

create table building_field_values (
    id                  uuid            primary key default gen_random_uuid(),
    building_id         uuid            not null references buildings(id) on delete cascade,
    field_name          text            not null,   -- 컬럼명 (예: 'gross_area_sqm', 'ceiling_height_m')
    value               text            not null,   -- 문자열 직렬화 값 (숫자/날짜 포함)
    source_document_id  uuid            not null references source_documents(id) on delete restrict,
    broker_id           uuid            references brokers(id) on delete set null,
    source_month        date,                       -- 출처 안내문 발행 월 (YYYY-MM-01)
    confidence          numeric(4,3)    not null default 1.0
                            check (confidence between 0 and 1),
    is_active           boolean         not null default true,  -- 현재 채택 여부
    notes               text,           -- 수동 검토 메모
    created_at          timestamptz     not null default now(),
    updated_at          timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_building_field_values_updated_at
    before update on building_field_values
    for each row execute function touch_updated_at();

-- 핵심 유니크 제약: 건물×필드×출처 문서 조합 1건 (upsert 키)
create unique index idx_bfv_building_field_source
    on building_field_values (building_id, field_name, source_document_id);

-- 현재 활성 값 빠른 조회 (병합 결과 확인)
create index idx_bfv_building_field_active
    on building_field_values (building_id, field_name)
    where is_active = true;

-- 출처 문서 기준 조회 (PDF 재처리 시 해당 출처 비활성화용)
create index idx_bfv_source_document
    on building_field_values (source_document_id);

-- RLS
alter table building_field_values enable row level security;

create policy "authenticated 읽기/쓰기" on building_field_values
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
