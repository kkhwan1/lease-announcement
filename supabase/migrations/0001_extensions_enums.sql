-- 0001_extensions_enums.sql
-- PostgreSQL 확장, 공통 enum 타입, 공통 트리거 함수 설치
-- 모든 마이그레이션의 기반이 되는 파일 — 반드시 가장 먼저 실행해야 함.

begin;

-- ───────────────────────────────────────────────
-- 1. 확장 (extension)
-- ───────────────────────────────────────────────

-- SHA-256 해시(source_documents.file_sha256) 생성용
create extension if not exists pgcrypto;

-- 건물명 유사도 검색(building_aliases, entity resolution) 인덱스용
create extension if not exists pg_trgm;

-- 한글 등 악센트 제거(정규화 주소 identity_key 생성용)
create extension if not exists unaccent;


-- ───────────────────────────────────────────────
-- 2. 공통 Enum 타입
-- ───────────────────────────────────────────────

-- 서울 업무권역 구분 (GBD=강남, CBD=도심, YBD=여의도, BBD=분당/판교, ETC=기타)
create type business_district as enum (
    'GBD',  -- 강남권역
    'CBD',  -- 도심권역
    'YBD',  -- 여의도권역
    'BBD',  -- 분당/판교권역
    'ETC'   -- 기타
);

-- 데이터 출처 유형 (향후 Vision/OCR 구분용)
create type data_source_type as enum (
    'rule_table',    -- 표 파싱(Oscar/CnW)
    'section_text',  -- 섹션 헤더 파싱(에스원)
    'vision',        -- Vision LLM (향후)
    'ocr'            -- OCR 폴백
);

-- 공실 입주 가능 시점
create type availability_kind as enum (
    'immediate',   -- 즉시 입주 가능
    'negotiable',  -- 협의
    'by_date',     -- 특정일 이후
    'unknown'      -- 미기재/불명
);

-- 건물 이미지 종류
create type image_kind as enum (
    'exterior',      -- 외관
    'location_map',  -- 위치도
    'floor_plan',    -- 평면도
    'lobby',         -- 로비
    'interior',      -- 전용부/내부
    'other'          -- 기타
);

-- PDF 파싱 진행 상태
create type parse_status as enum (
    'pending',   -- 대기 중
    'parsing',   -- 파싱 진행 중
    'parsed',    -- 완료
    'partial',   -- 일부 실패
    'failed'     -- 전체 실패
);


-- ───────────────────────────────────────────────
-- 3. 공통 트리거 함수
-- ───────────────────────────────────────────────

-- updated_at 자동 갱신 트리거 함수 (모든 테이블에 공유)
create or replace function touch_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- ───────────────────────────────────────────────
-- 4. immutable unaccent 래퍼
-- ───────────────────────────────────────────────
-- unaccent()는 STABLE이라 generated 컬럼(buildings.identity_key)에 직접 사용 불가.
-- 'unaccent' 사전을 명시 호출하여 결정적으로 동작하는 IMMUTABLE 래퍼로 감싼다.
create or replace function immutable_unaccent(text)
returns text
language sql
immutable
parallel safe
strict
set search_path = pg_catalog
as $$
    select unaccent('unaccent', $1);
$$;

commit;
