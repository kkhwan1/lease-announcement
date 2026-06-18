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
from collections import defaultdict
from pathlib import Path

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

def cmd_push(pdf_dir: str, out_dir: str, enrich: bool = False) -> int:
    """폴더 내 모든 PDF를 파싱해 Supabase에 적재.

    흐름:
      1. 폴더 내 PDF 목록 수집
      2. 각 PDF: pipeline.process_pdf → SourceDocument
      3. (enrich=True) 각 건물에 건축물대장 API 보강 (빈 필드만 채움)
      4. supa_store.store_document → Supabase upsert
      5. 중개사별 적재 통계 출력
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
        try:
            source_doc = process_pdf(pdf)
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

    args = parser.parse_args()

    if args.cmd == "ingest":
        return cmd_ingest(args.pdf, args.out)
    elif args.cmd == "batch":
        return cmd_batch(args.dir, args.out)
    elif args.cmd == "push":
        return cmd_push(args.pdf_dir, args.out, enrich=args.enrich)

    return 0


if __name__ == "__main__":
    sys.exit(main())
