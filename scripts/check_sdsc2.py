#!/usr/bin/env python3
"""소상공인시장진흥공단 상가(상권)정보 API 실호출 검증.

사용법: python3 scripts/check_sdsc2.py
  .env의 DATAGO_SERVICE_KEY / SDSC2_BASE_URL 사용.
  자동승인 직후 403이면 키-서비스 매핑 전파 지연 → 수 분~수십 분 후 재시도.
"""
import pathlib
import urllib.error
import urllib.parse
import urllib.request

# .env 간단 로드
env = {}
env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

KEY = env["DATAGO_SERVICE_KEY"]
BASE = env.get("SDSC2_BASE_URL", "https://apis.data.go.kr/B553077/api/open/sdsc2")


def call(path, params, label):
    query = urllib.parse.urlencode(
        {**params, "serviceKey": KEY, "type": "json"}, safe=""
    )
    url = f"{BASE}{path}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
        print(f"[{label}] HTTP {resp.status}  {body[:300]}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"[{label}] HTTPError {exc.code}  {body[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] ERR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    # 업종 대분류(좌표 불필요 — 가장 단순한 호출)
    call("/largeUpjongList", {"numOfRows": "3", "pageNo": "1"}, "업종대분류")
    # 반경내 상가업소(강남 테헤란로 부근 좌표 반경 300m)
    call(
        "/storeListInRadius",
        {"radius": "300", "cx": "127.0276", "cy": "37.4979",
         "numOfRows": "3", "pageNo": "1"},
        "반경내업소",
    )
