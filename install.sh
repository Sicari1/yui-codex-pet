#!/usr/bin/env bash
# 유이 펫 배치 스크립트. repo의 파일을 실행 위치로 옮기고 훅을 등록합니다.
#
#   ./install.sh              배치 + 훅 등록
#   ./install.sh --dry-run    무엇을 할지만 보여줍니다
#   ./install.sh --no-hooks   파일만 배치(훅 등록 생략)
#   ./install.sh --uninstall  훅 해제 + 설치한 파일 제거(개인 설정·스프라이트는 남깁니다)
#
# 배치 위치는 YUI_PET_DIR로 지정할 수 있습니다. 없으면 /mnt/c/Users/*/.yui-pet 를 찾고,
# 그것도 없으면 Windows 사용자 폴더 아래에 만듭니다. 파이썬 경로도 알아서 찾습니다.
#
# 여러 번 실행해도 안전합니다. 개인 설정(config.json)과 스프라이트, 세션 기록은
# 이미 있으면 건드리지 않습니다.
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
  [ -z "$win_home" ] && { echo "Windows 사용자 폴더를 찾지 못했습니다. YUI_PET_DIR로 지정해 주세요." >&2; exit 1; }
  DIR="$win_home/.yui-pet"
fi
CLAUDE_DIR="$HOME/.claude"
BIN_DIR="$HOME/.local/bin"
SETTINGS="$CLAUDE_DIR/settings.json"

PYW="$( { ls -d /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/pythonw.exe 2>/dev/null || true
          ls -d '/mnt/c/Program Files/Python3'*/pythonw.exe 2>/dev/null || true; } | head -1 )"
# 훅은 stdin으로 JSON을 받으므로 콘솔 핸들이 있는 python.exe 를 쓴다(pythonw는 stdin이 없다).
PYEXE="${PYW%pythonw.exe}python.exe"
[ -e "$PYEXE" ] || PYEXE=""

# Codex 홈 — 데스크톱(윈도우)과 CLI(WSL) 둘 다 있을 수 있어 각각 등록한다.
CODEX_WIN="$(dirname "$DIR")/.codex"
CODEX_WSL="$HOME/.codex"

echo "배치 위치: $DIR"
[ "$DRY" = 1 ] && echo "(dry-run — 실제로 바꾸지 않습니다)"

# ---- 제거 ----
if [ "$UNINSTALL" = 1 ]; then
  echo "제거"
  for f in yui_pet.py lines.json 유이펫-시작.bat 유이펫-실행.vbs restart.sh; do
    [ -e "$DIR/$f" ] && { run rm -f "$DIR/$f"; say "$f"; }
  done
  desk="$(powershell.exe -NoProfile -Command '[Environment]::GetFolderPath("Desktop")' 2>/dev/null | tr -d '\r' || true)"
  if [ -n "$desk" ] && desk_wsl="$(wslpath -u "$desk" 2>/dev/null)" && [ -e "$desk_wsl/유이펫.lnk" ]; then
    run rm -f "$desk_wsl/유이펫.lnk"; say "바탕화면 유이펫.lnk"
  fi
  [ -d "$DIR/fonts" ] && run rm -rf "$DIR/fonts"
  [ -d "$DIR/icons" ] && run rm -rf "$DIR/icons"
  [ -d "$DIR/pets" ] && run rm -rf "$DIR/pets"
  run rm -f "$CLAUDE_DIR/yui-pet-status.py" "$CLAUDE_DIR/yui-pet-status.sh" "$BIN_DIR/yui"
  run rm -f "$DIR/yui-pet-status.py" "$DIR/yui-pet-status.cmd"
  run rm -f "$CODEX_WSL/yui-pet-status.py" "$CODEX_WSL/yui-pet-status.sh"
  say "훅 · CLI 제거"
  say "config.json · 스프라이트 · sessions 는 남겨 뒀습니다"
  if [ "$DRY" = 0 ]; then
    YUI_SETTINGS="$SETTINGS" python3 "$REPO/tools/_hookreg.py" remove
    for ch in "$CODEX_WIN" "$CODEX_WSL"; do
      [ -f "$ch/hooks.json" ] && YUI_CODEX_HOME="$ch" python3 "$REPO/tools/_hookreg_codex.py" remove
    done
  fi
  echo; echo "제거했습니다. 펫이 떠 있으면 트레이에서 종료해 주세요."
  exit 0
fi

# ---- 앱 ----
echo "앱"
run mkdir -p "$DIR/fonts" "$DIR/sessions/claude" "$DIR/sessions/codex" "$BIN_DIR" "$CLAUDE_DIR"
for f in yui_pet.py lines.json; do
  run cp "$REPO/overlay/$f" "$DIR/$f"; say "$f"
done
run cp -r "$REPO/overlay/fonts/." "$DIR/fonts/"; say "fonts/"
run mkdir -p "$DIR/icons"
run cp -r "$REPO/overlay/icons/." "$DIR/icons/"; say "icons/"

