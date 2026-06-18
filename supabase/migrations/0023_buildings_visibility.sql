-- 0023_buildings_visibility.sql
-- 공개 플랫폼에서 특정 건물을 숨기는 플래그.
-- 'Others' 같은 미분류/쓰레기 데이터를 화면에서 제외하되 DB에는 보존.
-- 향후 이미지/데이터 관리 페이지에서 토글 가능.

begin;

alter table buildings
    add column if not exists is_hidden boolean not null default false;

comment on column buildings.is_hidden is
    '공개 화면 노출 제외 여부(true=숨김). 미분류/검수대기 건물용.';

-- 미분류 'Others' 건물 숨김
update buildings set is_hidden = true where name = 'Others';

commit;
