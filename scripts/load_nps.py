#!/usr/bin/env python3
"""국민연금 가입 사업장 CSV → 법정동별 직장인구 집계 → Supabase 적재.

data.go.kr '국민연금공단_국민연금 가입 사업장 내역' 전국 CSV(cp949)를
고객법정동주소코드(10자리) 단위로 집계한다:
  - 등록 사업장 수(biz_count)
  - 총 가입자수(employee_total) ≈ 직장 종사자
  - 업종(사업장업종코드명) Top 6
건물 단위 매칭은 CSV에 건물번호가 없어 불가 → 법정동 집계가 안정적.

사용법: .venv/bin/python scripts/load_nps.py [--dry-run]
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CSV_PATH = ROOT / "data" / "nps_workplaces.csv"

# 컬럼 인덱스 (헤더 기준, 0-based)
C_PERIOD = 0      # 자료생성년월
C_STATUS = 3      # 사업장가입상태코드 1등록 2탈퇴
C_LDONG = 7       # 고객법정동주소코드(10자리)
C_INDUSTRY = 14   # 사업장업종코드명
C_EMP = 18        # 가입자수


def aggregate() -> tuple[dict, str | None]:
    """CSV를 법정동코드별로 집계. (records, base_period) 반환."""
    biz: collections.Counter[str] = collections.Counter()
    emp: collections.Counter[str] = collections.Counter()
    ind: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )  # 업종별 사업장 수
    ind_emp: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )  # 업종별 종사자 수(가입자수 합)
    period = None

    with open(CSV_PATH, encoding="cp949", errors="replace") as f:
        rd = csv.reader(f)
        next(rd)  # 헤더
        for row in rd:
            if len(row) <= C_EMP:
                continue
            if row[C_STATUS] != "1":  # 등록 사업장만
                continue
            ldong = row[C_LDONG].strip()
            if not ldong:
                continue
            if period is None and row[C_PERIOD]:
                period = row[C_PERIOD].strip()  # 'YYYY-MM'
            try:
                cnt = int(row[C_EMP] or 0)
            except ValueError:
                cnt = 0
            biz[ldong] += 1
            emp[ldong] += cnt
            iname = row[C_INDUSTRY].strip()
            if iname and iname != "BIZ_NO미존재사업장":
                ind[ldong][iname] += 1       # 사업장 수
                ind_emp[ldong][iname] += cnt  # 종사자 수

    records = {}
    for ldong in biz:
        # 사업장수 기준 Top10
        top_biz = [{"name": n, "count": c} for n, c in ind[ldong].most_common(10)]
        # 종사자수 기준 Top10
        top_emp = [
            {"name": n, "count": c} for n, c in ind_emp[ldong].most_common(10)
        ]
        records[ldong] = {
            "ldong_cd": ldong,
            "biz_count": biz[ldong],
            "employee_total": emp[ldong],
            "top_industries": top_biz,
            "top_industries_emp": top_emp,
        }
    # 'YYYY-MM' → 'YYYY.MM'
    base_period = period.replace("-", ".") if period else None
    return records, base_period


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not CSV_PATH.exists():
        print(f"오류: CSV 없음 — {CSV_PATH}")
        return 1

    print(f"집계 시작: {CSV_PATH.name}")
    records, base_period = aggregate()
    print(f"법정동 {len(records)}개, 기준 {base_period}")

    if dry:
        for code in ("1165010800", "1168010100"):
            r = records.get(code)
            if r:
                print(f"  {code}: 사업장 {r['biz_count']}, 종사자 {r['employee_total']}, "
                      f"업종 {[i['name'] for i in r['top_industries'][:3]]}")
        return 0

    from app.supa_store import get_client
    client = get_client()
    rows = list(records.values())
    for r in rows:
        r["base_period"] = base_period
    # 배치 upsert (500개씩)
    for i in range(0, len(rows), 500):
        client.table("dong_workplace_stats").upsert(rows[i:i + 500]).execute()
        print(f"  적재 {min(i + 500, len(rows))}/{len(rows)}")
    print(f"완료: {len(rows)}개 법정동 적재")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
