"""임대료 이상치 검증 스크립트 — 수정 후 파싱 결과의 rent_per_pyeong 분포 확인.

실행:
  .venv/bin/python tests/check_rent_anomalies.py

검증 항목:
  1. rent_per_pyeong > 1,000만 건수 (정상: 0에 가까워야 함)
  2. deposit_per_pyeong > 1억 건수 (정상: 0에 가까워야 함)
  3. 오스카 케이스퀘어 기준층 임대료 200,000/평 회귀
  4. parse_korean_money '빌' 노이즈 제거 확인
  5. cnw 총월임대료 컬럼 → 평당 환산 결과 확인
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from app.pipeline import process_pdf
from app.normalize import parse_korean_money

RAW_DIR = Path(__file__).parent.parent / "Raw"

# ---------------------------------------------------------------------------
# 1. parse_korean_money 노이즈 제거 단위 테스트
# ---------------------------------------------------------------------------

def test_noise_removal():
    """'빌딩', '빌' 아티팩트 제거 후 숫자 파싱 확인."""
    cases = [
        ("8,528,000빌", 8_528_000),
        ("35,940,000빌딩", 35_940_000),
        ("200,000", 200_000),
        ("1억4천만", 140_000_000),   # 정상 한글 단위 — 보존
        ("144,300 44,700", 144_300),  # C&W 셀 병합 → 첫 토큰
        ("담당자문의", None),
        ("", None),
    ]
    ok = True
    for raw, expected in cases:
        result = parse_korean_money(raw)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{status}] parse_korean_money({raw!r}) = {result}  (expected {expected})")
    return ok


# ---------------------------------------------------------------------------
# 2. 4개 PDF 전체 파싱 → rent_per_pyeong 이상치 집계
# ---------------------------------------------------------------------------

ANOMALY_RENT_THRESHOLD = 10_000_000    # 평당 임대료 1,000만원 초과 → 이상치
ANOMALY_DEP_THRESHOLD  = 100_000_000   # 평당 보증금 1억 초과 → 이상치


def run_anomaly_check():
    """4개 PDF 파싱 후 평당 단가 이상치 건수 출력."""
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"[WARN] PDF 없음: {RAW_DIR}")
        return

    rent_anomalies = []
    dep_anomalies = []
    oscar_casesquare_ok = False

    for pdf_path in pdfs:
        print(f"\n--- {pdf_path.name} ---")
        try:
            src_doc = process_pdf(str(pdf_path))
            buildings = src_doc.buildings
        except Exception as e:
            print(f"  [ERROR] 파싱 실패: {e}")
            continue

        for b in buildings:
            for rt in b.rents:
                # 오스카 케이스퀘어 회귀 확인
                if (
                    "케이스퀘어" in b.building_name
                    and rt.rent_per_pyeong is not None
                    and 190_000 <= rt.rent_per_pyeong <= 210_000
                ):
                    oscar_casesquare_ok = True

                # 이상치 수집
                if rt.rent_per_pyeong is not None and rt.rent_per_pyeong > ANOMALY_RENT_THRESHOLD:
                    rent_anomalies.append({
                        "file": pdf_path.name,
                        "building": b.building_name,
                        "scope": rt.scope_label,
                        "rent_per_pyeong": rt.rent_per_pyeong,
                        "rent_raw": rt.terms_raw.get("rent", ""),
                        "rent_total_raw": rt.terms_raw.get("rent_total_raw", ""),
                    })
                if rt.deposit_per_pyeong is not None and rt.deposit_per_pyeong > ANOMALY_DEP_THRESHOLD:
                    dep_anomalies.append({
                        "file": pdf_path.name,
                        "building": b.building_name,
                        "scope": rt.scope_label,
                        "deposit_per_pyeong": rt.deposit_per_pyeong,
                        "deposit_raw": rt.terms_raw.get("deposit", ""),
                    })

        print(f"  건물 {len(buildings)}개 파싱 완료")

    # ---------------------------------------------------------------------------
    # 결과 출력
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("검증 결과 요약")
    print("=" * 60)

    print(f"\n[rent_per_pyeong > 1,000만] 이상치: {len(rent_anomalies)}건")
    for a in rent_anomalies[:10]:
        print(f"  {a['file']} / {a['building']} / {a['scope']}: "
              f"{a['rent_per_pyeong']:,.0f} (raw={a['rent_raw']!r}, total_raw={a['rent_total_raw']!r})")

    print(f"\n[deposit_per_pyeong > 1억] 이상치: {len(dep_anomalies)}건")
    for a in dep_anomalies[:10]:
        print(f"  {a['file']} / {a['building']} / {a['scope']}: "
              f"{a['deposit_per_pyeong']:,.0f} (raw={a['deposit_raw']!r})")

    casesquare_status = "OK" if oscar_casesquare_ok else "MISS (200,000/평 행 미발견)"
    print(f"\n[케이스퀘어 기준층 임대료 ~200,000/평 회귀]: {casesquare_status}")

    all_ok = len(rent_anomalies) == 0 and len(dep_anomalies) == 0 and oscar_casesquare_ok
    print("\n" + ("ALL PASS" if all_ok else "이상치 존재 — 상세 로그 확인 필요"))
    return all_ok


if __name__ == "__main__":
    print("=" * 60)
    print("1. parse_korean_money 노이즈 제거 단위 테스트")
    print("=" * 60)
    noise_ok = test_noise_removal()

    print("\n" + "=" * 60)
    print("2. 4개 PDF 전체 파싱 이상치 검사")
    print("=" * 60)
    anomaly_ok = run_anomaly_check()

    sys.exit(0 if (noise_ok and anomaly_ok) else 1)
