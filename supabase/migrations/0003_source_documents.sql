-- 0003_source_documents.sql
-- PDF 원본 추적 테이블.
-- file_sha256 unique → 같은 PDF 재업로드 시 멱등 보장.
-- issue_period: 월 정규화 (예: 2026-06-01, 항상 월 1일로 저장).

begin;

create table source_documents (
    id                  uuid         primary key default gen_random_uuid(),
    broker_id           uuid         not null references brokers(id) on delete restrict,
    filename            text         not null,             -- 원본 파일명
    file_sha256         text         not null unique,      -- SHA-256 hex, 멱등 키
    file_size_bytes     bigint,
    page_count          integer,
    issue_period        date,                              -- 안내문 발행 월 (YYYY-MM-01)
    parse_status        parse_status not null default 'pending',
    parsed_at           timestamptz,
    parse_error         text,                              -- 실패 시 에러 메시지
    storage_path        text,                              -- Supabase Storage 경로
    created_at          timestamptz  not null default now(),
    updated_at          timestamptz  not null default now()
);

-- updated_at 자동 갱신
create trigger trg_source_documents_updated_at
    before update on source_documents
    for each row execute function touch_updated_at();

-- broker_id + issue_period 복합 인덱스 (중개사별 월 조회)
create index idx_source_documents_broker_period
    on source_documents (broker_id, issue_period);

-- 파싱 상태 조회 인덱스 (batch 재처리 시 pending/failed 필터)
create index idx_source_documents_parse_status
    on source_documents (parse_status)
    where parse_status in ('pending', 'parsing', 'failed');

-- RLS
alter table source_documents enable row level security;

create policy "authenticated 읽기/쓰기" on source_documents
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
