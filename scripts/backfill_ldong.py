#!/usr/bin/env python3
"""building_commercial_areas.ldong_cd 백필.

상권 점포 API(storeListInRadius) 1페이지만 호출해 최빈 법정동코드(ldongCd)를
얻어 채운다. 거주인구/세부업종 재호출 없이 가벼움. 직장인구(dong_workplace_stats)
조인에 필요한 ldong_cd만 보강.

사용법: .venv/bin/python scripts/backfill_ldong.py
"""
from __future__ import annotations

import collections
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ.get(
    "SDSC2_BASE_URL", "https://apis.data.go.kr/B553077/api/open/sdsc2"
).strip()
KEY = os.environ["DATAGO_SERVICE_KEY"].strip()
UA = "lease-platform/1.0"


def top_ldong(lat: float, lon: float, radius: int = 300) -> str | None:
    """반경 점포 1페이지에서 최빈 법정동코드."""
    with httpx.Client(timeout=20.0, headers={"User-Agent": UA}) as c:
        r = c.get(f"{BASE}/storeListInRadius", params={
            "serviceKey": KEY, "radius": str(radius),
            "cx": str(lon), "cy": str(lat),
            "type": "json", "numOfRows": "500", "pageNo": "1",
        })
        r.raise_for_status()
        items = (r.json().get("body", {}) or {}).get("items", []) or []
    codes = collections.Counter(
        (it.get("ldongCd") or "").strip() for it in items if it.get("ldongCd")
    )
    return codes.most_common(1)[0][0] if codes else None


def main() -> int:
    from app.supa_store import get_client
    client = get_client()
    rows = (
        client.table("building_commercial_areas")
        .select("building_id")
        .is_("ldong_cd", "null")
        .execute()
        .data or []
    )
    # 좌표 조인
    print(f"ldong_cd 미보유: {len(rows)}건")
    ok = fail = 0
    for r in rows:
        bid = r["building_id"]
        b = (
            client.table("buildings")
            .select("latitude, longitude, name")
            .eq("id", bid)
            .single()
            .execute()
            .data
        )
        if not b or b.get("latitude") is None:
            continue
        try:
            code = top_ldong(float(b["latitude"]), float(b["longitude"]))
        except Exception as exc:
            fail += 1
            print(f"  -- {b.get('name')}: {type(exc).__name__}")
            continue
        if code:
            client.table("building_commercial_areas").update(
                {"ldong_cd": code}
            ).eq("building_id", bid).execute()
            ok += 1
    print(f"완료: {ok} 채움 / {fail} 실패")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
