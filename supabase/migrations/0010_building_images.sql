-- 0010_building_images.sql
-- 건물 이미지 메타 테이블 (바이너리는 Supabase Storage 'building-images' 버킷).
-- 경로 규약: {broker}/{period}/{building_id}/{kind}_p{page}.png
-- 120px×120px 미만 노이즈 이미지는 파이프라인에서 사전 제거 후 이 테이블에 삽입.

begin;

create table building_images (
    id                  uuid            primary key default gen_random_uuid(),
    building_id         uuid            not null references buildings(id) on delete cascade,
    source_document_id  uuid            references source_documents(id) on delete set null,

    -- Storage 경로 (private 버킷, signed URL 발급 필요)
    storage_path        text            not null unique,
    -- 경로 예: 'OSCAR/2026-06/018a2b3c-...-uuid/exterior_p003.png'

    -- 이미지 분류
    kind                image_kind      not null default 'other',
    page_number         integer,        -- 출처 PDF 페이지 번호

    -- PDF 내 좌표 (재crop 가능성 보존)
    bbox                numeric(10,2)[] ,  -- [x0, y0, x1, y1] PDF pt 좌표

    -- 이미지 크기 (노이즈 필터 통과 후 실측값)
    width_px            integer,
    height_px           integer,

    -- 검수 상태 (향후 이미지 QA 확장)
    is_verified         boolean         not null default false,
    verified_at         timestamptz,

    created_at          timestamptz     not null default now(),
    updated_at          timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_building_images_updated_at
    before update on building_images
    for each row execute function touch_updated_at();

-- 건물별 이미지 목록 조회 (kind 순 정렬용)
create index idx_building_images_building_kind
    on building_images (building_id, kind);

-- 출처 문서 기준 조회 (PDF 재처리 시 기존 이미지 삭제/대체용)
create index idx_building_images_source_doc
    on building_images (source_document_id);

-- RLS
alter table building_images enable row level security;

create policy "authenticated 읽기/쓰기" on building_images
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
