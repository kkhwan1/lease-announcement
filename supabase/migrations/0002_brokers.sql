-- 0002_brokers.sql
-- 중개사 마스터 테이블 + 초기 4개사 시드 데이터
-- 파서 라우팅 키(parser_key) 포함 — 어댑터 패턴에서 중개사별 파서 선택에 사용.

begin;

create table brokers (
    id            uuid        primary key default gen_random_uuid(),
    code          text        not null unique,   -- 'JLL' | 'CW' | 'S1' | 'OSCAR'
    name          text        not null,           -- 표시명 (한글)
    parser_key    text        not null,           -- 어댑터 라우팅 키
    active        boolean     not null default true,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- updated_at 자동 갱신
create trigger trg_brokers_updated_at
    before update on brokers
    for each row execute function touch_updated_at();

-- RLS 활성화 (1인 운영자 — authenticated 전체 허용)
alter table brokers enable row level security;

create policy "authenticated 읽기/쓰기" on brokers
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);


-- ───────────────────────────────────────────────
-- 초기 시드: 4개 중개사
-- ───────────────────────────────────────────────
insert into brokers (code, name, parser_key) values
    ('JLL',   'JLL코리아',          'jll'),    -- Vision 필요, 현재 파싱 제외
    ('CW',    '쿠시먼앤드웨이크필드', 'cnw'),   -- 표 파싱(분리 층별표 결합)
    ('S1',    '에스원부동산',         's1'),    -- 섹션 헤더 파싱
    ('OSCAR', '오스카앤컴퍼니',       'oscar'); -- 표 파싱(가장 깔끔)

commit;