if [ -e "$DIR/config.json" ]; then
  say "config.json — 이미 있어 그대로 둡니다(크기 등 개인 설정)"
else
  run cp "$REPO/overlay/config.json" "$DIR/config.json"; say "config.json (새로)"
fi

# ---- 스프라이트 ----
echo "스프라이트"
if [ -e "$DIR/spritesheet.webp" ]; then
  say "spritesheet.webp — 이미 있어 그대로 둡니다"
else
  run cp "$REPO/pets/yui/spritesheet.webp" "$DIR/spritesheet.webp"; say "spritesheet.webp"
fi
# 갈아탈 수 있는 다른 펫들 (우클릭 → 펫 바꾸기)
for pd in "$REPO"/pets/*/; do
  pid="$(basename "$pd")"
  [ "$pid" = "yui" ] && continue
  run mkdir -p "$DIR/pets/$pid"
  [ -e "$pd/pet.json" ] && run cp "$pd/pet.json" "$DIR/pets/$pid/pet.json"
  for sh in spritesheet.webp spritesheet.png; do
    [ -e "$pd/$sh" ] && [ ! -e "$DIR/pets/$pid/$sh" ] && run cp "$pd/$sh" "$DIR/pets/$pid/$sh"
  done
  say "pets/$pid"
done

if ls "$DIR"/spritesheet-*x.png >/dev/null 2>&1; then
  say "고해상 시트 있음 — 그대로 씁니다"
else
  say "고해상 시트 없음 — 원본으로 동작합니다(확대 상한 1.7배)"
  say "  만들려면 tools/upscale_spritesheet.py (CUDA 필요). 자세한 건 ROADMAP 참고"
fi

# ---- 실행 스크립트 (파이썬 경로가 기기마다 달라 설치 시점에 만든다) ----
echo "실행 스크립트"
if [ -z "$PYW" ]; then
  say "주의: pythonw.exe 를 찾지 못했습니다. Python 설치 후 다시 실행해 주세요"
elif [ "$DRY" = 1 ]; then
  say "[dry] 유이펫-시작.bat · restart.sh · 유이펫-실행.vbs 생성 + 바탕화면 바로가기 (python: $PYW)"
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

  # 바탕화면에서 한 번에 켜는 실행기. 검은 창 없이 뜨고, 켤 때마다
  # repo의 최신 코드를 배치 폴더로 옮긴 뒤 실행한다(= 항상 최신으로 돈다).
  win_dir="$(wslpath -w "$DIR" 2>/dev/null || echo "$DIR")"
  # wscript는 UTF-8 BOM을 못 읽는다. 한글 주석을 살리려면 UTF-16LE로 써야 한다.
  cat > "$DIR/.vbs.tmp" <<VBS
' 유이 펫 실행기 — install.sh가 만든 파일이다. 고치려면 install.sh 쪽을 고쳐라.
'   1) repo 최신 코드를 배치 폴더로 동기화
'   2) 이미 떠 있는 유이만 골라 종료(다른 파이썬 앱은 건드리지 않는다)
'   3) 콘솔 창 없이 실행
Option Explicit
Dim sh, wmi, procs, p
Set sh = CreateObject("WScript.Shell")

On Error Resume Next

Set wmi = GetObject("winmgmts:\\\\.\\root\\cimv2")
Set procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='pythonw.exe'")
For Each p In procs
    If Not IsNull(p.CommandLine) Then
        If InStr(LCase(p.CommandLine), "yui_pet.py") > 0 Then p.Terminate()
    End If
Next
Err.Clear

' repo가 없거나 동기화가 실패해도 펫은 그대로 켠다
sh.Run "wsl.exe -e bash -lc ""cd '$REPO' && ./install.sh --no-hooks""", 0, True
Err.Clear

On Error Goto 0
sh.Run """$win_pyw"" ""$win_script""", 0, False
VBS
  printf '\xFF\xFE' > "$DIR/유이펫-실행.vbs"
  iconv -f UTF-8 -t UTF-16LE < "$DIR/.vbs.tmp" >> "$DIR/유이펫-실행.vbs"
  rm -f "$DIR/.vbs.tmp"
  say "유이펫-실행.vbs (켤 때마다 최신 코드로 동기화)"

  # 바탕화면 바로가기 — 아이콘까지 붙여 프로그램처럼 보이게 한다
  ps1="$DIR/.mkshortcut.ps1"
  printf '\xEF\xBB\xBF' > "$ps1"   # BOM: 한글 경로가 안 깨지게
  cat >> "$ps1" <<PS1
\$desk = [Environment]::GetFolderPath('Desktop')
\$lnk  = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path \$desk '유이펫.lnk'))
\$lnk.TargetPath       = "\$env:SystemRoot\\System32\\wscript.exe"
\$lnk.Arguments        = '"$win_dir\유이펫-실행.vbs"'
\$lnk.WorkingDirectory = '$win_dir'
\$lnk.IconLocation     = '$win_dir\icons\yui.ico'
\$lnk.Description      = '히라사와 유이 데스크톱 펫'
\$lnk.Save()
Write-Output \$lnk.FullName
PS1
  if desk_lnk="$(powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$ps1")" 2>/dev/null | tr -d '\r')"; then
    say "바탕화면 바로가기: ${desk_lnk:-유이펫.lnk}"
  else
    say "주의: 바탕화면 바로가기를 만들지 못했습니다. $DIR/유이펫-실행.vbs 를 직접 보내면 됩니다"
  fi
  rm -f "$ps1"
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
  *) say "주의: $BIN_DIR 가 PATH에 없습니다. .bashrc에 추가해 주세요" ;;
esac

# ---- Codex 훅 파일 ----
# 데스크톱(윈도우)판은 훅 명령을 윈도우에서 돌리므로 배치 폴더에 .cmd 래퍼를 둔다.
# WSL의 codex CLI 는 bash 로 돌아서 ~/.codex 에 .sh 를 둔다.
echo "Codex 훅 파일"
if [ -d "$CODEX_WIN" ]; then
  run cp "$REPO/hooks/yui-pet-status.py" "$DIR/yui-pet-status.py"; say "$DIR/yui-pet-status.py"
  if [ -z "$PYEXE" ]; then
    say "주의: python.exe 를 찾지 못했습니다. Codex 데스크톱 훅은 건너뜁니다"
  elif [ "$DRY" = 1 ]; then
    say "[dry] yui-pet-status.cmd 생성 (python: $PYEXE)"
  else
    win_dir_c="$(wslpath -w "$DIR" 2>/dev/null || echo "$DIR")"
    win_py="$(wslpath -w "$PYEXE" 2>/dev/null || echo "$PYEXE")"
    # 콘솔 출력이 stdout으로 새면 Codex가 훅 응답으로 잘못 읽는다. 전부 막고 0으로 끝낸다.
    printf '@echo off\r\nset "YUI_PET_DIR=%s"\r\nset "YUI_PET_SOURCE=codex"\r\n"%s" "%%~dp0yui-pet-status.py" %%1 2>nul\r\nexit /b 0\r\n' \
      "$win_dir_c" "$win_py" > "$DIR/yui-pet-status.cmd"
    say "yui-pet-status.cmd (python: $PYEXE)"
  fi
else
  say "윈도우 Codex 홈이 없습니다 — 건너뜁니다"
fi
if [ -d "$CODEX_WSL" ]; then
  run cp "$REPO/hooks/yui-pet-status.py" "$CODEX_WSL/yui-pet-status.py"; say "$CODEX_WSL/yui-pet-status.py"
  run cp "$REPO/hooks/yui-pet-status.sh" "$CODEX_WSL/yui-pet-status.sh"
  run chmod +x "$CODEX_WSL/yui-pet-status.sh"; say "$CODEX_WSL/yui-pet-status.sh"
else
  say "WSL Codex 홈이 없습니다 — 건너뜁니다"
fi

# ---- 훅 등록 ----
if [ "$HOOKS" = 1 ]; then
  echo "Claude 훅 등록"
  if [ "$DRY" = 1 ]; then
    say "[dry] settings.json 의 8개 이벤트에 등록 + YUI_PET_DIR 설정"
  else
    YUI_SETTINGS="$SETTINGS" YUI_DIR="$DIR" python3 "$REPO/tools/_hookreg.py" add
  fi

  echo "Codex 훅 등록"
  if [ "$DRY" = 1 ]; then
    say "[dry] $CODEX_WIN/hooks.json · $CODEX_WSL/hooks.json 의 7개 이벤트에 등록"
  else
    if [ -d "$CODEX_WIN" ] && [ -n "$PYEXE" ]; then
      YUI_CODEX_HOME="$CODEX_WIN" YUI_MODE=windows \
        YUI_WIN_DIR="$(wslpath -w "$DIR" 2>/dev/null || echo "$DIR")" \
        python3 "$REPO/tools/_hookreg_codex.py" add
    fi
    if [ -d "$CODEX_WSL" ]; then
      YUI_CODEX_HOME="$CODEX_WSL" YUI_MODE=wsl python3 "$REPO/tools/_hookreg_codex.py" add
    fi
  fi
fi

echo
if [ "$DRY" = 1 ]; then
  echo "dry-run을 마쳤습니다. 실제로 적용하려면 옵션 없이 다시 실행해 주세요."
else
  echo "완료."
  echo "  실행: $DIR/restart.sh   (또는 유이펫-시작.bat 더블클릭)"
  echo "  훅은 새 Claude 세션부터 적용됩니다."
fi
