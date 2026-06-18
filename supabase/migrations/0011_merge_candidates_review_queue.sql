-- 0011_merge_candidates_review_queue.sql
-- 수동 병합 큐(merge_candidates): Entity Resolution 회색지대(유사도 0.80~0.92) 후보.
-- 검수 큐(review_queue): 저신뢰 추출 건 검수 대기.

begin;

-- ───────────────────────────────────────────────
-- 수동 병합 큐
-- Entity Resolution 자동 임계값(0.92) 미달 → 사람이 같은 건물인지 판정
-- ───────────────────────────────────────────────
create table merge_candidates (
    id                  uuid            primary key default gen_random_uuid(),

    -- 병합 후보 쌍 (building_id_a < building_id_b 정렬로 중복 방지)
    building_id_a       uuid            not null references buildings(id) on delete cascade,
    building_id_b       uuid            not null references buildings(id) on delete cascade,

    -- 유사도 점수 (rapidfuzz token_set_ratio + Jaro-Winkler)
    similarity_score    numeric(5,4)    not null check (similarity_score between 0 and 1),
    match_reason        text,           -- 매칭 근거 메모 (예: '주소 일치 + 이름 유사도 0.87')

    -- 검토 상태
    status              text            not null default 'pending'
                            check (status in ('pending', 'merged', 'rejected', 'deferred')),
    reviewed_by         text,           -- 검토자
    reviewed_at         timestamptz,
    merge_result_id     uuid            references buildings(id) on delete set null,  -- 병합 후 마스터 ID

    -- 출처 추적
    detected_in_doc_id  uuid            references source_documents(id) on delete set null,

    created_at          timestamptz     not null default now(),
    updated_at          timestamptz     not null default now(),

    -- 후보 쌍 중복 방지 (a < b 보장은 애플리케이션 레이어 책임)
    constraint uq_merge_candidate_pair unique (building_id_a, building_id_b)
);

create trigger trg_merge_candidates_updated_at
    before update on merge_candidates
    for each row execute function touch_updated_at();

-- 미검토 항목 조회 (검수 워크플로우)
create index idx_merge_candidates_pending
    on merge_candidates (similarity_score desc)
    where status = 'pending';

create index idx_merge_candidates_building_a
    on merge_candidates (building_id_a);

create index idx_merge_candidates_building_b
    on merge_candidates (building_id_b);

-- RLS
alter table merge_candidates enable row level security;

create policy "authenticated 읽기/쓰기" on merge_candidates
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);


-- ───────────────────────────────────────────────
-- 검수 큐
-- 저신뢰(confidence < 임계값) 추출 건 또는 파서 경고 발생 건
-- ───────────────────────────────────────────────
create table review_queue (
    id                      uuid            primary key default gen_random_uuid(),

    -- 검수 대상 (raw_extraction 또는 listing_snapshot 중 하나)
    raw_extraction_id       uuid            references raw_extractions(id) on delete cascade,
    listing_snapshot_id     uuid            references listing_snapshots(id) on delete cascade,

    -- 검수 사유
    reason_code             text            not null,   -- 'low_confidence' | 'parse_warning' | 'missing_required' | 'manual'
    reason_detail           text,
    confidence              numeric(4,3)    check (confidence between 0 and 1),
    warnings                text[],         -- 파서 경고 메시지 배열

    -- 검토 상태
    status                  text            not null default 'pending'
                                check (status in ('pending', 'approved', 'rejected', 'corrected')),
    reviewed_by             text,
    reviewed_at             timestamptz,
    correction_notes        text,           -- 수정 내용 메모

    created_at              timestamptz     not null default now(),
    updated_at              timestamptz     not null default now(),

    -- raw_extraction 또는 listing_snapshot 중 하나는 반드시 지정
    constraint chk_review_queue_target
        check (
            (raw_extraction_id is not null)
            or (listing_snapshot_id is not null)
        )
);

create trigger trg_review_queue_updated_at
    before update on review_queue
    for each row execute function touch_updated_at();

-- 미검토 항목 조회 (reason_code별 필터)
create index idx_review_queue_pending
    on review_queue (reason_code, created_at desc)
    where status = 'pending';

-- RLS
alter table review_queue enable row level security;

create policy "authenticated 읽기/쓰기" on review_queue
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
