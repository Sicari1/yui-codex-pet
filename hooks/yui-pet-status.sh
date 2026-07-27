#!/usr/bin/env bash
# 유이 펫 상태 기록 훅. 이벤트별 상태 + (stdin JSON의) 현재 작업 내용을 세션 파일에 기록.
# 사용법: yui-pet-status.sh <state>   state: idle|working|needs_input|done|error
#
# 배포 폴더는 YUI_PET_DIR로 지정할 수 있고, 없으면 /mnt/c/Users/*/.yui-pet 를 찾는다.
# (기기마다 Windows 사용자명이 달라 하드코딩하지 않는다.)

STATE="${1:-idle}"
DIR="${2:-${YUI_PET_DIR:-}}"
if [ -z "$DIR" ]; then
  DIR="$(ls -d /mnt/c/Users/*/.yui-pet 2>/dev/null | head -1)"
fi
DIR="${DIR:-$HOME/.yui-pet}"
mkdir -p "$DIR" 2>/dev/null

# 훅은 stdin으로 JSON을 준다(수동 실행 시 stdin이 tty면 빈 입력 처리).
if [ -t 0 ]; then
  printf '' | python3 "$HOME/.claude/yui-pet-status.py" "$STATE" "$DIR" 2>/dev/null
else
  python3 "$HOME/.claude/yui-pet-status.py" "$STATE" "$DIR" 2>/dev/null
fi
exit 0
