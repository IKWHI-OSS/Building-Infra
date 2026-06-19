#!/usr/bin/env bash
# 오케스트레이터 PoC — 격리 환경 1회 셋업.
# 시스템 파이썬과 분리된 venv에 잠긴 버전 설치 + 주피터 커널 등록 → pydantic 등 충돌 회피.
# 사용법:  cd <이 폴더>  &&  bash setup_env.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PYBIN="${PYBIN:-python3}"          # 다른 파이썬 쓰려면: PYBIN=/path/to/python3 bash setup_env.sh
VENV="$HERE/.venv"               # .gitignore의 .venv/ 에 걸려 git 미추적

echo "[1/4] venv 생성: $VENV"
"$PYBIN" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "[2/4] pip 업그레이드"
python -m pip install -U pip -q

echo "[3/4] 잠긴 버전 설치 (requirements-lock.txt)"
pip install -q -r "$HERE/requirements-lock.txt"

echo "[4/4] 주피터 커널 등록: 'Python (orc-poc)'"
pip install -q ipykernel
python -m ipykernel install --user --name orc-poc --display-name "Python (orc-poc)"

echo
echo "================ 완료 ================"
echo "1) 주피터에서 orchestrator_slice.ipynb 열기"
echo "2) 우상단 커널을 'Python (orc-poc)'로 변경"
echo "3) 첫 셀의 %pip 줄은 '실행하지 마세요'(이미 설치됨). 바로 Run All."
echo "   (.env의 CLAUDE_KEY는 노트북이 자동 로드)"
echo "====================================="
