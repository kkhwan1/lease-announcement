-- 0005_buildings.sql
-- 건물 마스터 테이블 + 별칭 테이블.
-- buildings: 물리적 건물 1건 = 1행. 중개사별 중복 없음.
-- building_aliases: 중개사별 호칭 차이 흡수 ("케이스퀘어 강남 II" vs "케이스퀘어강남2").
-- identity_key: 정규화 주소 기반 generated 컬럼 → Entity Resolution 매칭 키.
-- pg_trgm 인덱스로 건물명 유사도 검색 지원.

begin;

create table buildings (
    id                  uuid            primary key default gen_random_uuid(),

    -- 대표 건물명 (정규화, 마스터 레코드 기준)
    name                text            not null,
    name_raw            text,           -- 최초 추출 원문 보존

    -- 위치
    address_road        text,           -- 도로명 주소
    address_jibun       text,           -- 지번 주소
    address_raw         text,           -- 원문 (정규화 전)
    district            business_district,
    station_area        text,           -- 인근 역 (예: '강남역 도보 3분')

    -- Entity Resolution 매칭 키 (주소 정규화 결과)
    -- 공백·특수문자 제거 + unaccent 적용한 도로명 주소
    -- immutable_unaccent: unaccent()는 STABLE이라 generated 컬럼에 직접 사용 불가 → 0001의 IMMUTABLE 래퍼 사용
    identity_key        text generated always as (
                            lower(
                                regexp_replace(
                                    immutable_unaccent(coalesce(address_road, name)),
                                    '[^가-힣a-z0-9]', '', 'g'
                                )
                            )
                        ) stored,

    -- 물리 스펙 (시간 불변)
    floors_above        integer,        -- 지상 층수
    floors_below        integer,        -- 지하 층수
    scale_raw           text,           -- 원문 ('B3 / 20F')
    gross_area_sqm      numeric(12,2),  -- 연면적 ㎡
    gross_area_pyeong   numeric(12,2),  -- 연면적 평 (원문)
    exclusive_area_sqm  numeric(12,2),  -- 대표 전용면적 ㎡
    exclusive_area_pyeong numeric(12,2),
    ev_count            integer,        -- 엘리베이터 수
    completed_year      integer,        -- 준공연도
    completed_raw       text,           -- 원문 ('1976년(2009년 리모델링)')
    ceiling_height_m    numeric(5,2),   -- 층고 (m)
    efficiency_ratio    numeric(5,2),   -- 전용률 (%)
    parking_total       integer,        -- 주차 대수
    parking_terms_raw   text,
    features_raw        text,           -- 특장점 원문

    created_at          timestamptz     not null default now(),
    updated_at          timestamptz     not null default now()
);

-- updated_at 자동 갱신
create trigger trg_buildings_updated_at
    before update on buildings
    for each row execute function touch_updated_at();

-- identity_key 고유 인덱스 (Entity Resolution 중복 방지)
create unique index idx_buildings_identity_key
    on buildings (identity_key)
    where identity_key is not null;

-- 건물명 trigram 인덱스 (유사도 검색: similarity(), %)
create index idx_buildings_name_trgm
    on buildings using gin (name gin_trgm_ops);

-- 도로명 주소 trigram 인덱스
create index idx_buildings_address_road_trgm
    on buildings using gin (address_road gin_trgm_ops);

-- 권역별 조회 인덱스
create index idx_buildings_district
    on buildings (district);

-- RLS
alter table buildings enable row level security;

create policy "authenticated 읽기/쓰기" on buildings
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);


-- ───────────────────────────────────────────────
-- 건물 별칭 테이블
-- ───────────────────────────────────────────────
create table building_aliases (
    id              uuid        primary key default gen_random_uuid(),
    building_id     uuid        not null references buildings(id) on delete cascade,
    broker_id       uuid        references brokers(id) on delete set null,  -- null=전사 공통 별칭
    alias           text        not null,       -- 중개사가 표기한 건물명 원문
    alias_normalized text        not null,      -- 정규화 후 (유사도 인덱스용)
    created_at      timestamptz not null default now()
);

-- 중개사 + 별칭 조합 고유 (같은 중개사의 동일 alias 중복 방지)
create unique index idx_building_aliases_broker_alias
    on building_aliases (broker_id, alias_normalized)
    where broker_id is not null;

-- 전사 공통 별칭 고유 (broker_id null 케이스)
create unique index idx_building_aliases_global_alias
    on building_aliases (alias_normalized)
    where broker_id is null;

-- 별칭 trigram 인덱스 (Entity Resolution 검색용)
create index idx_building_aliases_alias_trgm
    on building_aliases using gin (alias gin_trgm_ops);

-- building_id 조회 인덱스
create index idx_building_aliases_building_id
    on building_aliases (building_id);

-- RLS
alter table building_aliases enable row level security;

create policy "authenticated 읽기/쓰기" on building_aliases
    for all
    to authenticated
    using     ((select auth.uid()) is not null)
    with check ((select auth.uid()) is not null);

commit;
