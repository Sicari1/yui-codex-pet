#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
유이 펫 상태 기록 (공통 PetState).

  - 생명주기(phase)는 훅 인자로 결정.
  - detail은 tool_use를 안전한 한 문장으로 가공(raw thinking 미노출).
  - transcript_path(/home/... WSL)는 UNC(\\wsl.localhost\<distro>\...)로 변환해 기록
    → Windows에서 도는 오버레이가 그대로 읽을 수 있음.
  - 동시 훅 경쟁 방지: 고유 임시파일(mkstemp) 후 os.replace.

status.json: {source, session_id, phase, title, detail, transcript, ts(ns), expires_at?}
phase: idle | working | waiting | done | failed
"""
import json
import os
import sys
import time
import tempfile

state_arg = sys.argv[1] if len(sys.argv) > 1 else "idle"
base = sys.argv[2] if len(sys.argv) > 2 else \
    os.environ.get("YUI_PET_DIR") or os.path.join(os.path.expanduser("~"), ".yui-pet")

raw = sys.stdin.read()
try:
    d = json.loads(raw) if raw.strip() else {}
except Exception:
    d = {}

# 멀티세션: 세션별 파일에 기록 (sessions/claude/<session_id>.json)
sid = (d.get("session_id", "") or "default").replace("/", "_").replace("\\", "_")
sess_dir = os.path.join(base, "sessions", "claude")
try:
    os.makedirs(sess_dir, exist_ok=True)
except Exception:
    pass
out = os.path.join(sess_dir, sid + ".json")

prev = {}
try:
    with open(out, encoding="utf-8") as f:
        prev = json.load(f)
except Exception:
    pass

PHASE = {"working": "working", "needs_input": "waiting",
         "done": "done", "error": "failed", "idle": "idle"}
phase = PHASE.get(state_arg, state_arg)

_DISTRO = os.environ.get("WSL_DISTRO_NAME", "")


def to_unc(p):
    if p and p.startswith("/") and _DISTRO:
        return "\\\\wsl.localhost\\" + _DISTRO + p.replace("/", "\\")
    return p


TOOL_PHRASE = {
    "Read": "파일을 살펴보는 중", "Edit": "코드를 고치는 중", "Write": "파일을 작성하는 중",
    "Grep": "코드를 검색하는 중", "Glob": "파일을 찾는 중", "WebSearch": "자료를 검색하는 중",
    "WebFetch": "웹 페이지를 읽는 중", "Task": "하위 작업을 맡기는 중", "Agent": "하위 작업을 맡기는 중",
    "TodoWrite": "할 일을 정리하는 중", "NotebookEdit": "노트북을 손보는 중",
    "AskUserQuestion": "물어볼 걸 정리하는 중",
}


def clip(s, n):
    return (s or "").strip().replace("\n", " ")[:n]


def load_cfg():
    try:
        with open(os.path.join(base, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load_cfg()
PRIVACY = bool(CFG.get("privacyMode", True))
# 저장소 이름이 길거나 낯설면 config.json의 projectAliases로 보기 좋은 이름을 붙인다.
ALIASES = CFG.get("projectAliases") or {}

# 프로젝트로 치기 어려운 위치들(홈, 드라이브 루트 등) — 여기 있으면 폴더명을 제목으로 안 쓴다
_NOT_PROJECT = {os.path.realpath(os.path.expanduser("~")), "/", "/mnt", "/mnt/c",
                "/mnt/c/Users", "/home", "/tmp", "/root",
                os.path.dirname(base.rstrip("/\\"))}   # 배포 폴더의 상위 = 윈도우 사용자 폴더


def repo_root(path):
    """경로에서 위로 올라가며 .git이 있는 폴더를 찾는다. 파일시스템 조회만 한다."""
    try:
        p = os.path.realpath(path)
    except Exception:
        return ""
    if not os.path.isdir(p):
        p = os.path.dirname(p)
    for _ in range(24):
        if os.path.exists(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return ""


def project_name(cwd, file_hint=""):
    """저장소 이름 > 작업 폴더 이름 > 만지던 파일이 속한 저장소 이름. 없으면 빈 문자열."""
    cwd = (cwd or os.getcwd()).rstrip("/\\")
    root = repo_root(cwd)
    if root:
        name = os.path.basename(root)
        return ALIASES.get(name, name)
    try:
        real = os.path.realpath(cwd)
    except Exception:
        real = cwd
    if real not in _NOT_PROJECT:                # 홈 같은 자리가 아니면 폴더명이 곧 프로젝트
        name = os.path.basename(cwd)
        if name:
            return ALIASES.get(name, name)
    if file_hint:                               # 홈에서 돌리는 중이면 만지던 파일로 되짚는다
        root = repo_root(str(file_hint))
        if root:
            name = os.path.basename(root)
            return ALIASES.get(name, name)
    return ""


ev = d.get("hook_event_name", "")
# 제목: privacyMode면 '프로젝트명', 아니면 세션 첫 프롬프트를 한 번 정해 유지
title = prev.get("title", "")
detail = ""
_GENERIC = {"", "작업", "작업 중", "확인 필요"}
_CWD = d.get("cwd") or os.getcwd()
_FILE_HINT = (d.get("tool_input") or {}).get("file_path") or ""
PROJECT = project_name(_CWD, _FILE_HINT)

if ev == "UserPromptSubmit":
    if PRIVACY:
        title = PROJECT or title            # 못 알아내면 이전 제목을 그대로 둔다
    else:
        prompt = d.get("prompt", "") or ""
        if title in _GENERIC and len(prompt.strip()) > 4:   # 짧은 인사(hi 등)는 제목으로 안 씀
            title = clip(prompt, 28)
    detail = "요청을 살펴보는 중"
elif ev == "PreToolUse":
    tool = d.get("tool_name", "")
    ti = d.get("tool_input", {}) or {}
    if PRIVACY and PROJECT:     # 폴더를 옮겨 다니면 제목도 따라간다
        title = PROJECT
    if tool == "Bash":
        # description은 원문(주로 영어)이라 privacyMode에선 성격만 표시
        detail = "명령을 실행하는 중" if PRIVACY else \
            (clip(ti.get("description", ""), 44) or "명령을 실행하는 중")
    else:
        # 변수명 주의: 모듈 상단 base(배포 폴더)를 가리지 않도록 phrase로 둔다
        phrase = TOOL_PHRASE.get(tool, "작업하는 중")
        fp = ti.get("file_path")
        detail = f"{os.path.basename(str(fp))} · {phrase}" if (fp and tool in ("Read", "Edit", "Write")) else phrase
elif ev == "PostToolUse":
    # 도구 실행이 끝나면 working을 유지해 waiting(권한 대기)을 해제
    detail = prev.get("detail", "") or "다음 단계를 준비하는 중"
elif ev == "Notification":
    # 알림 원문에도 프롬프트/응답 조각이 섞일 수 있어 privacyMode에선 고정 문구
    detail = "확인을 기다리고 있어요" if PRIVACY else \
        (clip(d.get("message", ""), 50) or "확인을 기다리고 있어요")
elif ev == "Stop":
    detail = "작업을 마쳤어요"
elif ev in ("SessionStart", "SessionEnd"):
    title, detail = "", ""

if phase != "idle" and not title:
    title = PROJECT if PRIVACY else "작업 중"
if phase == "failed" and not detail:
    detail = "문제가 생겼어요"
if phase == "idle":
    title, detail = "", ""

now = time.time_ns()
tp = d.get("transcript_path", "")
# 작업이 시작된 시각. working이 이어지는 동안 유지해 오버레이가 경과 시간을 셀 수 있게 한다.
started = prev.get("started_at") or 0
if phase == "working":
    if prev.get("phase") != "working" or not started:
        started = now
else:
    started = 0
data = {
    "source": "claude",
    "session_id": d.get("session_id", "") or prev.get("session_id", ""),
    "phase": phase,
    "title": title,
    "detail": detail,
    "transcript": to_unc(tp) if tp else prev.get("transcript", ""),
    "ts": now,
    "started_at": started,
}
if phase == "done":
    data["expires_at"] = now + 4_000_000_000
elif phase == "failed":
    data["expires_at"] = now + 8_000_000_000

# 고유 임시파일 → 원자적 교체 (동시 훅 경쟁 방지)
try:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, out)
except Exception as e:
    try:
        with open(os.path.join(os.path.dirname(out), "yui-hook-error.log"), "a", encoding="utf-8") as lf:
            lf.write(f"{now} {ev} {e}\n")
        os.unlink(tmp)
    except Exception:
        pass
