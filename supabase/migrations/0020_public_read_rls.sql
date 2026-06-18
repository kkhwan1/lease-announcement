-- 0020_public_read_rls.sql
-- 공개 플랫폼: anon(비로그인) 역할에 공개 테이블 SELECT 허용.
-- 내부 테이블(raw_extractions/source_documents/review_queue/merge_candidates/
-- building_field_values)은 정책 미부여 = anon 접근 차단 유지.
-- anon은 SELECT만 — INSERT/UPDATE/DELETE 정책 없음 = 쓰기 차단.

begin;

create policy "anon read buildings"            on buildings            for select to anon using (true);
create policy "anon read listing_snapshots"    on listing_snapshots    for select to anon using (true);
create policy "anon read floor_availabilities" on floor_availabilities for select to anon using (true);
create policy "anon read rent_terms"           on rent_terms           for select to anon using (true);
create policy "anon read building_images"      on building_images      for select to anon using (true);
create policy "anon read brokers"              on brokers              for select to anon using (true);
create policy "anon read building_aliases"     on building_aliases     for select to anon using (true);

commit;
