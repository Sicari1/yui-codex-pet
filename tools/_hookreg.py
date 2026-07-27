#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""~/.claude/settings.json 의 유이펫 훅을 등록/해제한다. install.sh가 부른다.

기존 설정과 다른 훅은 건드리지 않는다. 유이펫 훅(yui-pet-status가 들어간 명령)만
갈아끼우거나 뺀다. 바꾸기 전에 settings.json.bak-yui 로 백업한다.

  python3 _hookreg.py add      환경변수 YUI_SETTINGS, YUI_DIR 필요
  python3 _hookreg.py remove   환경변수 YUI_SETTINGS 필요
"""
import collections
import json
import os
import shutil
import sys

CMD = "bash $HOME/.claude/yui-pet-status.sh"


def entry(state, matcher=None):
    e = collections.OrderedDict()
    if matcher is not None:
        e["matcher"] = matcher
    e["hooks"] = [collections.OrderedDict(
        [("type", "command"), ("command", "%s %s" % (CMD, state))])]
    return e


WANTED = collections.OrderedDict([
    ("UserPromptSubmit", [entry("working")]),
    ("PreToolUse",       [entry("working", "*")]),
    ("PostToolUse",      [entry("working", "*")]),
    ("Notification",     [entry("needs_input", "permission_prompt"),
                          entry("needs_input", "elicitation_dialog")]),
    ("Stop",             [entry("done")]),
    ("StopFailure",      [entry("error")]),
    ("SessionStart",     [entry("idle")]),
    ("SessionEnd",       [entry("idle")]),
])


def is_ours(e):
    return any("yui-pet-status" in h.get("command", "") for h in e.get("hooks", []))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "add"
    path = os.environ["YUI_SETTINGS"]

    s = collections.OrderedDict()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            s = json.load(f, object_pairs_hook=collections.OrderedDict)
        shutil.copyfile(path, path + ".bak-yui")

    hooks = s.setdefault("hooks", collections.OrderedDict())
    for ev in list(hooks):                      # 우리 것만 먼저 걷어낸다
        hooks[ev][:] = [e for e in hooks[ev] if not is_ours(e)]

    if action == "add":
        for ev, lst in WANTED.items():
            hooks.setdefault(ev, []).extend(lst)
        s.setdefault("env", collections.OrderedDict())["YUI_PET_DIR"] = os.environ["YUI_DIR"]
        msg = "  8개 이벤트 등록 + YUI_PET_DIR 설정"
    else:
        (s.get("env") or {}).pop("YUI_PET_DIR", None)
        msg = "  훅 해제"

    # 빈 이벤트 목록은 지워 설정을 깔끔하게 유지
    s["hooks"] = collections.OrderedDict((k, v) for k, v in hooks.items() if v)
    if not s["hooks"]:
        del s["hooks"]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(msg + ("  (백업: settings.json.bak-yui)" if os.path.exists(path + ".bak-yui") else ""))


if __name__ == "__main__":
    main()
