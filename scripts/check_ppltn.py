#!/usr/bin/env python3
"""행정안전부 주민등록 인구·세대현황 API(법정동별/행정동별) 실호출 검증.

사용법: python3 scripts/check_ppltn.py
  자동승인 직후 403이면 키-서비스 매핑 전파 지연 → 수 분~수십 분 후 재시도.
"""
import pathlib
import urllib.error
import urllib.parse
import urllib.request

env = {}
env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

KEY = env["DATAGO_SERVICE_KEY"]


def call(base, path, label):
    params = {"serviceKey": KEY, "type": "json", "numOfRows": "2", "pageNo": "1"}
    url = base + path + "?" + urllib.parse.urlencode(params, safe="")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
        print(f"[{label}] HTTP {resp.status}  {body[:350]}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"[{label}] HTTPError {exc.code}  {body[:350]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] ERR {type(exc).__name__}: {exc}")


def probe(base, path, params, label):
    url = base + path + "?" + urllib.parse.urlencode(
        {**params, "serviceKey": KEY, "type": "json"}, safe=""
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            print(f"[{label}] {resp.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.HTTPError as exc:
        print(f"[{label}] HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] ERR {type(exc).__name__}: {exc}")
    print("---")


if __name__ == "__main__":
    call(env["STDG_PPLTN_BASE_URL"], "/selectStdgPpltnHhStus", "법정동별(기존)")
    call(env["ADMM_PPLTN_BASE_URL"], "/selectAdmmPpltnHhStus", "행정동별(신규)")
    print("=== 파라미터 조합 탐색 (법정동별, 강남구 역삼동 1168010100) ===")
    sb = env["STDG_PPLTN_BASE_URL"]
    sp = "/selectStdgPpltnHhStus"
    probe(sb, sp, {"numOfRows": "3", "pageNo": "1", "admmCd": "1168010100",
                   "srchFrYm": "202604", "srchToYm": "202604"}, "admmCd+ym")
    probe(sb, sp, {"numOfRows": "3", "pageNo": "1", "stdgCd": "1168010100"}, "stdgCd")
    probe(sb, sp, {"numOfRows": "3", "pageNo": "1", "lv": "3",
                   "admmCd": "11680"}, "lv+admmCd")
