#!/usr/bin/env bash
# 유이 펫 배치 스크립트 — repo에서 실행 위치로 파일을 옮기고 훅을 등록한다.
#
#   ./install.sh              배치 + 훅 등록
#   ./install.sh --dry-run    무엇을 할지만 보여준다
#   ./install.sh --no-hooks   파일만 배치(훅 등록 생략)
#   ./install.sh --uninstall  훅 해제 + 설치한 파일 제거(개인 설정·스프라이트는 남긴다)
#
# 배치 위치는 YUI_PET_DIR로 지정할 수 있다. 없으면 /mnt/c/Users/*/.yui-pet 를 찾고,
# 그것도 없으면 Windows 사용자 폴더 아래에 만든다. 파이썬 경로도 자동으로 찾는다.
#
# 여러 번 실행해도 안전하다. 개인 설정(config.json)과 스프라이트, 세션 기록은
# 이미 있으면 건드리지 않는다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY=0; HOOKS=1; UNINSTALL=0
for a in "$@"; do
  case "$a" in
    --dry-run)   DRY=1 ;;
    --no-hooks)  HOOKS=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help)   sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "모르는 옵션: $a" >&2; exit 2 ;;
  esac
done

say() { printf '  %s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then say "[dry] $*"; else "$@"; fi; }

# ---- 위치 정하기 ----
DIR="${YUI_PET_DIR:-}"
[ -z "$DIR" ] && DIR="$(ls -d /mnt/c/Users/*/.yui-pet 2>/dev/null | head -1 || true)"
if [ -z "$DIR" ]; then
  win_home="$(ls -d /mnt/c/Users/* 2>/dev/null \
             | grep -vE '/(Public|Default|Default User|All Users)$' | head -1 || true)"
  [ -z "$win_home" ] && { echo "Windows 사용자 폴더를 찾지 못했다. YUI_PET_DIR를 지정해라." >&2; exit 1; }
  DIR="$win_home/.yui-pet"
fi
CLAUDE_DIR="$HOME/.claude"
BIN_DIR="$HOME/.local/bin"
SETTINGS="$CLAUDE_DIR/settings.json"

PYW="$( { ls -d /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/pythonw.exe 2>/dev/null || true
          ls -d '/mnt/c/Program Files/Python3'*/pythonw.exe 2>/dev/null || true; } | head -1 )"

echo "배치 위치: $DIR"
[ "$DRY" = 1 ] && echo "(dry-run — 실제로 바꾸지 않는다)"

# ---- 제거 ----
if [ "$UNINSTALL" = 1 ]; then
  echo "제거"
  for f in yui_pet.py lines.json 유이펫-시작.bat restart.sh; do
    [ -e "$DIR/$f" ] && { run rm -f "$DIR/$f"; say "$f"; }
  done
  [ -d "$DIR/fonts" ] && run rm -rf "$DIR/fonts"
  [ -d "$DIR/icons" ] && run rm -rf "$DIR/icons"
  [ -d "$DIR/pets" ] && run rm -rf "$DIR/pets"
  run rm -f "$CLAUDE_DIR/yui-pet-status.py" "$CLAUDE_DIR/yui-pet-status.sh" "$BIN_DIR/yui"
  say "훅 · CLI 제거"
  say "config.json · 스프라이트 · sessions 는 남겨 뒀다"
  [ "$DRY" = 0 ] && YUI_SETTINGS="$SETTINGS" python3 "$REPO/tools/_hookreg.py" remove
  echo; echo "제거 완료. 펫이 떠 있으면 트레이에서 종료해라."
  exit 0
fi

# ---- 앱 ----
echo "앱"
run mkdir -p "$DIR/fonts" "$DIR/sessions/claude" "$BIN_DIR" "$CLAUDE_DIR"
for f in yui_pet.py lines.json; do
  run cp "$REPO/claude-overlay/$f" "$DIR/$f"; say "$f"
done
run cp -r "$REPO/claude-overlay/fonts/." "$DIR/fonts/"; say "fonts/"
run mkdir -p "$DIR/icons"
run cp -r "$REPO/claude-overlay/icons/." "$DIR/icons/"; say "icons/"

if [ -e "$DIR/config.json" ]; then
  say "config.json — 이미 있어 그대로 둔다(크기 등 개인 설정)"
else
  run cp "$REPO/claude-overlay/config.json" "$DIR/config.json"; say "config.json (새로)"
fi

