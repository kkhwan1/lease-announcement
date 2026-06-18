-- 0019_buildings_enrich_columns.sql
-- buildings 마스터에 건축물대장/지오코딩 보강 컬럼 추가.
-- building_field_values에 이미 저장된 보강값을 마스터에서도 바로 조회/검색할 수 있도록
-- 비정규화 컬럼을 추가한다. 백필은 별도 UPDATE로 수행.

begin;

-- 주용도 (예: '업무시설', '근린생활시설')
alter table buildings
    add column if not exists main_purpose text;

-- 건폐율 % (예: 59.35)
alter table buildings
    add column if not exists building_coverage_ratio numeric(6,2);

-- 용적률 % — 800% 초과 사례 있어 8자리 확보 (예: 799.88)
alter table buildings
    add column if not exists floor_area_ratio numeric(8,2);

-- 건물 높이 m
alter table buildings
    add column if not exists height_m numeric(8,2);

-- 대지면적 ㎡ (소수점 포함, 큰 부지 대비 18자리)
alter table buildings
    add column if not exists land_area_sqm numeric(18,2);

-- 용도지역 (예: '일반상업지역', '준주거지역')
alter table buildings
    add column if not exists use_zone text;

-- 위도 (소수점 7자리 → 약 1cm 정밀도)
alter table buildings
    add column if not exists latitude numeric(10,7);

-- 경도
alter table buildings
    add column if not exists longitude numeric(10,7);

commit;
