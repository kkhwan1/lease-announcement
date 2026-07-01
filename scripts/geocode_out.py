"""out/*.json 파일 전체를 순회하며 latitude/longitude를 채우는 배치 스크립트.

실행 방법:
    source .venv/bin/activate
    python scripts/geocode_out.py 2>&1 | tee logs/geocode_out.log
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (app.geocode 임포트)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from app.geocode import geocode_address  # noqa: E402

OUT_DIR = PROJECT_ROOT / "out"
KAKAO_KEY = os.environ.get("KAKAO_REST_API_KEY")

json_files = sorted(OUT_DIR.glob("*.json"))
total = len(json_files)

success = 0
skipped = 0
failed = 0
failed_addrs: list[str] = []

print(f"[지오코딩 배치] 대상 파일: {total}건")
print(f"[지오코딩 배치] KAKAO_KEY 존재: {'예' if KAKAO_KEY else '아니오(VWORLD 폴백 사용)'}")
print("-" * 60)

for idx, fpath in enumerate(json_files, start=1):
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    # 이미 좌표가 있으면 스킵 (멱등)
    if data.get("latitude") is not None and data.get("longitude") is not None:
        skipped += 1
        print(f"[{idx:3d}/{total}] 스킵(이미 좌표 보유): {fpath.name}")
        continue

    addr = data.get("address_road") or data.get("address_raw")
    if not addr:
        failed += 1
        failed_addrs.append(f"{fpath.name} (주소 없음)")
        print(f"[{idx:3d}/{total}] 실패(주소 없음): {fpath.name}")
        continue

    pt = geocode_address(addr, KAKAO_KEY)

    if pt:
        data["latitude"] = pt.lat
        data["longitude"] = pt.lng
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        success += 1
        print(f"[{idx:3d}/{total}] 성공: {fpath.name} → ({pt.lat:.4f}, {pt.lng:.4f})")
    else:
        failed += 1
        failed_addrs.append(f"{fpath.name} | 주소: {addr}")
        print(f"[{idx:3d}/{total}] 실패: {fpath.name} | 주소: {addr}")

    time.sleep(0.2)

print("=" * 60)
print(f"[완료] 성공: {success}건 / 실패: {failed}건 / 스킵: {skipped}건 / 합계: {total}건")

if failed_addrs:
    print("\n[실패 주소 목록]")
    for item in failed_addrs:
        print(f"  - {item}")