# ---- 스프라이트 ----
echo "스프라이트"
if [ -e "$DIR/spritesheet.webp" ]; then
  say "spritesheet.webp — 이미 있어 그대로 둔다"
elif [ -e "$REPO/pets/current-yui/spritesheet.webp" ]; then
  run cp "$REPO/pets/current-yui/spritesheet.webp" "$DIR/spritesheet.webp"; say "spritesheet.webp"
else
  say "스프라이트 미포함(공개본) — SPRITE_SPEC.md 규격으로 직접 만들어 $DIR/spritesheet.webp 에 두어라"
fi
# 갈아탈 수 있는 다른 펫들 (우클릭 → 펫 바꾸기)
for pd in "$REPO"/pets/*/; do
  pid="$(basename "$pd")"
  [ "$pid" = "current-yui" ] && continue
  run mkdir -p "$DIR/pets/$pid"
  [ -e "$pd/pet.json" ] && run cp "$pd/pet.json" "$DIR/pets/$pid/pet.json"
  for sh in spritesheet.webp spritesheet.png; do
    [ -e "$pd/$sh" ] && [ ! -e "$DIR/pets/$pid/$sh" ] && run cp "$pd/$sh" "$DIR/pets/$pid/$sh"
  done
  say "pets/$pid"
done

if ls "$DIR"/spritesheet-*x.png >/dev/null 2>&1; then
  say "고해상 시트 있음 — 그대로 쓴다"
else
  say "고해상 시트 없음 — 원본으로 동작한다(확대 상한 1.7배)"
  say "  만들려면 tools/upscale_spritesheet.py (CUDA 필요). 자세한 건 ROADMAP 참고"
fi

# ---- 실행 스크립트 (파이썬 경로가 기기마다 달라 설치 시점에 만든다) ----
echo "실행 스크립트"
if [ -z "$PYW" ]; then
  say "주의: pythonw.exe 를 찾지 못했다. Python 설치 후 다시 실행해라"
elif [ "$DRY" = 1 ]; then
  say "[dry] 유이펫-시작.bat · restart.sh 생성 (python: $PYW)"
else
  win_script="$(wslpath -w "$DIR/yui_pet.py" 2>/dev/null || echo "$DIR/yui_pet.py")"
  win_pyw="$(wslpath -w "$PYW" 2>/dev/null || echo "$PYW")"
  printf '@echo off\r\nstart "" "%s" "%s"\r\n' "$win_pyw" "$win_script" > "$DIR/유이펫-시작.bat"
  cat > "$DIR/restart.sh" <<RESTART
#!/usr/bin/env bash
# 오버레이 재시작. install.sh가 만든 파일이다.
/mnt/c/Windows/System32/taskkill.exe /F /IM pythonw.exe >/dev/null 2>&1
sleep 1
cd "$DIR"
setsid nohup "$PYW" "$win_script" </dev/null >/dev/null 2>&1 &
disown
RESTART
  chmod +x "$DIR/restart.sh"
  say "유이펫-시작.bat · restart.sh (python: $PYW)"
fi

# ---- 훅 · CLI ----
echo "훅 · CLI"
run cp "$REPO/hooks/yui-pet-status.py" "$CLAUDE_DIR/yui-pet-status.py"; say "~/.claude/yui-pet-status.py"
run cp "$REPO/hooks/yui-pet-status.sh" "$CLAUDE_DIR/yui-pet-status.sh"; say "~/.claude/yui-pet-status.sh"
run chmod +x "$CLAUDE_DIR/yui-pet-status.sh"
run cp "$REPO/tools/yui" "$BIN_DIR/yui"; say "~/.local/bin/yui"
run chmod +x "$BIN_DIR/yui"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "주의: $BIN_DIR 가 PATH에 없다. .bashrc에 추가해라" ;;
esac

# ---- settings.json 훅 등록 ----
if [ "$HOOKS" = 1 ]; then
  echo "Claude 훅 등록"
  if [ "$DRY" = 1 ]; then
    say "[dry] settings.json 의 8개 이벤트에 등록 + YUI_PET_DIR 설정"
  else
    YUI_SETTINGS="$SETTINGS" YUI_DIR="$DIR" python3 "$REPO/tools/_hookreg.py" add
  fi
fi

echo
if [ "$DRY" = 1 ]; then
  echo "dry-run 끝. 실제로 하려면 옵션 없이 다시 실행해라."
else
  echo "완료."
  echo "  실행: $DIR/restart.sh   (또는 유이펫-시작.bat 더블클릭)"
  echo "  훅은 새 Claude 세션부터 적용된다."
fi
