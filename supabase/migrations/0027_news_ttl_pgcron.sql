-- 0027_news_ttl_pgcron.sql
-- 뉴스 14일 TTL 자동 삭제 — Supabase pg_cron 기반(DB 자체 청소).
-- ⚠️ 아직 적용하지 마세요(서버/배포 시 활성화). 적용 시 apply_migration 또는 SQL 에디터에서 실행.
--
-- 장점: PC·수집기 가동과 무관하게 DB가 매일 스스로 14일 경과분 삭제(가장 견고).
-- 대안: cli.py news --purge-days 14 (수집할 때 같이 청소) — 수집 cron이 돌 때만 청소됨.
--   둘 중 하나만 쓰면 충분. pg_cron을 켜면 cli의 --purge-days는 0으로 둬도 됨.

begin;

-- pg_cron 확장 활성화 (Supabase는 pg_cron 1.6.4 제공)
create extension if not exists pg_cron;

commit;

-- 매일 03:17(UTC)에 fetched_at 기준 14일 경과 뉴스 삭제.
-- cron.schedule은 트랜잭션 밖에서 실행(begin/commit 분리).
select cron.schedule(
  'purge-old-news',           -- 잡 이름(유니크)
  '17 3 * * *',               -- 매일 03:17 UTC (정각 피크 회피)
  $$delete from public.news_articles
     where fetched_at < now() - interval '14 days'$$
);

-- === 비활성화(잡 제거) ===
--   select cron.unschedule('purge-old-news');
-- === 등록 확인 ===
--   select * from cron.job where jobname = 'purge-old-news';
