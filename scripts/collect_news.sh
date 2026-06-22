#!/usr/bin/env bash
# 뉴스 수집 cron 래퍼 — 1시간마다 실행 권장.
# 멱등 설계라 반복 실행해도 새 기사만 추가되고, 14일 경과분은 자동 삭제된다.
#
# === 로컬 WSL crontab 등록 (서버 배포 전까지 임시 운영용) ===
#   crontab -e  하고 아래 한 줄 추가 (매시 7분에 실행 — 정각 피크 회피):
#     7 * * * * /home/kkhwan/projects/Lease\ Announcemen/scripts/collect_news.sh >> /home/kkhwan/projects/Lease\ Announcemen/logs/news_cron.log 2>&1
#   ⚠️ WSL/PC가 켜져 있을 때만 동작. PC 꺼져 있으면 그 시각은 건너뜀.
#
# === 비활성화 ===
#   crontab -e 에서 해당 줄 삭제 또는 맨 앞에 # 주석.

set -euo pipefail

PROJECT_DIR="/home/kkhwan/projects/Lease Announcemen"
cd "$PROJECT_DIR"

# 가상환경 우선, 없으면 python3
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 뉴스 수집 시작 ====="
# --pages 1: 검색어당 100건. --purge-days 14: 14일 경과분 삭제(사용자 정책).
"$PY" cli.py news --pages 1 --purge-days 14
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 뉴스 수집 종료 ====="
