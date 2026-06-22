"""CLI 진입점 — PDF 임대안내문 처리 파이프라인.

사용법:
  python cli.py ingest <pdf> [--out out/]   # 단건 처리
  python cli.py batch <dir> [--out out/]    # 폴더 내 모든 PDF 일괄 처리
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# 이 프로젝트 .env를 먼저 로드해 모든 키(DATAGO_SERVICE_KEY·VWORLD_KEY 등)를
# 자급자족하게 한다. kk_real_estate/.env는 building_register가 보조로 로드하되
# 이미 세팅된 키는 덮어쓰지 않으므로, 여기서 로드한 이 프로젝트 값이 우선한다.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.pipeline import process_pdf
from app.schemas import BrokerCode, BuildingExtraction, SourceDocument

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cli")


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

# 파일명에 사용할 수 없는 문자를 _ 로 치환
_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|]')


def _safe_filename(name: str) -> str:
    """파일명에 부적합한 문자를 _ 로 치환."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def _save_building(building: BuildingExtraction, out_dir: Path) -> Path:
    """BuildingExtraction을 JSON 파일로 저장하고 경로를 반환."""
    broker_code = building.broker.value
    bname = _safe_filename(building.building_name)
    filename = f"{broker_code}_{bname}.json"
    out_path = out_dir / filename
    out_path.write_text(
        json.dumps(building.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def _count_missing(building: BuildingExtraction) -> int:
    """누락 필드 수 반환 (missing_fields() 사용)."""
    return len(building.missing_fields())


def _summarize_building(building: BuildingExtraction) -> None:
    """단건 처리 콘솔 요약 출력 (층별 합계, 누락필드 수)."""
    floor_count = len([f for f in building.floors if not f.is_total_row])
    total_floors = len(building.floors)
    missing = _count_missing(building)
    warnings_str = ", ".join(building.warnings) if building.warnings else "없음"

    print(f"  건물명    : {building.building_name}")
    print(f"  층별 공실 : {floor_count}개 행 (Total 포함 {total_floors}개)")
    print(f"  누락 필드 : {missing}개")
    print(f"  경고      : {warnings_str}")
    print(f"  신뢰도    : {building.confidence:.2f}")


# ---------------------------------------------------------------------------
# ingest 커맨드: 단건 처리
# ---------------------------------------------------------------------------

def cmd_ingest(pdf_path: str, out_dir: str) -> int:
    """단건 PDF 처리 → out/{broker}_{건물명}.json 저장."""
    pdf = Path(pdf_path)
    if not pdf.exists():
        print(f"오류: 파일 없음 — {pdf}", file=sys.stderr)
        return 1

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n[ingest] {pdf.name} 처리 중...")

    try:
        source_doc = process_pdf(pdf)
    except Exception as exc:
        print(f"오류: PDF 처리 실패 — {exc}", file=sys.stderr)
        return 1

    print(f"  중개사    : {source_doc.broker.value}")
    print(f"  발행월    : {source_doc.source_month or '미확인'}")
    print(f"  전체 페이지: {source_doc.page_count}p")
    print(f"  추출 건물 : {len(source_doc.buildings)}개\n")

    if not source_doc.buildings:
        print("  (추출된 건물 없음)")
        return 0

    for b in source_doc.buildings:
        out_path = _save_building(b, out)
        _summarize_building(b)
        print(f"  저장      : {out_path}\n")

    return 0


# ---------------------------------------------------------------------------
# batch 커맨드: 폴더 내 모든 PDF 처리
# ---------------------------------------------------------------------------

def cmd_batch(pdf_dir: str, out_dir: str) -> int:
    """폴더 내 모든 PDF 처리 → 중개사별 통계 테이블 출력."""
    src = Path(pdf_dir)
    if not src.exists():
        print(f"오류: 디렉토리 없음 — {src}", file=sys.stderr)
        return 1

    pdfs = sorted(src.glob("*.pdf"))
    if not pdfs:
        print(f"오류: PDF 파일 없음 — {src}", file=sys.stderr)
        return 1

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 통계 집계용 구조: {broker_code: {buildings, floors, missing, failures}}
    stats: dict[str, dict] = defaultdict(lambda: {
        "buildings": 0,
        "floors": 0,
        "missing": 0,
        "failures": 0,
        "files": 0,
    })

    print(f"\n[batch] {src} → {len(pdfs)}개 PDF 처리 시작\n")

    for pdf in pdfs:
        print(f"  처리 중: {pdf.name}")
        try:
            source_doc = process_pdf(pdf)
        except Exception as exc:
            print(f"  [실패] {pdf.name} — {exc}", file=sys.stderr)
            # 중개사 불명이면 'UNKNOWN'으로 집계
            stats["UNKNOWN"]["failures"] += 1
            stats["UNKNOWN"]["files"] += 1
            continue

        bcode = source_doc.broker.value
        stats[bcode]["files"] += 1

        for b in source_doc.buildings:
            stats[bcode]["buildings"] += 1
            # Total 행 제외한 실제 공실 층 수
            stats[bcode]["floors"] += len([f for f in b.floors if not f.is_total_row])
            stats[bcode]["missing"] += _count_missing(b)

            try:
                _save_building(b, out)
            except Exception as exc:
                logger.error("JSON 저장 실패: %s — %s", b.building_name, exc)
                stats[bcode]["failures"] += 1

    # ---------------------------------------------------------------------------
    # 통계 테이블 출력
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("  중개사별 처리 결과 요약")
    print("=" * 72)
    print(f"  {'중개사':<8} {'파일':>4} {'건물':>6} {'공실층':>8} {'누락필드':>8} {'실패':>4}")
    print("-" * 72)

    total_buildings = 0
    total_floors = 0
    total_missing = 0
    total_failures = 0
    total_files = 0

    for bcode in sorted(stats.keys()):
        s = stats[bcode]
        print(
            f"  {bcode:<8} {s['files']:>4} {s['buildings']:>6}"
            f" {s['floors']:>8} {s['missing']:>8} {s['failures']:>4}"
        )
        total_buildings += s["buildings"]
        total_floors += s["floors"]
        total_missing += s["missing"]
        total_failures += s["failures"]
        total_files += s["files"]

    print("-" * 72)
    print(
        f"  {'합계':<8} {total_files:>4} {total_buildings:>6}"
        f" {total_floors:>8} {total_missing:>8} {total_failures:>4}"
    )
    print("=" * 72)
    print(f"\n  출력 경로: {out.resolve()}\n")

    return 0 if total_failures == 0 else 1


# ---------------------------------------------------------------------------
# push 커맨드: PDF 재파싱 → Supabase 적재 (pipeline + store_document 연동)
# ---------------------------------------------------------------------------

def cmd_push(pdf_dir: str, out_dir: str, enrich: bool = False, with_images: bool = True) -> int:
    """폴더 내 모든 PDF를 파싱해 Supabase에 적재.

    흐름:
      1. 폴더 내 PDF 목록 수집
      2. 각 PDF: pipeline.process_pdf → SourceDocument
      3. (enrich=True) 각 건물에 건축물대장 API 보강 (빈 필드만 채움)
      4. supa_store.store_document → Supabase upsert
      5. 중개사별 적재 통계 출력

    with_images=False면 이미지 추출/Storage 업로드를 건너뛴다(텍스트 적재만, 빠름).
    """
    from app.supa_store import store_document

    enrichers = []
    if enrich:
        from app.enrich.base import apply_enrichers
        from app.enrich.building_register import BuildingRegisterEnricher
        enrichers = [BuildingRegisterEnricher()]
        print("  [enrich] 건축물대장 API 보강 활성화")

    src = Path(pdf_dir)
    if not src.exists():
        print(f"오류: 디렉토리 없음 — {src}", file=sys.stderr)
        return 1

    pdfs = sorted(src.glob("*.pdf"))
    if not pdfs:
        print(f"오류: PDF 파일 없음 — {src}", file=sys.stderr)
        return 1

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 집계: {broker_code: {files, buildings_new, buildings_matched, buildings_queued, errors}}
    stats: dict[str, dict] = defaultdict(lambda: {
        "files": 0,
        "buildings_new": 0,
        "buildings_matched": 0,
        "buildings_queued": 0,
        "errors": 0,
    })

    print(f"\n[push] {src} → Supabase 적재 시작 ({len(pdfs)}개 PDF)\n")

    total_errors: list[str] = []

    for pdf in pdfs:
        print(f"  처리 중: {pdf.name}")
        # 이미지 crop PNG의 수명을 store_document 호출 이후까지 보장하기 위해
        # 임시 디렉토리를 push 루프 안에서 직접 관리한다.
        with tempfile.TemporaryDirectory(prefix="lease_imgs_") as tmp_img_dir:
            # with_images=False면 이미지 추출/업로드 생략 (img_out_dir=None)
            img_out_dir = Path(tmp_img_dir) if with_images else None
            try:
                source_doc = process_pdf(pdf, img_out_dir=img_out_dir)
            except Exception as exc:
                msg = f"  [파싱 실패] {pdf.name} — {exc}"
                print(msg, file=sys.stderr)
                total_errors.append(msg)
                stats["UNKNOWN"]["files"] += 1
                stats["UNKNOWN"]["errors"] += 1
                continue

            bcode = source_doc.broker.value
            stats[bcode]["files"] += 1

            # 건축물대장 API 보강 (빈 필드만 채움, graceful — 실패해도 적재 진행)
            if enrichers:
                for i, bld in enumerate(source_doc.buildings):
                    try:
                        source_doc.buildings[i] = apply_enrichers(bld, enrichers)
                    except Exception as exc:
                        print(f"    [보강 실패] {bld.building_name} — {exc}", file=sys.stderr)

            try:
                result = store_document(source_doc, source_doc.buildings)
            except Exception as exc:
                msg = f"  [적재 실패] {pdf.name} — {exc}"
                print(msg, file=sys.stderr)
                total_errors.append(msg)
                stats[bcode]["errors"] += 1
                continue

            stats[bcode]["buildings_new"] += result.get("buildings_new", 0)
            stats[bcode]["buildings_matched"] += result.get("buildings_matched", 0)
            stats[bcode]["buildings_queued"] += result.get("buildings_queued", 0)
            stats[bcode]["errors"] += len(result.get("errors", []))

            print(
                f"    건물: {result['buildings_processed']}개"
                f" (신규={result.get('buildings_new', 0)}"
                f", 매칭={result.get('buildings_matched', 0)}"
                f", 큐={result.get('buildings_queued', 0)})"
                f" 오류={len(result.get('errors', []))}"
            )
            # with 블록 종료 시 tmp_img_dir 자동 삭제 (Storage 업로드 완료 후)

    # 통계 테이블 출력
    print("\n" + "=" * 72)
    print("  Supabase 적재 결과 요약")
    print("=" * 72)
    print(f"  {'중개사':<8} {'파일':>4} {'신규':>6} {'매칭':>6} {'큐':>6} {'오류':>6}")
    print("-" * 72)

    for bcode in sorted(stats.keys()):
        s = stats[bcode]
        print(
            f"  {bcode:<8} {s['files']:>4} {s['buildings_new']:>6}"
            f" {s['buildings_matched']:>6} {s['buildings_queued']:>6} {s['errors']:>6}"
        )

    print("=" * 72)

    if total_errors:
        print(f"\n  오류 {len(total_errors)}건 발생 — 위 로그 확인")
        return 1
    return 0


def cmd_geocode(limit: int | None = None, dry_run: bool = False) -> int:
    """buildings.latitude/longitude가 NULL인 행을 주소 기반으로 보강."""
    import os
    from app.geocode import geocode_address
    from app.supa_store import get_client

    # 쓰기 작업이므로 service_role 키 필수 (anon이면 RLS로 UPDATE가 조용히 실패)
    if not dry_run and not (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    ):
        print("오류: geocode는 쓰기 작업입니다. SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
        return 1

    client = get_client()
    kakao_key = os.environ.get("KAKAO_REST_API_KEY")

    # latitude 또는 longitude 어느 한쪽이라도 NULL인 행을 보강 대상으로
    q = (
        client.table("buildings")
        .select("id, name, address_road, address_raw, latitude, longitude")
        .or_("latitude.is.null,longitude.is.null")
    )
    if limit:
        q = q.limit(limit)
    rows = q.execute().data or []
    print(f"좌표 미보유 건물: {len(rows)}건")

    ok = fail = 0
    for r in rows:
        addr = r.get("address_road") or r.get("address_raw")
        pt = geocode_address(addr, kakao_key)
        if pt:
            ok += 1
            print(f"  OK  {r['name']}: ({pt.lat:.6f}, {pt.lng:.6f}) <- {addr}")
            if not dry_run:
                client.table("buildings").update(
                    {"latitude": pt.lat, "longitude": pt.lng}
                ).eq("id", r["id"]).execute()
        else:
            fail += 1
            print(f"  --  {r['name']}: 보강 실패 <- {addr}")
    print(f"\n완료: 성공 {ok} / 실패 {fail}" + (" (dry-run)" if dry_run else ""))
    return 0


def cmd_commercial(limit: int | None = None, radius: int = 300,
                   dry_run: bool = False) -> int:
    """buildings의 좌표 보유 건물에 발달상권 정보를 보강한다.

    소상공인 상권정보 API로 좌표 반경 점포를 집계해
    building_commercial_areas 테이블에 upsert.
    """
    import os
    from app.commercial import fetch_commercial
    from app.supa_store import get_client

    # 쓰기 작업이므로 service_role 키 필수 (anon이면 RLS로 upsert 조용히 실패)
    if not dry_run and not (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    ):
        print("오류: commercial은 쓰기 작업입니다. SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
        return 1

    client = get_client()

    # 좌표가 모두 있는 건물만 대상 (둘 다 not null)
    q = (
        client.table("buildings")
        .select("id, name, latitude, longitude")
        .not_.is_("latitude", "null")
        .not_.is_("longitude", "null")
    )
    if limit:
        q = q.limit(limit)
    rows = q.execute().data or []
    print(f"좌표 보유 건물: {len(rows)}건 (반경 {radius}m)")

    ok = empty = fail = 0
    for r in rows:
        try:
            s = fetch_commercial(float(r["latitude"]), float(r["longitude"]), radius)
        except Exception as exc:
            fail += 1
            print(f"  --  {r['name']}: 조회 실패 — {type(exc).__name__}: {exc}")
            continue
        if not s:
            empty += 1
            print(f"  ..  {r['name']}: 반경 내 점포 없음")
            continue
        ok += 1
        print(
            f"  OK  {r['name']}: {s.area_name or '-'} "
            f"총 {s.store_count}개 (도소매 {s.retail_count}/서비스 {s.service_count}/외식 {s.food_count})"
        )
        if not dry_run:
            client.table("building_commercial_areas").upsert({
                "building_id": r["id"],
                "area_name": s.area_name,
                "store_count": s.store_count,
                "retail_count": s.retail_count,
                "service_count": s.service_count,
                "food_count": s.food_count,
                "radius_m": s.radius_m,
                "base_period": s.base_period,
                "top_industries": s.top_industries,
                "dong_name": s.dong_name,
                "resident_total": s.resident_total,
                "resident_male": s.resident_male,
                "resident_female": s.resident_female,
                "household_count": s.household_count,
                "resident_period": s.resident_period,
                "ldong_cd": s.ldong_cd,
            }).execute()
    print(
        f"\n완료: 적재 {ok} / 점포없음 {empty} / 실패 {fail}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def cmd_subway(xlsx_path: str | None = None, limit: int | None = None,
               dry_run: bool = False) -> int:
    """지하철역 마스터 적재 + 매물별 최근접역 보강.

    xlsx_path 지정 시: 레일포털 전국 도시철도역 XLSX를 subway_stations에 적재(upsert).
    그 후(또는 xlsx 미지정 시): 좌표 보유 building에 최근접역을 계산해
    building_commercial_areas.nearest_station* 컬럼에 반영.
    """
    import os
    from app.subway import nearest_station, parse_stations_xlsx
    from app.supa_store import get_client

    if not dry_run and not (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    ):
        print("오류: subway는 쓰기 작업입니다. SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
        return 1

    client = get_client()

    # (1) XLSX 마스터 적재
    if xlsx_path:
        stations = parse_stations_xlsx(xlsx_path)
        print(f"XLSX 파싱: {len(stations)}개역 (좌표 보유)")
        if not dry_run:
            # (name, line_name) 중복 제거 — upsert 키 충돌 방지(같은 역 중복 행 존재).
            seen: dict[tuple, dict] = {}
            for s in stations:
                key = (s.name, s.line_name or "")
                seen[key] = {
                    "station_code": s.station_code,
                    "name": s.name,
                    "line_name": s.line_name or "",
                    "line_code": s.line_code,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "operator": s.operator,
                    "road_address": s.road_address,
                    "is_transfer": s.is_transfer,
                    "base_date": s.base_date,
                }
            rows = list(seen.values())
            if len(rows) != len(stations):
                print(f"  (중복 제거: {len(stations)} → {len(rows)}건)")
            # 1000건 배치 upsert (name+line_name 유니크)
            for i in range(0, len(rows), 500):
                client.table("subway_stations").upsert(
                    rows[i:i + 500], on_conflict="name,line_name"
                ).execute()
            print(f"  → subway_stations 적재 완료 ({len(rows)}건)")

    # (2) 최근접역 보강 — 마스터를 메모리로 로드(1000행 제한 회피: 페이지네이션)
    master: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        chunk = (
            client.table("subway_stations")
            .select("name, line_name, latitude, longitude")
            .range(offset, offset + page_size - 1)
            .execute().data or []
        )
        master.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    if not master:
        print("subway_stations가 비어있습니다. --xlsx로 먼저 마스터를 적재하세요.")
        return 1
    print(f"역 마스터: {len(master)}개")

    q = (
        client.table("buildings")
        .select("id, name, latitude, longitude")
        .not_.is_("latitude", "null")
        .not_.is_("longitude", "null")
    )
    if limit:
        q = q.limit(limit)
    blds = q.execute().data or []
    print(f"좌표 보유 건물: {len(blds)}건")

    ok = 0
    for b in blds:
        res = nearest_station(float(b["latitude"]), float(b["longitude"]), master)
        if not res:
            continue
        st, dist = res
        ok += 1
        print(f"  OK  {b['name']}: {st['name']}({st.get('line_name') or '-'}) {dist}m")
        if not dry_run:
            # building_commercial_areas에 최근접역만 갱신(없으면 생성)
            client.table("building_commercial_areas").upsert({
                "building_id": b["id"],
                "nearest_station": st["name"],
                "nearest_station_line": st.get("line_name"),
                "nearest_station_distance_m": dist,
            }).execute()
    print(f"\n완료: 최근접역 보강 {ok}/{len(blds)}"
          + (" (dry-run)" if dry_run else ""))
    return 0


def cmd_news(pages: int = 1, dry_run: bool = False, purge_days: int = 14) -> int:
    """상업용 부동산 뉴스를 수집해 Supabase news_articles에 적재한다.

    통계 출력: sector × subcategory 교차표 + 섹터별 샘플 제목.
    적재 후 purge_days일이 지난 오래된 뉴스를 삭제한다(0이면 청소 생략).
    """
    import os
    from collections import defaultdict
    from app.news_fetch import collect_all
    from app.supa_store import store_news, purge_old_news

    # 쓰기 작업이므로 service_role 키 필수 (dry_run 제외)
    if not dry_run and not (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    ):
        print("오류: news 적재는 쓰기 작업입니다. SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
        return 1

    # dry-run은 분류 품질 확인 목적이므로 스크래핑 생략
    print(f"뉴스 수집 중... (pages={pages}, dry_run={dry_run})")
    rows = collect_all(pages=pages, scrape_body=not dry_run)

    if not rows:
        print("수집된 기사 없음 — NAVER_CLIENT_ID/SECRET 설정 또는 검색어 확인 필요")
        return 1

    # sector × subcategory 교차 집계
    SECTORS = ["datacenter", "hotel", "logistics", "office", "retail"]
    SUBS = ["deal", "general", "landlord", "tenant"]

    cross: dict[str, dict[str, int]] = {s: {sub: 0 for sub in SUBS} for s in SECTORS}
    sector_samples: dict[str, list] = defaultdict(list)
    for r in rows:
        sec = r["sector"]
        sub = r.get("subcategory", "general") or "general"
        if sec in cross and sub in cross[sec]:
            cross[sec][sub] += 1
        if len(sector_samples[sec]) < 2:
            sector_samples[sec].append(r["title"])

    total = len(rows)
    print(f"\n수집 결과: 총 {total}건")
    print()

    # 교차표 헤더
    col_w = 8
    header = f"{'sector':<12s}" + "".join(f"{sub:>{col_w}}" for sub in SUBS) + f"{'합계':>{col_w}}"
    print(header)
    print("-" * len(header))
    for sec in SECTORS:
        row_total = sum(cross[sec].values())
        cols = "".join(f"{cross[sec][sub]:>{col_w}}" for sub in SUBS)
        print(f"{sec:<12s}{cols}{row_total:>{col_w}}")
        for title in sector_samples[sec]:
            print(f"  · {title[:62]}")
    print("-" * len(header))
    col_totals = "".join(f"{sum(cross[s][sub] for s in SECTORS):>{col_w}}" for sub in SUBS)
    print(f"{'합계':<12s}{col_totals}{total:>{col_w}}")

    if dry_run:
        print("\n(dry-run) DB 적재 생략")
        return 0

    result = store_news(rows)
    print(
        f"\n적재 완료: 총 {result['total']}건 "
        f"/ 신규 {result['inserted']}건 "
        f"/ 스킵(중복) {result['skipped']}건"
    )

    # TTL 청소 — 수집 시각 기준 purge_days일 경과 뉴스 삭제 (0이면 생략)
    if purge_days > 0:
        deleted = purge_old_news(days=purge_days)
        print(f"오래된 뉴스 정리: {purge_days}일 경과 {deleted}건 삭제")

    return 0


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cli",
        description="임대안내문 PDF 추출 CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ingest 커맨드
    p_ingest = sub.add_parser("ingest", help="단건 PDF 처리")
    p_ingest.add_argument("pdf", help="처리할 PDF 파일 경로")
    p_ingest.add_argument("--out", default="out/", help="출력 디렉토리 (기본: out/)")

    # batch 커맨드
    p_batch = sub.add_parser("batch", help="폴더 내 모든 PDF 일괄 처리")
    p_batch.add_argument("dir", help="PDF가 들어있는 폴더 경로")
    p_batch.add_argument("--out", default="out/", help="출력 디렉토리 (기본: out/)")

    # push 커맨드: PDF 재파싱 → (보강) → Supabase 적재
    p_push = sub.add_parser("push", help="PDF를 파싱해 Supabase에 적재")
    p_push.add_argument("pdf_dir", help="원본 PDF 폴더 경로 (pipeline 재실행용)")
    p_push.add_argument("--out", default="out/", help="JSON 출력 디렉토리 (기본: out/)")
    p_push.add_argument("--enrich", action="store_true",
                        help="건축물대장 API로 빈 필드 보강 후 적재")
    p_push.add_argument("--no-images", action="store_true",
                        help="이미지 추출/Storage 업로드 생략 (텍스트만, 빠름)")

    # geocode 커맨드: buildings 좌표 보강
    p_geo = sub.add_parser("geocode", help="buildings 좌표 보강 (주소→위경도)")
    p_geo.add_argument("--limit", type=int, default=None, help="처리 건수 제한")
    p_geo.add_argument("--dry-run", action="store_true", help="DB 미반영, 결과만 출력")

    # commercial 커맨드: 좌표 반경 발달상권 정보 보강
    p_com = sub.add_parser("commercial", help="발달상권 정보 보강 (좌표→반경 점포 집계)")
    p_com.add_argument("--limit", type=int, default=None, help="처리 건수 제한")
    p_com.add_argument("--radius", type=int, default=300, help="집계 반경(m, 기본 300)")
    p_com.add_argument("--dry-run", action="store_true", help="DB 미반영, 결과만 출력")

    # subway 커맨드: 지하철역 마스터 적재 + 매물 최근접역 보강
    p_sub = sub.add_parser("subway", help="지하철역 좌표 마스터 적재 + 매물 최근접역 보강")
    p_sub.add_argument("--xlsx", default=None,
                       help="레일포털 전국 도시철도역 XLSX 경로 (지정 시 마스터 적재)")
    p_sub.add_argument("--limit", type=int, default=None, help="처리 건수 제한")
    p_sub.add_argument("--dry-run", action="store_true", help="DB 미반영, 결과만 출력")

    # news 커맨드: 네이버 뉴스 수집 → Supabase 적재
    p_news = sub.add_parser("news", help="상업용 부동산 뉴스 수집 → Supabase 적재")
    p_news.add_argument("--pages", type=int, default=1,
                        help="검색어당 수집 페이지 수 (1페이지=100건, 기본 1)")
    p_news.add_argument("--dry-run", action="store_true",
                        help="DB 미반영, 섹터별 카운트·샘플 제목만 출력")
    p_news.add_argument("--purge-days", type=int, default=14,
                        help="수집 후 N일 경과 뉴스 삭제 (기본 14, 0이면 청소 생략)")

    args = parser.parse_args()

    if args.cmd == "ingest":
        return cmd_ingest(args.pdf, args.out)
    elif args.cmd == "batch":
        return cmd_batch(args.dir, args.out)
    elif args.cmd == "push":
        return cmd_push(args.pdf_dir, args.out, enrich=args.enrich,
                        with_images=not args.no_images)
    elif args.cmd == "geocode":
        return cmd_geocode(limit=args.limit, dry_run=args.dry_run)
    elif args.cmd == "commercial":
        return cmd_commercial(limit=args.limit, radius=args.radius,
                              dry_run=args.dry_run)
    elif args.cmd == "subway":
        return cmd_subway(xlsx_path=args.xlsx, limit=args.limit,
                          dry_run=args.dry_run)
    elif args.cmd == "news":
        return cmd_news(pages=args.pages, dry_run=args.dry_run, purge_days=args.purge_days)

    return 0


if __name__ == "__main__":
    sys.exit(main())
