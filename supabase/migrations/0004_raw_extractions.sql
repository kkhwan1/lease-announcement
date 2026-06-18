-- 0004_raw_extractions.sql
-- 파서가 추출한 가공 전 원본 보존 테이블 (immutable).
-- 파서 로직 개선 시 PDF 재파싱 없이 이 레코드에서 재승격 가능.
-- 분류 키: (source_document_id, page_group_id, raw_building_name)

begin;

create table raw_extractions (
    id                  uuid            primary key default gen_random_uuid(),
    source_document_id  uuid            not null references source_documents(id) on delete restrict,

    -- 건물 분류 키 (파서가 페이지 그룹핑 결과로 채움)
    page_group_id       text,           -- 같은 건물의 연속 페이지 묶음 식별자 (예: 'p012-015')
    raw_building_name   text,           -- 파서가 인식한 원본 건물명 (정규화 전)

    -- 파싱 메타
    page_range          integer[],      -- 이 추출이 걸친 페이지 번호 배열
    extraction_method   data_source_type not null default 'rule_table',
    confidence          numeric(4,3)    not null default 1.0
                            check (confidence between 0 and 1),

    -- 가공 전 raw 전체 페이로드 (JSON, immutable)
    raw_payload         jsonb           not null,

    -- 승격 상태 추적
    promoted_building_id uuid,          -- buildings.id 연결 시 채움 (null=미승격)
    promoted_at         timestamptz,

    created_at          timestamptz     not null default now()
    -- updated_at 없음: immutable 레코드
);

-- 중복 방지: 같은 PDF × 건물명 조합은 1건
create unique index idx_raw_extractions_doc_building
    on raw_extractions (source_document_id, raw_building_name)
    where raw_building_name is not null;

-- 페이지 그룹 단위 조회 (재파싱 결과 비교용)
create index idx_raw_extractions_page_group
    on raw_extractions (source_document_id, page_group_id);

-- 미승격 항목 빠른 조회 (승격 배치 처리용)
create index idx_raw_extractions_unpromotoed
    on raw_extractions (source_document_id)
    where promoted_building_id is null;

-- GIN 인덱스: raw_payload jsonb 필드 검색
create index idx_raw_extractions_payload_gin
    on raw_extractions using gin (raw_payload);

-- RLS
alter table raw_extractions enable row level security;

create policy "authenticated 읽기/쓰기" on raw_extractions
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
