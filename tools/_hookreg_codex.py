#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codex 홈의 hooks.json 에 유이펫 훅을 등록/해제한다. install.sh가 부른다.

Codex 훅은 클로드와 payload 형태가 같아서 기록 스크립트를 그대로 쓴다. 다만 훅을
어디서 실행하느냐가 달라 명령 문자열을 두 갈래로 만든다.

  windows : Codex 데스크톱(윈도우)이 실행 → 배치 폴더의 yui-pet-status.cmd
  wsl     : WSL의 codex CLI가 실행       → 같은 폴더의 yui-pet-status.sh

기존 설정과 다른 훅은 건드리지 않는다. 유이펫 훅(yui-pet-status가 들어간 명령)만
갈아끼우거나 뺀다. 바꾸기 전에 hooks.json.bak-yui 로 백업한다.

  python3 _hookreg_codex.py add     환경변수 YUI_CODEX_HOME, YUI_MODE, (windows면 YUI_WIN_DIR)
  python3 _hookreg_codex.py remove  환경변수 YUI_CODEX_HOME
"""
import collections
import json
import os
import shutil
import sys

# (이벤트, 상태). Codex에는 클로드의 StopFailure·Notification이 없고,
# 승인 대기는 PermissionRequest가 맡는다.
EVENTS = [
    ("SessionStart",     "idle"),
    ("UserPromptSubmit", "working"),
    ("PreToolUse",       "working"),
    ("PostToolUse",      "working"),
    ("PermissionRequest", "needs_input"),
    ("Stop",             "done"),
    ("SessionEnd",       "idle"),
]


def command_for(mode, state):
    if mode == "windows":
        # 배치 폴더의 .cmd 래퍼. 경로에 공백이 없어 따옴표 없이도 안전하다.
        return r"%s\yui-pet-status.cmd %s" % (os.environ["YUI_WIN_DIR"].rstrip("\\"), state)
    return 'bash "$HOME/.codex/yui-pet-status.sh" %s "" codex' % state


def is_ours(group):
    return any("yui-pet-status" in h.get("command", "")
               for h in group.get("hooks", []))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "add"
    home = os.environ["YUI_CODEX_HOME"]
    path = os.path.join(home, "hooks.json")

    doc = collections.OrderedDict()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f, object_pairs_hook=collections.OrderedDict)
        except ValueError:
            print("  경고: %s 를 읽지 못했습니다(형식 오류). 건너뜁니다." % path)
            return
        shutil.copyfile(path, path + ".bak-yui")

    hooks = doc.setdefault("hooks", collections.OrderedDict())
    for ev in list(hooks):                      # 우리 것만 먼저 걷어낸다
        if isinstance(hooks[ev], list):
            hooks[ev][:] = [g for g in hooks[ev] if not is_ours(g)]

    if action == "add":
        mode = os.environ.get("YUI_MODE", "wsl")
        for ev, state in EVENTS:
            group = collections.OrderedDict([
                ("hooks", [collections.OrderedDict([
                    ("type", "command"),
                    ("command", command_for(mode, state)),
                    ("timeout", 15),
                ])]),
            ])
            hooks.setdefault(ev, []).append(group)
        msg = "  %s: %d개 이벤트 등록 (%s)" % (path, len(EVENTS), mode)
    else:
        msg = "  %s: 훅 해제" % path

    # 빈 이벤트 목록은 지워 설정을 깔끔하게 유지. hooks 자체가 비면 파일도 지운다.
    doc["hooks"] = collections.OrderedDict((k, v) for k, v in hooks.items() if v)
    if not doc["hooks"]:
        del doc["hooks"]
    if not doc:
        if os.path.exists(path):
            os.remove(path)
        print(msg + "  (빈 hooks.json 제거)")
        return

    # Codex는 hooks.json에 모르는 최상위 키가 있으면 파일 전체를 무시한다.
    # (description 을 넣었다가 "unknown field `description`" 로 통째로 버려졌다.)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(msg + ("  (백업: hooks.json.bak-yui)" if os.path.exists(path + ".bak-yui") else ""))


if __name__ == "__main__":
    main()
