# -*- coding: utf-8 -*-
"""
유이 데스크톱 펫 — Codex v2 규격 재현 + 클로드 코드 상태/작업 표시 오버레이.

상태 소스(status.json = 공통 PetState) ──▶ 이 오버레이(렌더러)
  PetState: {source, session_id, phase, title, detail, transcript, ts(ns), expires_at?}
  phase: idle | working | waiting | done | failed
  - 생명주기(phase)·제목·기본 detail은 클로드 훅이 기록.
  - 진행 문장은 transcript의 '공개 assistant 텍스트'로 보충(raw thinking 미노출).
"""
import os
import sys
import json
import math
import time
import random
import html
import logging
import ctypes
from ctypes import wintypes

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6 import QtNetwork
from PySide6.QtNetwork import QLocalServer, QLocalSocket

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = APP_DIR if os.path.exists(os.path.join(APP_DIR, "spritesheet.webp")) \
    else os.path.join(os.path.expanduser("~"), ".yui-pet")
SESSIONS_DIR = os.path.join(BASE, "sessions")   # sessions/<source>/<session_id>.json
FONT_DIR = os.path.join(BASE, "fonts")          # 번들 폰트(Pretendard 등)
# 고해상 시트가 있으면 우선 사용 → 확대해도 선명. 없으면 원본 PNG/WebP.
# 주의: 파일명에 '@4x' 같은 접미사를 쓰면 Qt가 고밀도 에셋으로 보고 devicePixelRatio를
#       자동으로 올려 버려 그림이 1/N 크기로 그려진다. 반드시 '-4x' 형태로 둘 것.
SPRITE_PATH = next(
    (p for p in (os.path.join(BASE, n) for n in
                 ("spritesheet-4x.png", "spritesheet-3x.png", "spritesheet-2x.png",
                  "spritesheet.png", "spritesheet.webp"))
     if os.path.exists(p)),
    os.path.join(BASE, "spritesheet.png"))
CONFIG_PATH = os.path.join(BASE, "config.json")

# 표시 좌표는 항상 192x208 기준(LOGICAL). 실제 시트 셀 크기는 로드 후 결정.
LOGICAL_W, LOGICAL_H = 192, 208
SHEET_COLS, SHEET_ROWS = 8, 11
CELL_W, CELL_H = LOGICAL_W, LOGICAL_H
R_IDLE, R_RUN_R, R_RUN_L, R_WAVE, R_JUMP = 0, 1, 2, 3, 4
R_FAILED, R_WAITING, R_RUNNING, R_REVIEW = 5, 6, 7, 8
R_LOOK_A, R_LOOK_B = 9, 10

ROW_DEF = {
    "idle":          (R_IDLE,    [280, 110, 110, 140, 140, 320]),
    "running-right": (R_RUN_R,   [120, 120, 120, 120, 120, 120, 120, 220]),
    "running-left":  (R_RUN_L,   [120, 120, 120, 120, 120, 120, 120, 220]),
    "waving":        (R_WAVE,    [140, 140, 140, 280]),
    "jumping":       (R_JUMP,    [140, 140, 140, 140, 280]),
    "failed":        (R_FAILED,  [140, 140, 140, 140, 140, 140, 140, 240]),
    "waiting":       (R_WAITING, [150, 150, 150, 150, 150, 260]),
    "running":       (R_RUNNING, [120, 120, 120, 120, 120, 220]),
    "review":        (R_REVIEW,  [150, 150, 150, 150, 150, 280]),
}
PHASE_ANIM = {"working": "running", "waiting": "waiting", "failed": "failed",
              "done": "review", "idle": "idle"}
# 여러 세션 동시 표시 우선순위: 입력대기 > 실패 > 작업중 > 완료 > idle
PRIORITY = {"waiting": 4, "failed": 3, "working": 2, "done": 1, "idle": 0}
STALE_NS = 1800 * 1_000_000_000   # 30분 지난 세션은 무시
# 원본 up-left 프레임(292.5·315·337.5°)이 방향이 어긋나 정면/우측을 봄 → 자연스러운 인접으로 스냅
LOOK_REMAP = {13: 12, 14: 12, 15: 0}   # 12=270 left, 0=000 up

POLL_MS, TRACK_MS, TAIL_MS = 300, 70, 600
DRAG_RUN_THRESHOLD, CLICK_MOVE_TOL = 2, 5
MIN_SCALE = 0.35            # 최소 73px — 아주 작게
FALLBACK_MAX_SCALE = 2.0    # 고해상 시트가 없을 때의 확대 상한
MASK_MAX_H = 256            # 히트박스 마스크를 만들 때 쓰는 축소본 높이

# ---- 자율 행동(idle일 때 스스로 돌아다니기) ----
WANDER_TICK_MS = 33               # 이동 갱신 주기(≈30fps)
WANDER_SPEED = 55                 # 208px 기준 초당 이동 px. 크기에 비례해 늘어난다
BLINK_REST_MIN_MS, BLINK_REST_MAX_MS = 2000, 5500   # 깜빡임 사이 간격(고정이면 기계 같다)

# 사용자가 키보드·마우스를 만지고 있으면 방해되지 않게 훨씬 얌전히 군다.
# 자리를 비우거나 손을 멈추면 그때 편하게 돌아다닌다.
USER_ACTIVE_S = 25                # 이 시간 안에 입력이 있었으면 '사용 중'으로 본다
#            쉬는 시간(ms)   한 번에 갈 거리(px, 208 기준)  다음 행동 가중치
CALM = dict(rest=(40000, 110000), dist=(60, 170),
            actions=(("walk", 26), ("jump", 3), ("wave", 5), ("talk", 6), ("stay", 60)))
FREE = dict(rest=(9000, 30000), dist=(90, 340),
            actions=(("walk", 52), ("jump", 9), ("wave", 11), ("talk", 10), ("stay", 18)))

FULLSCREEN_CHECK_MS = 1500        # 전체화면 앱(게임·영상) 감지 주기
PANEL_GRACE_S = 2.5               # 목록을 막 열었을 때 커서가 벗어나도 유지하는 시간
POMO_TICK_MS = 1000               # 뽀모도로 남은 시간 갱신 주기

# 연속 클릭 반응: 이 시간 안에 이만큼 누르면 좋아한다
CLICK_COMBO_N, CLICK_COMBO_MS = 3, 1400
# 커서가 이만큼(펫 높이 대비) 가까이 오면 놀란다. 너무 자주 반응하면 성가시니 쿨다운을 둔다
PROXIMITY_RATIO, PROXIMITY_COOLDOWN_S = 0.30, 25
# 던지기 물리. MIN_SPEED가 낮으면 그냥 옮기려던 것도 날아가 버린다.
# 확 뿌리는 동작에서만 걸리도록 높게 잡고, 놓기 직전까지 움직이고 있어야 한다.
THROW_GRAVITY, THROW_BOUNCE, THROW_MIN_SPEED = 2600, 0.45, 1400
THROW_MAX_IDLE_S = 0.08          # 놓기 전 이만큼 멈춰 있었으면 던지지 않는다
WEATHER_REFRESH_MS = 60 * 60 * 1000      # 날씨는 한 시간에 한 번이면 충분

ICON_DIR = os.path.join(BASE, "icons")
# 말풍선 왼쪽에 붙는 출처 배지. 아이콘 파일이 없으면 글자만 나온다.
SOURCE_BADGE = {"claude": ("Claude", "claude.png"), "cli": ("CLI", "")}

SAY_MS = 4500                     # 대사 말풍선 표시 시간
SAY_MS_BUSY = 2200                # 작업 표시를 가리는 동안은 짧게
BORED_AFTER_S = 600               # 이만큼 입력이 없으면 심심해한다
# lines.json이 없을 때만 쓰는 최소 기본값. 실제 대사는 lines.json에 있다.
DEFAULT_LINES = {
    "morning":   [{"ko": "좋은 아침~ 오늘도 잘 부탁해!", "ja": "おはよ～ 今日もよろしくね！"}],
    "afternoon": [{"ko": "배고파~ 케이크 없어?", "ja": "お腹すいた～ ケーキない？"}],
    "evening":   [{"ko": "차 마실 시간이야~", "ja": "お茶の時間だよ～"}],
    "night":     [{"ko": "슬슬 잘 시간 아니야?", "ja": "そろそろ寝る時間じゃない？"}],
    "lateNight": [{"ko": "아직도 안 자?", "ja": "まだ寝ないの？"}],
    "bored":     [{"ko": "심심하다~", "ja": "ひまだな～"}],
    "idleChat":  [{"ko": "기타 치고 싶다~", "ja": "ギター弾きたいな～"}],
    "quotes":    [{"ko": "경음부, 정말 좋아~", "ja": "軽音、大好き～"}],
    "special":   {},
}
DEFAULTS = {"petHeight": 208, "bubbleWidth": 400, "bubbleMaxLines": 3,
            "completedDisplaySeconds": 3, "privacyMode": True, "wander": True,
            "showJapanese": True, "pomodoroFocusMin": 25, "pomodoroBreakMin": 5,
            "clickAction": "panel", "clickThrough": False, "opacity": 1.0, "pet": "",
            "weatherEnabled": False, "weatherLat": 35.2281, "weatherLon": 128.6811,
            "throwEnabled": True}


SHEET_NAMES = ("spritesheet-4x.png", "spritesheet-3x.png", "spritesheet-2x.png",
               "spritesheet.png", "spritesheet.webp")


def pet_sheet_path(pet_id):
    """펫 id에 해당하는 스프라이트 경로. 빈 문자열이면 기본(루트) 시트."""
    root = BASE if not pet_id else os.path.join(BASE, "pets", pet_id)
    for n in SHEET_NAMES:
        p = os.path.join(root, n)
        if os.path.exists(p):
            return p
    return SPRITE_PATH


# 폴더 id를 사람이 읽을 이름으로. 없으면 id를 그대로 쓴다.
PET_LABELS = {"chibi-yui": "치비"}


def pet_list():
    """[(id, 표시이름)] — 기본 펫 + BASE/pets/*/ 에 있는 것들.

    pet.json의 displayName이 서로 같을 수 있어(둘 다 "유이") 폴더 이름을 괄호로 붙인다.
    """
    out = [("", "유이 (기본)")]
    try:
        for d in sorted(os.listdir(os.path.join(BASE, "pets"))):
            pj = os.path.join(BASE, "pets", d, "pet.json")
            name = d
            try:
                with open(pj, encoding="utf-8") as f:
                    name = json.load(f).get("displayName") or d
            except Exception:
                pass
            if any(os.path.exists(os.path.join(BASE, "pets", d, n)) for n in SHEET_NAMES):
                out.append((d, "%s (%s)" % (name, PET_LABELS.get(d, d))))
    except OSError:
        pass
    return out


def load_lines():
    """대사 목록. lines.json이 있으면 그걸 쓰고, 없으면 기본 대사를 파일로 만들어 둔다."""
    path = os.path.join(BASE, "lines.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_LINES, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return DEFAULT_LINES


def time_bucket():
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    if h >= 21 or h < 2:
        return "night"
    return "lateNight"


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    return cfg


EDITOR_HINTS = ("Visual Studio Code", "Cursor", "Windows Terminal", "WindowsTerminal")


def find_windows(match=None):
    """제목에 match가 들어간 보이는 창들. match가 없으면 편집기/터미널 창."""
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value
                if (match and match in t) or (not match and any(h in t for h in EDITOR_HINTS)):
                    found.append(hwnd)
        return True

    user32.EnumWindows(proc(cb), 0)
    return found


def toggle_window(match=None):
    """맞는 창을 토글한다. 최소화돼 있으면 복원+포커스, 떠 있으면 최소화.

    세션마다 창이 따로 있는 게 아니라(터미널 여러 개가 편집기 창 하나를 쓴다)
    제목이 맞는 창을 먼저 찾고, 없으면 편집기 창으로 떨어진다.
    """
    user32 = ctypes.windll.user32
    found = (find_windows(match) if match else []) or find_windows()
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    else:
        user32.ShowWindow(hwnd, 6)
    return True


def activate_vscode():
    toggle_window()


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def user_idle_seconds():
    """마지막 키보드·마우스 입력 이후 흐른 시간. 사용 중인지 판단하는 데 쓴다."""
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    # dwTime과 GetTickCount는 같은 32비트 기준이라 그대로 빼면 된다
    return max(0.0, (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0)


# 바탕화면·작업표시줄은 '전체화면 앱'이 아니다
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"}


def fullscreen_app_active():
    """게임·영상처럼 화면을 통째로 덮는 창이 앞에 있는지. 그럴 땐 펫을 숨긴다."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, buf, 64)
    if buf.value in _SHELL_CLASSES:
        return False
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    for s in QtGui.QGuiApplication.screens():
        g = s.geometry()
        if (r.left <= g.left() and r.top <= g.top()
                and r.right >= g.right() + 1 and r.bottom >= g.bottom() + 1):
            return True
    return False


def startup_bat_path():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "유이펫.bat") if appdata else ""


def autostart_enabled():
    p = startup_bat_path()
    return bool(p) and os.path.exists(p)


def set_autostart(on):
    """시작프로그램 폴더에 실행용 배치파일을 넣거나 지운다(레지스트리는 건드리지 않는다)."""
    p = startup_bat_path()
    if not p:
        return False
    try:
        if on:
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pyw):
                pyw = sys.executable
            script = os.path.join(APP_DIR, "yui_pet.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write('@echo off\r\nstart "" "%s" "%s"\r\n' % (pyw, script))
        elif os.path.exists(p):
            os.remove(p)
        return True
    except Exception:
        logging.exception("autostart toggle failed")
        return False


def load_bundled_fonts():
    """fonts/ 폴더의 번들 폰트를 앱에 등록(시스템 설치 불필요)."""
    try:
        for fn in os.listdir(FONT_DIR):
            if fn.lower().endswith((".ttf", ".otf")):
                QtGui.QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, fn))
    except OSError:
        pass


def cut(sheet, row, col):
    return sheet.copy(col * CELL_W, row * CELL_H, CELL_W, CELL_H)


def summarize(text, limit=64):
    """공개 assistant 텍스트를 말풍선용 짧은 한 문장으로. 마크다운/공백 정리."""
    t = " ".join((text or "").split())
    for mark in ("```", "#", "*", "`"):
        t = t.replace(mark, "")
    t = t.strip()
    # 첫 문장 경계(., !, ?, 다., 요.)에서 자르기
    for i, ch in enumerate(t[:limit]):
        if ch in ".!?" and i > 10:
            return t[:i + 1]
    return t[:limit] + ("…" if len(t) > limit else "")


def elapsed_text(started_ns, short=False):
    """작업 시작 이후 경과. 말풍선은 1분이 넘어야 표시하고, 목록 패널은 초부터 보여준다."""
    if not started_ns:
        return ""
    sec = int((time.time_ns() - started_ns) / 1_000_000_000)
    if sec < 0:
        return ""
    if sec < 60:
        return "" if not short else "%d초" % sec
    m, h = sec // 60, sec // 3600
    if h:
        return "%d시간 %d분%s" % (h, m - h * 60, "" if short else "째")
    return "%d분%s" % (m, "" if short else "째")


class YuiBubble(QtWidgets.QWidget):
    PAD, TAIL, RADIUS, ICON = 15, 9, 19, 22
    BADGE_ICON, MORE_W = 13, 44

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.tail_down = True
        self.phase = "working"
        self.badge_text = ""
        self.badge_icon = None
        self.more = 0
        self.spin = 0.0
        self.started = 0
        self._last_state = ("idle", "", "")
        self._elapsed = ""
        self.label = QtWidgets.QLabel(self)
        self.label.setWordWrap(True)
        self.label.setTextFormat(QtCore.Qt.RichText)
        self.label.setStyleSheet(
            "QLabel{background:transparent;font-family:'Pretendard Variable','Pretendard','Noto Sans KR','맑은 고딕','Malgun Gothic';line-height:150%;}")
        self.spin_timer = QtCore.QTimer(self)
        self.spin_timer.timeout.connect(self._spin_tick)
        self.clock_timer = QtCore.QTimer(self)      # 경과 표시(분 단위)만 따로 갱신
        self.clock_timer.timeout.connect(self._clock_tick)

    def _spin_tick(self):
        self.spin = (self.spin + 32) % 360
        self.update()

    def _clock_tick(self):
        """'3분째' 문구가 바뀔 때만 다시 배치한다 — 매초 흔들리지 않게."""
        if elapsed_text(self.started if self.phase == "working" else 0) != self._elapsed:
            self.set_state(*self._last_state)

    def set_more(self, n):
        """동시에 도는 작업 수. 2개 이상이면 펼칠 수 있다는 표시를 단다."""
        self.more = n

    def set_started(self, ts):
        """작업 시작 시각(ns). 오래 걸리는 작업만 경과 시간을 곁들인다."""
        self.started = ts or 0

    def elapsed_width(self):
        if not self._elapsed:
            return 0
        return QtGui.QFontMetrics(self.small_font()).horizontalAdvance(self._elapsed) + 10

    def small_font(self):
        f = QtGui.QFont(self.label.font())
        f.setPixelSize(12)
        return f

    def set_badge(self, source):
        """어느 도구가 낸 상태인지 말풍선 왼쪽에 표시한다."""
        label, icon = SOURCE_BADGE.get(source or "", ("", ""))
        self.badge_text = label
        self.badge_icon = None
        if icon:
            pm = QtGui.QPixmap(os.path.join(ICON_DIR, icon))
            if not pm.isNull():
                self.badge_icon = pm.scaled(self.BADGE_ICON, self.BADGE_ICON,
                                            QtCore.Qt.KeepAspectRatio,
                                            QtCore.Qt.SmoothTransformation)

    def _badge_width(self):
        if not self.badge_text:
            return 0
        fm = QtGui.QFontMetrics(self.badge_font())
        w = fm.horizontalAdvance(self.badge_text) + 13
        if self.badge_icon:
            w += self.BADGE_ICON + 4
        return w + 8

    def badge_font(self):
        f = QtGui.QFont(self.label.font())
        f.setPixelSize(11)
        f.setWeight(QtGui.QFont.DemiBold)
        return f

    def set_state(self, phase, title, detail):
        self.phase = phase
        self._last_state = (phase, title, detail)
        self._elapsed = elapsed_text(self.started if phase == "working" else 0)
        # bubbleMaxLines 근사 말줄임(마지막에 …)
        maxchars = self.cfg["bubbleMaxLines"] * 28
        budget = maxchars - len(title or "") - 3
        if detail and budget > 4 and len(detail) > budget:
            detail = detail[:budget].rstrip() + "…"
        t = html.escape(title or "")
        dd = html.escape(detail or "")
        head = f"<span style='color:#2c2c33;font-weight:600;font-size:13px;letter-spacing:-0.2px;'>{t}</span>" if t else ""
        sep = "<span style='color:#cacad1;'>&nbsp;&nbsp;·&nbsp;&nbsp;</span>" if (t and dd) else ""
        body = f"<span style='color:#7c7c85;font-size:12px;letter-spacing:-0.1px;'>{dd}</span>" if dd else ""
        self.label.setText(head + sep + body)
        # 내용 길이에 맞춰 폭 결정(짧으면 좁게, 길면 최대폭에서 줄바꿈)
        icon = 0 if phase == "say" else self.ICON   # 대사엔 상태 아이콘이 없다
        badge = self._badge_width()
        more = self.MORE_W if self.more > 1 else 0
        el = self.elapsed_width() if phase != "say" else 0
        maxw = self.cfg["bubbleWidth"] - icon - badge - more - el - 6
        fm = self.label.fontMetrics()
        plain = (title or "") + ("  ·  " if (title and detail) else "") + (detail or "")
        natural = fm.horizontalAdvance(plain) + 10
        self.label.setFixedWidth(max(90, min(natural, maxw)))
        # bubbleMaxLines 적용: 최대 높이 제한(초과분은 잘림)
        fm = self.label.fontMetrics()
        max_h = fm.lineSpacing() * self.cfg["bubbleMaxLines"] + 6
        self.label.setMaximumHeight(max_h)
        self.label.adjustSize()
        w = self.label.width() + icon + badge + more + el + 6 + self.PAD * 2
        h = self.label.height() + self.PAD * 2 + self.TAIL
        self.setFixedSize(int(w), int(h))
        self._place()
        if phase == "working" and not self.spin_timer.isActive():
            self.spin_timer.start(70)
        elif phase != "working" and self.spin_timer.isActive():
            self.spin_timer.stop()
        if phase == "working" and self.started and not self.clock_timer.isActive():
            self.clock_timer.start(1000)
        elif phase != "working" and self.clock_timer.isActive():
            self.clock_timer.stop()
        self.update()

    def set_tail(self, down):
        if down != self.tail_down:
            self.tail_down = down
            self._place()
            self.update()

    def _place(self):
        self.label.move(self.PAD + self._badge_width(),
                        self.PAD if self.tail_down else self.PAD + self.TAIL)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top = 0 if self.tail_down else self.TAIL
        card = QtCore.QRectF(1, top + 1, w - 2, h - self.TAIL - 2)
        p.setPen(QtCore.Qt.NoPen)
        for dy, a in ((1, 16), (2, 12), (4, 8)):   # 부드러운 다중 그림자
            p.setBrush(QtGui.QColor(0, 0, 0, a))
            p.drawRoundedRect(card.adjusted(0, dy, 0, dy), self.RADIUS, self.RADIUS)
        path = QtGui.QPainterPath()
        path.addRoundedRect(card, self.RADIUS, self.RADIUS)
        cx = w / 2
        tail = QtGui.QPainterPath()
        if self.tail_down:
            tail.moveTo(cx - 8, card.bottom() - 1); tail.lineTo(cx, card.bottom() + self.TAIL - 1); tail.lineTo(cx + 8, card.bottom() - 1)
        else:
            tail.moveTo(cx - 8, card.top() + 1); tail.lineTo(cx, card.top() - self.TAIL + 1); tail.lineTo(cx + 8, card.top() + 1)
        tail.closeSubpath()
        path = path.united(tail)
        waiting = self.phase == "waiting"
        p.setBrush(QtGui.QColor(246, 246, 249, 244))
        p.setPen(QtGui.QPen(QtGui.QColor(230, 150, 60, 200) if waiting else QtGui.QColor(0, 0, 0, 22),
                            1.4 if waiting else 1))
        p.drawPath(path)
        # 출처 배지 (Claude 로고 + 이름)
        if self.badge_text:
            bw = self._badge_width()
            by = card.top() + (card.height() - 18) / 2
            br = QtCore.QRectF(card.left() + 8, by, bw - 8, 18)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 12))
            p.drawRoundedRect(br, 9, 9)
            x = br.left() + 5
            if self.badge_icon:
                p.drawPixmap(int(x), int(br.center().y() - self.BADGE_ICON / 2), self.badge_icon)
                x += self.BADGE_ICON + 4
            p.setFont(self.badge_font())
            p.setPen(QtGui.QColor(120, 120, 132))
            p.drawText(QtCore.QRectF(x, br.top(), br.right() - x, br.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.badge_text)

        # 오른쪽 끝에서부터 [상태 인디케이터] [경과 시간] [☰ n] 순으로 자리를 잡는다
        r = self.ICON
        ix = card.right() - r - 6
        iy = card.top() + max(6.0, (min(card.height(), 46.0) - r) / 2)
        right = ix - 6

        if self._elapsed:
            ew = self.elapsed_width()
            p.setFont(self.small_font()); p.setPen(QtGui.QColor(150, 150, 162))
            p.drawText(QtCore.QRectF(right - ew, card.top(), ew, card.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, self._elapsed)
            right -= ew

        # 작업이 여러 개면 '올리면 펼쳐진다'는 힌트
        if self.more > 1:
            f = QtGui.QFont(self.label.font()); f.setPixelSize(13)
            f.setWeight(QtGui.QFont.DemiBold)
            p.setFont(f); p.setPen(QtGui.QColor(140, 140, 152))
            p.drawText(QtCore.QRectF(right - self.MORE_W, card.top(), self.MORE_W, card.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight,
                       "☰ %d" % self.more)

        # 상태 인디케이터
        cxr, cyr = ix + r / 2, iy + r / 2
        k = r / 18.0                       # 기본 18px 기준으로 그리던 도형을 함께 키운다
        if self.phase == "working":
            pen = QtGui.QPen(QtGui.QColor(120, 120, 130), 2.2 * k); pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen); p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(QtCore.QRectF(ix, iy, r, r), int(-self.spin * 16), int(270 * 16))
        elif self.phase == "done":
            p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(52, 180, 90))
            p.drawEllipse(QtCore.QRectF(ix, iy, r, r))
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2.0 * k); pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawPolyline([QtCore.QPointF(cxr - 4 * k, cyr), QtCore.QPointF(cxr - 1 * k, cyr + 3 * k),
                            QtCore.QPointF(cxr + 4 * k, cyr - 3 * k)])
        elif self.phase in ("waiting", "failed"):
            col = QtGui.QColor(240, 150, 40) if self.phase == "waiting" else QtGui.QColor(220, 70, 60)
            p.setPen(QtCore.Qt.NoPen); p.setBrush(col)
            p.drawEllipse(QtCore.QRectF(ix + 3 * k, iy + 3 * k, r - 6 * k, r - 6 * k))
        p.end()


MENU_QSS = """
QMenu{background:#fbfbfd;border:1px solid #e4e4ea;border-radius:12px;padding:6px;
      font-family:'Pretendard Variable','Pretendard','Noto Sans KR','맑은 고딕';font-size:12px;color:#2c2c33;}
QMenu::item{padding:7px 16px;border-radius:8px;}
QMenu::item:selected{background:#eceaff;color:#3a2fa8;}
QMenu::separator{height:1px;background:#ececf1;margin:5px 8px;}
QSlider::groove:horizontal{height:4px;background:#e6e6ec;border-radius:2px;}
QSlider::sub-page:horizontal{height:4px;background:#8b7cf6;border-radius:2px;}
QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;border-radius:7px;
                           background:#ffffff;border:1.5px solid #8b7cf6;}
QSlider::handle:horizontal:hover{background:#f4f2ff;}
"""


class SliderAction(QtWidgets.QWidgetAction):
    """메뉴 안에 들어가는 조절 바. 끌면 실시간 반영, 놓으면 config에 저장.

    kind="size"는 표시 높이를, kind="opacity"는 불투명도를 조절한다.
    """

    def __init__(self, parent, pet, kind="size"):
        super().__init__(parent)
        self.pet = pet
        self.kind = kind
        box = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(box)
        lay.setContentsMargins(16, 4, 16, 8)
        lay.setSpacing(10)

        cap = QtWidgets.QLabel("크기" if kind == "size" else "투명도")
        cap.setStyleSheet("color:#7c7c85;font-size:11px;background:transparent;")
        self.val = QtWidgets.QLabel()
        self.val.setStyleSheet("color:#2c2c33;font-size:11px;font-weight:600;background:transparent;")
        self.val.setFixedWidth(42)
        self.val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setFixedWidth(170)
        if kind == "size":
            self.slider.setMinimum(int(MIN_SCALE * 100))
            self.slider.setMaximum(int(pet.max_scale * 100))
            self.slider.setValue(int(round(pet.scale * 100)))
            self.slider.sliderReleased.connect(lambda: self.pet._save_size())
        else:
            self.slider.setMinimum(20)
            self.slider.setMaximum(100)
            self.slider.setValue(int(round(float(pet.cfg.get("opacity", 1.0)) * 100)))
            self.slider.sliderReleased.connect(
                lambda: self.pet._save_cfg({"opacity": self.slider.value() / 100.0}))
        self.slider.setPageStep(10)
        self.slider.valueChanged.connect(self._changed)

        lay.addWidget(cap)
        lay.addWidget(self.slider)
        lay.addWidget(self.val)
        self._sync_label(self.slider.value())
        self.setDefaultWidget(box)

    def _sync_label(self, v):
        self.val.setText(f"{int(round(LOGICAL_H * v / 100))}px" if self.kind == "size"
                         else f"{v}%")

    def _changed(self, v):
        self._sync_label(v)
        if self.kind == "size":
            self.pet.set_scale(v / 100.0)
        else:
            self.pet.cfg["opacity"] = v / 100.0
            self.pet._apply_opacity()


PHASE_DOT = {"working": (120, 120, 132), "waiting": (240, 150, 40),
             "failed": (220, 70, 60), "done": (52, 180, 90)}
PHASE_WORD = {"working": "작업 중", "waiting": "입력 대기", "failed": "실패", "done": "완료"}


class SessionPanel(QtWidgets.QWidget):
    """도는 작업들을 한눈에. 줄을 누르면 그 작업의 창을 띄우거나 내린다."""
    ROW_H, PAD, W = 40, 8, 430

    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self.rows = []
        self.hover = -1
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.icon = QtGui.QPixmap(os.path.join(ICON_DIR, "claude.png"))
        if not self.icon.isNull():
            self.icon = self.icon.scaled(14, 14, QtCore.Qt.KeepAspectRatio,
                                         QtCore.Qt.SmoothTransformation)

    def refresh(self, rows):
        self.rows = rows[:8]                    # 너무 길어지면 잘라 보여준다
        h = self.PAD * 2 + max(1, len(self.rows)) * self.ROW_H + 22
        self.setFixedSize(self.W, h)
        self.update()

    def place_over(self, anchor):
        scr = QtGui.QGuiApplication.screenAt(anchor.center())
        g = (scr or QtGui.QGuiApplication.primaryScreen()).availableGeometry()
        x = max(g.left() + 4, min(anchor.center().x() - self.width() // 2,
                                  g.right() - self.width() - 4))
        y = anchor.top() - self.height() - 6
        if y < g.top():
            y = anchor.bottom() + 6
        self.move(int(x), int(y))

    def _row_at(self, pos):
        i = (pos.y() - self.PAD - 18) // self.ROW_H
        return int(i) if 0 <= i < len(self.rows) else -1

    def mouseMoveEvent(self, e):
        i = self._row_at(e.position().toPoint())
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._row_at(e.position().toPoint())
        if i >= 0:
            title = self.rows[i].get("title") or ""
            toggle_window(title.split("  ·")[0].strip() or None)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        card = QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(QtCore.Qt.NoPen)
        for dy, a in ((1, 16), (2, 12), (4, 8)):
            p.setBrush(QtGui.QColor(0, 0, 0, a))
            p.drawRoundedRect(card.adjusted(0, dy, 0, dy), 14, 14)
        p.setBrush(QtGui.QColor(246, 246, 249, 248))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 22), 1))
        p.drawRoundedRect(card, 14, 14)

        f = QtGui.QFont(self.font()); f.setPixelSize(11)
        p.setFont(f); p.setPen(QtGui.QColor(150, 150, 160))
        p.drawText(QtCore.QRectF(14, 6, self.width() - 28, 16),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   "작업 %d개  ·  줄을 누르면 창 열기/내리기" % len(self.rows))

        if not self.rows:
            p.setPen(QtGui.QColor(150, 150, 160))
            p.drawText(card, QtCore.Qt.AlignCenter, "도는 작업이 없어요")
            p.end(); return

        y = self.PAD + 18
        for i, r in enumerate(self.rows):
            rect = QtCore.QRectF(6, y, self.width() - 12, self.ROW_H - 2)
            if i == self.hover:
                p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(236, 234, 255))
                p.drawRoundedRect(rect, 8, 8)
            x = rect.left() + 10
            if r["source"] == "claude" and not self.icon.isNull():
                p.drawPixmap(int(x), int(rect.center().y() - 7), self.icon)
                x += 20
            else:
                f2 = QtGui.QFont(self.font()); f2.setPixelSize(9)
                p.setFont(f2); p.setPen(QtGui.QColor(150, 150, 160))
                p.drawText(QtCore.QRectF(x, rect.top(), 22, rect.height()),
                           QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                           (r["source"] or "?")[:3].upper())
                x += 24
            f3 = QtGui.QFont(self.font()); f3.setPixelSize(12); f3.setWeight(QtGui.QFont.DemiBold)
            p.setFont(f3); p.setPen(QtGui.QColor(44, 44, 51))
            tw = 130
            p.drawText(QtCore.QRectF(x, rect.top(), tw, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                       QtGui.QFontMetrics(f3).elidedText(r["title"], QtCore.Qt.ElideRight, int(tw)))
            f4 = QtGui.QFont(self.font()); f4.setPixelSize(11)
            el = elapsed_text(r.get("started", 0) if r["phase"] == "working" else 0, short=True)
            ew = QtGui.QFontMetrics(f4).horizontalAdvance(el) + 8 if el else 0
            p.setFont(f4); p.setPen(QtGui.QColor(124, 124, 133))
            dx = x + tw + 6
            dw = rect.right() - dx - 60 - ew
            p.drawText(QtCore.QRectF(dx, rect.top(), dw, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                       QtGui.QFontMetrics(f4).elidedText(r["detail"], QtCore.Qt.ElideRight, int(dw)))
            if el:
                p.setPen(QtGui.QColor(160, 160, 170))
                p.drawText(QtCore.QRectF(rect.right() - 56 - ew, rect.top(), ew, rect.height()),
                           QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, el)
            col = QtGui.QColor(*PHASE_DOT.get(r["phase"], (150, 150, 160)))
            p.setPen(QtCore.Qt.NoPen); p.setBrush(col)
            p.drawEllipse(QtCore.QRectF(rect.right() - 52, rect.center().y() - 3, 6, 6))
            p.setFont(f4); p.setPen(col)
            p.drawText(QtCore.QRectF(rect.right() - 42, rect.top(), 38, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                       PHASE_WORD.get(r["phase"], ""))
            y += self.ROW_H
        p.end()


class YuiPet(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.scale = self.cfg["petHeight"] / LOGICAL_H   # 높이 기반 배율(매직넘버 제거)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.label = QtWidgets.QLabel(self)
        self.label.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.anim_durs = {name: durs for name, (row, durs) in ROW_DEF.items()}
        if not self._load_sheet(pet_sheet_path(self.cfg.get("pet", ""))):
            QtWidgets.QMessageBox.critical(self, "유이 펫", "스프라이트를 읽지 못했다")
            sys.exit(1)

        self.phase = "idle"
        self.anim = "idle"
        self.frame_idx = 0
        self.oneshot_after = None
        self._last_key = None
        self.title = ""
        self.hook_detail = ""
        self.tail_detail = ""
        self._transcript = ""
        self.source = ""
        self.dragging = False
        self._drag_offset = self._last_mouse = self._press_pos = None
        self._moved = False
        self._look_state = False   # 커서 응시 상태(히스테리시스)
        self._done_gen = 0         # 완료 타이머 세대 토큰
        self._behavior = "rest"    # 자율 행동: rest | walk
        self._rest_until = 0.0
        self._walk_to = self._walk_last = 0.0
        self._hidden_by_fullscreen = False
        self._hidden_by_user = False
        self._say_until = 0.0
        self.lines = load_lines()
        self._pomo = None          # 뽀모도로: None | {"kind": "focus"|"break", "until": ts}
        self._clicks = []          # 연속 클릭 판정용 타임스탬프
        self._prox_until = 0.0     # 근접 반응 쿨다운
        self._throw = None         # 던져진 상태: {"vx","vy","x","y"}
        self._drag_track = []      # 드래그 속도 추정용 (시각, x, y)
        self.bubble = YuiBubble(self.cfg)
        self.panel = SessionPanel(self)
        self._hover_since = 0.0
        self._panel_opened = 0.0

        self._apply_size()   # 프레임을 현재 크기로 미리 스케일해 캐시
        self._move_to_corner()

        self.anim_timer = QtCore.QTimer(self); self.anim_timer.setSingleShot(True)
        self.anim_timer.timeout.connect(self._next_frame)
        self.track_timer = QtCore.QTimer(self); self.track_timer.timeout.connect(self._track)
        self.track_timer.start(TRACK_MS)
        self.poll_timer = QtCore.QTimer(self); self.poll_timer.timeout.connect(self._poll_status)
        self.poll_timer.start(POLL_MS)
        self.wander_timer = QtCore.QTimer(self); self.wander_timer.timeout.connect(self._wander_tick)
        self.wander_timer.start(WANDER_TICK_MS)
        self.fs_timer = QtCore.QTimer(self); self.fs_timer.timeout.connect(self._fullscreen_tick)
        self.fs_timer.start(FULLSCREEN_CHECK_MS)
        self.panel_timer = QtCore.QTimer(self); self.panel_timer.timeout.connect(self._panel_tick)
        self.panel_timer.start(200)
        self.pomo_timer = QtCore.QTimer(self); self.pomo_timer.timeout.connect(self._pomo_tick)
        self.pomo_timer.start(POMO_TICK_MS)
        self._setup_tray()
        self._apply_opacity()
        self._apply_click_through()
        self._weather = None
        self.weather_timer = QtCore.QTimer(self)
        self.weather_timer.timeout.connect(self._fetch_weather)
        self.weather_timer.start(WEATHER_REFRESH_MS)
        QtCore.QTimer.singleShot(6000, self._fetch_weather)
        QtCore.QTimer.singleShot(4000, self._greet)   # 켜지고 잠시 뒤 시간대 인사
        self.tail_timer = QtCore.QTimer(self); self.tail_timer.timeout.connect(self._tail_transcript)
        self.tail_timer.start(TAIL_MS)
        self._enter("idle")

    # ---- 크기/위치 ----
    def _screen(self):
        s = QtGui.QGuiApplication.screenAt(self.frameGeometry().center())
        return (s or QtGui.QGuiApplication.primaryScreen()).availableGeometry()

    def _apply_size(self):
        w, h = int(LOGICAL_W * self.scale), int(LOGICAL_H * self.scale)
        self.setFixedSize(w, h); self.label.setFixedSize(w, h); self.label.move(0, 0)
        # 크기별 프레임 캐시를 비우고, 실제 쓰는 애니만 지연 생성(슬라이더 드래그 반응성)
        self._px = (w, h)
        self.sframes = {}
        self.slook = None
        self._masks = {}   # 히트박스 마스크 캐시(크기가 바뀌면 같이 버린다)

    def _scaled(self, frames):
        w, h = self._px
        return [f.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                for f in frames]

    def frames(self, name):
        """현재 크기의 애니 프레임(첫 사용 시에만 스케일)."""
        fr = self.sframes.get(name)
        if fr is None:
            fr = self.sframes[name] = self._scaled(self.anim_frames[name])
        return fr

    def looks(self):
        if self.slook is None:
            self.slook = self._scaled(self.look_frames)
        return self.slook

    # ---- 트레이 아이콘 ----
    def _setup_tray(self):
        """창을 놓쳐도 되돌릴 수 있게 트레이에 둔다. 종료가 우클릭 메뉴뿐이면 곤란하다."""
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            logging.info("system tray unavailable")
            self.tray = None
            return
        self.tray = QtWidgets.QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("유이 펫")

        m = QtWidgets.QMenu()
        m.setStyleSheet(MENU_QSS)
        self._act_show = m.addAction("펫 보이기")
        self._act_show.setCheckable(True); self._act_show.setChecked(True)
        self._act_show.toggled.connect(self.set_visible_by_user)
        self._act_wander = m.addAction("자유롭게 돌아다니기")
        self._act_wander.setCheckable(True)
        self._act_wander.setChecked(bool(self.cfg.get("wander", True)))
        self._act_wander.toggled.connect(self._set_wander)
        self._act_through = m.addAction("클릭 통과")
        self._act_through.setCheckable(True)
        self._act_through.setChecked(bool(self.cfg.get("clickThrough", False)))
        self._act_through.toggled.connect(self._set_click_through)
        self._act_pomo = m.addAction("뽀모도로 시작")
        self._act_pomo.setCheckable(True)
        self._act_pomo.toggled.connect(self._set_pomodoro)
        m.addSeparator()
        act_auto = m.addAction("부팅 시 자동 실행")
        act_auto.setCheckable(True); act_auto.setChecked(autostart_enabled())
        act_auto.toggled.connect(lambda on: act_auto.setChecked(set_autostart(on) and on))
        m.addSeparator()
        m.addAction("종료").triggered.connect(self._quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        # 아이콘을 더블클릭하면 숨김/보임 토글
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self._act_show.setChecked(self._hidden_by_user)

    def _set_click_through(self, on):
        self.cfg["clickThrough"] = bool(on)
        self._save_cfg({"clickThrough": self.cfg["clickThrough"]})
        self._apply_click_through()

    def _set_wander(self, on):
        self.cfg["wander"] = bool(on)
        self._save_cfg({"wander": self.cfg["wander"]})
        self._rest(1000) if on else self._enter("idle")

    def _quit(self):
        self.panel.close()
        self.bubble.close()
        if self.tray:
            self.tray.hide()
        QtWidgets.QApplication.quit()

    def _load_sheet(self, path):
        """스프라이트 시트를 읽어 프레임을 만든다. 펫 교체 때 다시 호출된다."""
        sheet = QtGui.QPixmap(path)
        if sheet.isNull():
            logging.error("sheet load failed: %s", path)
            return False
        sheet.setDevicePixelRatio(1.0)   # 스프라이트는 항상 실제 픽셀 그대로 다룬다
        # 시트 해상도에서 셀 크기를 역산(원본 192x208, 4x면 768x832)
        global CELL_W, CELL_H
        CELL_W, CELL_H = sheet.width() // SHEET_COLS, sheet.height() // SHEET_ROWS
        # 원본 대비 몇 배 시트인지 → 선명하게 키울 수 있는 상한
        self.sheet_scale = CELL_H / LOGICAL_H
        self.max_scale = max(FALLBACK_MAX_SCALE, self.sheet_scale)
        self.scale = max(MIN_SCALE, min(self.max_scale, self.scale))
        logging.info("sheet %s cell %dx%d (%.1fx)",
                     os.path.basename(path), CELL_W, CELL_H, self.sheet_scale)
        self.anim_frames = {name: [cut(sheet, row, c) for c in range(len(durs))]
                            for name, (row, durs) in ROW_DEF.items()}
        self.look_frames = [cut(sheet, R_LOOK_A, c) for c in range(8)] + \
                           [cut(sheet, R_LOOK_B, c) for c in range(8)]
        return True

    def _switch_pet(self, pet_id):
        if pet_id == self.cfg.get("pet", ""):
            return
        path = pet_sheet_path(pet_id)
        if not self._load_sheet(path):
            return
        self.cfg["pet"] = pet_id
        self._save_cfg({"pet": pet_id})
        self._apply_size()          # 프레임·마스크 캐시를 새 시트로 다시 만든다
        self._enter(self.anim)
        if self.tray:
            self.tray.setIcon(self._tray_icon())

    def _tray_icon(self):
        src = self.anim_frames["idle"][0]
        w, h = src.width(), src.height()
        return QtGui.QIcon(src.copy(int(w * 0.30), int(h * 0.01),
                                    int(w * 0.40), int(h * 0.30)))

    def _apply_opacity(self):
        o = float(self.cfg.get("opacity", 1.0))
        o = max(0.2, min(1.0, o))
        self.setWindowOpacity(o)
        self.bubble.setWindowOpacity(o)

    def _apply_click_through(self):
        """켜면 클릭이 통째로 통과한다. 되돌리려면 트레이를 써야 한다."""
        on = bool(self.cfg.get("clickThrough", False))
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, on)
        # 속성 변경은 창을 다시 띄워야 반영된다
        if self.isVisible():
            self.hide()
            self.show()

    def _mask_for(self, pm):
        """캐릭터 실루엣만 클릭을 받도록 알파에서 마스크를 만든다.

        창은 셀 비율(192x208)이라 유이 좌우로 투명한 여백이 넓다. 832px로 키우면
        좌우 180px씩이 빈 공간인데도 클릭을 먹어 뒤쪽 화면을 못 누른다.
        판정용이라 정밀할 필요가 없어 축소본에서 만들어 다시 늘린다 — 크기와 무관하게 4ms 안쪽.
        """
        key = pm.cacheKey()
        r = self._masks.get(key)
        if r is None:
            small = pm if pm.height() <= MASK_MAX_H else \
                pm.scaledToHeight(MASK_MAX_H, QtCore.Qt.FastTransformation)
            bmp = QtGui.QBitmap.fromImage(
                small.toImage().createAlphaMask(QtCore.Qt.ThresholdAlphaDither))
            if small.size() != pm.size():
                bmp = QtGui.QBitmap.fromPixmap(
                    bmp.scaled(pm.width(), pm.height(),
                               QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.FastTransformation))
            r = self._masks[key] = QtGui.QRegion(bmp)
        return r

    def set_scale(self, scale, persist=False):
        """슬라이더용 크기 변경. 발밑(하단 중앙)을 고정해 자라나듯 커진다."""
        scale = max(MIN_SCALE, min(self.max_scale, scale))
        if abs(scale - self.scale) < 0.005:
            return
        g = self.frameGeometry()
        anchor_x, anchor_y = g.center().x(), g.bottom()
        self.scale = scale
        self._apply_size()
        scr = self._screen()
        x = max(scr.left(), min(anchor_x - self.width() // 2, scr.right() - self.width()))
        y = max(scr.top(), min(anchor_y - self.height(), scr.bottom() - self.height()))
        self.move(int(x), int(y))
        self._enter(self.anim)
        self._reposition_bubble()
        if persist:
            self._save_size()

    def _save_cfg(self, changes):
        """config.json의 일부 키만 갱신(나머지 설정은 보존)."""
        try:
            cfg = {}
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg.update(changes)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            logging.exception("save config failed")

    def _save_size(self):
        """선택한 크기를 config.json에 저장해 다음 실행에도 유지."""
        self._save_cfg({"petHeight": int(round(LOGICAL_H * self.scale))})

    def _move_to_corner(self):
        scr = self._screen()
        self.move(scr.right() - self.width() - 40, scr.bottom() - self.height() - 40)
        self._reposition_bubble()

    def _reposition_bubble(self):
        if not self.bubble.isVisible():
            return
        g = self.frameGeometry()
        bw, bh = self.bubble.width(), self.bubble.height()
        scr = self._screen()
        y = g.top() - bh - 4
        down = True
        if y < scr.top():
            y = g.bottom() + 4; down = False
        self.bubble.set_tail(down)
        x = max(scr.left() + 2, min(g.center().x() - bw // 2, scr.right() - bw - 2))
        self.bubble.move(x, y)

    # ---- 대사 ----
    @staticmethod
    def _split_line(item):
        """대사 한 줄 → (한국어, 일본어). 문자열만 있는 옛 형식도 받아준다."""
        if isinstance(item, dict):
            return item.get("ko", "") or item.get("ja", ""), item.get("ja", "")
        return str(item), ""

    def _pick_line(self, kind=None):
        sp = self.lines.get("special", {}) or {}
        today = sp.get(time.strftime("%m-%d"))
        if today and random.random() < 0.6:
            return self._split_line(random.choice(today))
        pool = self.lines.get(kind or time_bucket()) or []
        return self._split_line(random.choice(pool)) if pool else ("", "")

    def _say(self, ko, ja="", ms=SAY_MS, force=False):
        """말풍선으로 한마디.

        평소엔 작업 상태 표시를 가리지 않으려고 idle일 때만 말한다.
        force=True(사용자가 직접 클릭)면 작업 중에도 말하고, 끝나면 상태 표시로 되돌린다.
        """
        if not ko or not self.isVisible():
            return
        if not force and self.phase != "idle":
            return
        self.bubble.set_badge("")
        self.bubble.set_more(0)
        self.bubble.set_state("say", ko, ja if self.cfg.get("showJapanese", True) else "")
        if not self.bubble.isVisible():
            self.bubble.show()
        self._reposition_bubble()
        if force and self.phase != "idle" and ms == SAY_MS:
            ms = SAY_MS_BUSY        # 작업 상태를 오래 가리지 않는다
        self._say_until = time.monotonic() + ms / 1000.0
        QtCore.QTimer.singleShot(ms + 20, self._say_done)

    def _dismiss_say(self):
        """대사를 지금 끝낸다. 기다릴 필요 없이 작업 표시로 돌아간다."""
        self._say_until = 0.0
        self._say_done()

    def _say_done(self):
        if time.monotonic() < self._say_until:   # 그 사이 새 대사가 떴다
            return
        if self.phase == "idle":
            self.bubble.hide()
        else:
            self._refresh_bubble()               # 가려 뒀던 작업 상태를 되돌린다

    def _saying(self):
        return time.monotonic() < self._say_until

    def _greet(self):
        self._say(*self._pick_line())

    # ---- 작업 목록 패널 ----
    def _panel_tick(self):
        """열려 있는 동안 내용을 갱신하고, 펫·패널에서 커서가 멀어지면 접는다."""
        if not self.panel.isVisible():
            return
        if not self.isVisible():
            self.panel.hide()
            return
        c = QtGui.QCursor.pos()
        near = (self.frameGeometry().adjusted(-40, -40, 40, 40).contains(c)
                or self.panel.frameGeometry().adjusted(-40, -40, 40, 40).contains(c))
        # 막 열었을 땐 잠시 유지한다. 커서를 옮겨도 바로 닫히면 쓰기 어렵다
        if time.monotonic() - self._panel_opened < PANEL_GRACE_S:
            near = True
        if near:
            self.panel.refresh(self.read_sessions())   # 도는 동안 내용이 바뀐다
        else:
            self.panel.hide()

    def _toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self._show_panel()

    def _mask_hit(self, gpos):
        """커서가 실루엣 안에 있는지(투명 여백은 제외)."""
        m = self.mask()
        return m.isEmpty() or m.contains(gpos - self.frameGeometry().topLeft())

    def _show_panel(self):
        self._panel_opened = time.monotonic()
        rows = self.read_sessions()
        self.panel.refresh(rows)
        self.panel.place_over(self.frameGeometry())
        if not self.panel.isVisible():
            self.panel.show()

    # ---- 클릭 반응 ----
    def _on_click(self):
        now = time.monotonic()
        self._clicks = [t for t in self._clicks if now - t <= CLICK_COMBO_MS / 1000.0]
        self._clicks.append(now)
        if len(self._clicks) >= CLICK_COMBO_N:      # 연달아 누르면 좋아한다
            self._clicks = []
            self._enter("jumping", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
            self._say(*self._pick_line("petted"), force=True)
            return
        if self.panel.isVisible():  # 목록이 열려 있으면 먼저 닫는다
            self.panel.hide()
            return
        if self._saying():          # 대사 중 다시 누르면 바로 작업 표시로 돌아간다
            self._dismiss_say()
            return
        act = self.cfg.get("clickAction", "panel")
        if act == "panel":
            # 도는 작업이 있으면 목록, 없으면 한마디 — 빈 목록만 뜨면 허무하다
            if self.read_sessions():
                self._toggle_panel()
            else:
                self._say(*self._pick_line("idleChat"), force=True)
        elif act == "app":
            try:
                activate_vscode()
            except Exception:
                pass
        elif act == "talk":
            self._say(*self._pick_line("idleChat"), force=True)

    def _proximity_check(self):
        """커서가 아주 가까이 오면 놀란다. 쿨다운을 둬서 성가시지 않게."""
        if self.phase != "idle" or self.dragging or self._throw or self.anim != "idle":
            return
        now = time.monotonic()
        if now < self._prox_until:
            return
        dx, dy = self._cursor_vec()
        if math.hypot(dx, dy) > self.height() * PROXIMITY_RATIO:
            return
        self._prox_until = now + PROXIMITY_COOLDOWN_S
        self._enter(random.choice(("jumping", "waving")), oneshot_after="idle")
        self._say(*self._pick_line("surprised"))

    # ---- 던지기 ----
    def _begin_throw(self):
        """드래그를 놓을 때 속도가 충분하면 날아간다. 착지 프레임이 없어 jumping으로 대신한다."""
        if not self.cfg.get("throwEnabled", True) or len(self._drag_track) < 2:
            return False
        (t0, x0, y0), (t1, x1, y1) = self._drag_track[0], self._drag_track[-1]
        if time.monotonic() - t1 > THROW_MAX_IDLE_S:   # 놓기 전에 멈췄으면 그냥 내려놓는다
            return False
        dt = t1 - t0
        if dt <= 0.001:
            return False
        vx, vy = (x1 - x0) / dt, (y1 - y0) / dt
        if math.hypot(vx, vy) < THROW_MIN_SPEED:
            return False
        self._throw = {"vx": vx, "vy": vy, "x": float(self.x()), "y": float(self.y())}
        self._enter("jumping")
        return True

    def _throw_step(self, dt):
        scr = self._screen()
        t = self._throw
        t["vy"] += THROW_GRAVITY * dt
        t["x"] += t["vx"] * dt
        t["y"] += t["vy"] * dt
        floor = scr.bottom() - self.height()
        if t["x"] < scr.left() or t["x"] > scr.right() - self.width():   # 벽에서 튕김
            t["x"] = max(scr.left(), min(t["x"], scr.right() - self.width()))
            t["vx"] = -t["vx"] * THROW_BOUNCE
        if t["y"] >= floor:                                              # 착지
            t["y"] = floor
            t["vy"] = -t["vy"] * THROW_BOUNCE
            t["vx"] *= 0.7
            if abs(t["vy"]) < 120:
                self.move(int(t["x"]), int(floor))
                self._throw = None
                self._rest(random.randint(1500, 3000))
                return
        if t["y"] < scr.top():
            t["y"] = float(scr.top())
            t["vy"] = abs(t["vy"]) * THROW_BOUNCE
        self.move(int(t["x"]), int(t["y"]))
        if self.bubble.isVisible():
            self._reposition_bubble()

    # ---- 날씨 ----
    def _fetch_weather(self):
        """Open-Meteo(키 불필요)에서 현재 날씨만 가져온다. 실패하면 조용히 넘어간다."""
        if not self.cfg.get("weatherEnabled", False):
            return
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
               "&current=temperature_2m,weather_code" %
               (self.cfg.get("weatherLat"), self.cfg.get("weatherLon")))
        try:
            if not hasattr(self, "_net"):
                self._net = QtNetwork.QNetworkAccessManager(self)
            reply = self._net.get(QtNetwork.QNetworkRequest(QtCore.QUrl(url)))
            reply.finished.connect(lambda r=reply: self._weather_done(r))
        except Exception:
            logging.exception("weather request failed")

    def _weather_done(self, reply):
        try:
            if reply.error() == QtNetwork.QNetworkReply.NoError:
                d = json.loads(bytes(reply.readAll().data()).decode("utf-8"))
                cur = d.get("current", {})
                self._weather = (int(cur.get("weather_code", -1)),
                                 float(cur.get("temperature_2m", 99)))
                logging.info("weather %s", self._weather)
        except Exception:
            logging.exception("weather parse failed")
        finally:
            reply.deleteLater()

    def _weather_kind(self):
        """날씨 → 대사 카테고리. 해당 없으면 None."""
        if not self._weather:
            return None
        code, temp = self._weather
        if code in (71, 73, 75, 77, 85, 86):
            return "weatherSnow"
        if 51 <= code <= 67 or 80 <= code <= 82 or code in (95, 96, 99):
            return "weatherRain"
        if temp >= 30:
            return "weatherHot"
        if temp <= 0:
            return "weatherCold"
        return None

    # ---- 뽀모도로 ----
    def _set_pomodoro(self, on):
        if on:
            self._pomo_begin("focus")
        else:
            self._pomo = None
            self._pomo_tooltip()

    def _pomo_begin(self, kind):
        mins = self.cfg["pomodoroFocusMin"] if kind == "focus" else self.cfg["pomodoroBreakMin"]
        self._pomo = {"kind": kind, "until": time.monotonic() + mins * 60}
        self._pomo_tooltip()

    def _pomo_tooltip(self):
        """남은 시간은 트레이 툴팁으로만 알린다 — 말풍선을 계속 띄우면 방해된다."""
        if not self.tray:
            return
        if not self._pomo:
            self.tray.setToolTip("유이 펫")
            return
        left = max(0, int(self._pomo["until"] - time.monotonic()))
        label = "집중" if self._pomo["kind"] == "focus" else "휴식"
        self.tray.setToolTip("유이 펫 — %s %d:%02d 남음" % (label, left // 60, left % 60))

    def _pomo_tick(self):
        if not self._pomo:
            return
        self._pomo_tooltip()
        if time.monotonic() < self._pomo["until"]:
            return
        done = self._pomo["kind"]
        self._pomo_begin("break" if done == "focus" else "focus")
        self._say(*self._pick_line("pomoFocusEnd" if done == "focus" else "pomoBreakEnd"),
                  ms=7000)
        if self.phase == "idle" and not self.dragging:
            self._enter("waving", oneshot_after="idle")

    def _refresh_bubble(self):
        if self._saying():              # 대사 중엔 건드리지 않는다(끝나면 여기로 다시 온다)
            return
        if self.phase == "idle":
            self.bubble.hide()
            return
        # privacyMode면 대화 원문 노출 없이 도구 작업 문장만, 아니면 공개 문장 우선
        if self.cfg.get("privacyMode", True):
            detail = self.hook_detail
        else:
            detail = self.tail_detail or self.hook_detail
        self.bubble.set_badge(self.source)
        self.bubble.set_more(len(self.read_sessions()))
        self.bubble.set_state(self.phase, self.title, detail)
        if not self.bubble.isVisible():
            self.bubble.show()
        self._reposition_bubble()

    def _show(self, pm):
        if os.environ.get("YUI_DEBUG"):
            g = self.geometry()
            logging.info("show pm=%dx%d dpr=%.2f label=%dx%d win=%dx%d@%d,%d scale=%.2f px=%s dpr_win=%.2f",
                         pm.width(), pm.height(), pm.devicePixelRatio(),
                         self.label.width(), self.label.height(),
                         g.width(), g.height(), g.x(), g.y(), self.scale, self._px,
                         self.devicePixelRatioF())
        self.label.setPixmap(pm)
        self.setMask(self._mask_for(pm))   # 투명 여백은 클릭이 통과하도록

    # ---- 애니 재생 ----
    def _enter(self, anim, oneshot_after=None):
        self.anim = anim
        self.frame_idx = 0
        self.oneshot_after = oneshot_after
        self.anim_timer.stop()
        if anim == "idle":
            if not self._saying():      # 방금 띄운 대사를 지우면 안 된다
                self.bubble.hide()
            self._render_idle()
            self.anim_timer.start(self.anim_durs["idle"][0])   # 호흡 루프 시작
        else:
            self._show(self.frames(anim)[0])
            self.anim_timer.start(self.anim_durs[anim][0])

    def _next_frame(self):
        if self.dragging:
            return
        if self.anim == "idle":
            # 근거리: idle 6프레임 호흡/깜빡임 루프 / 원거리: 커서 방향 시선(정지)
            if self._looking():
                self._render_idle()
                self.anim_timer.start(TRACK_MS)
            else:
                self.frame_idx = (self.frame_idx + 1) % len(self.anim_durs["idle"])
                self._show(self.frames("idle")[self.frame_idx])
                dur = self.anim_durs["idle"][self.frame_idx]
                if self.frame_idx == 0:
                    # 한 사이클(깜빡임) 끝 → 다음까지 쉼. 간격을 흔들어야 기계처럼 안 보인다
                    dur = random.randint(BLINK_REST_MIN_MS, BLINK_REST_MAX_MS)
                self.anim_timer.start(dur)
            return
        durs = self.anim_durs[self.anim]
        self.frame_idx += 1
        if self.frame_idx >= len(durs):
            self.frame_idx = 0
            if self.oneshot_after is not None:
                nxt, self.oneshot_after = self.oneshot_after, None
                self._enter(nxt)
                return
        self._show(self.frames(self.anim)[self.frame_idx])
        self.anim_timer.start(durs[self.frame_idx])

    # ---- idle 커서 추적 ----
    def _cursor_vec(self):
        c = QtGui.QCursor.pos(); ctr = self.frameGeometry().center()
        return c.x() - ctr.x(), c.y() - ctr.y()

    def _looking(self):
        # 히스테리시스: 멀어질 때 0.85, 가까워질 때 0.6 (경계 떨림 방지)
        dx, dy = self._cursor_vec()
        dist = math.hypot(dx, dy)
        base = max(self.width(), self.height())
        if self._look_state and dist < base * 0.6:
            self._look_state = False
        elif not self._look_state and dist > base * 0.85:
            self._look_state = True
        return self._look_state

    def _render_idle(self):
        if self._looking():
            dx, dy = self._cursor_vec()
            idx = int(round((math.degrees(math.atan2(dx, -dy)) % 360) / 22.5)) % 16
            idx = LOOK_REMAP.get(idx, idx)   # 어긋난 프레임 보정
            self._show(self.looks()[idx])
        else:
            self._show(self.frames("idle")[0])

    def _track(self):
        if self.dragging or self.phase != "idle" or self.oneshot_after is not None:
            return
        if self.anim != "idle":      # 걷는 중엔 시선 프레임이 걸음을 덮어쓰면 안 된다
            return
        if self._looking():          # 원거리에서만 시선 부드럽게 갱신(근거리는 호흡 루프가 담당)
            self._render_idle()

    # ---- 자율 행동 ----
    def _can_wander(self):
        """스스로 움직여도 되는 상황인지. 작업 표시 중이거나 잡혀 있으면 가만히 있는다."""
        return (self.cfg.get("wander", True) and self.phase == "idle"
                and not self.dragging and self.oneshot_after is None)

    def _profile(self):
        """사용 중이면 얌전하게(CALM), 손을 멈췄거나 자리를 비웠으면 자유롭게(FREE)."""
        try:
            return CALM if user_idle_seconds() < USER_ACTIVE_S else FREE
        except Exception:
            return CALM

    def _rest(self, ms=None):
        self._behavior = "rest"
        if ms is None:
            ms = random.randint(*self._profile()["rest"])
        self._rest_until = time.monotonic() + ms / 1000.0
        # 작업 표시 중에는 그 애니를 유지한다. idle 애니로 돌리는 건 idle일 때만.
        if self.anim != "idle" and self.phase == "idle":
            self._enter("idle")

    def _pick_action(self):
        names, weights = zip(*self._profile()["actions"])
        act = random.choices(names, weights=weights)[0]
        if act == "walk":
            self._start_walk()
        elif act in ("jump", "wave"):
            self._enter("jumping" if act == "jump" else "waving", oneshot_after="idle")
            self._rest(random.randint(1200, 3000))
        elif act == "talk":
            try:
                bored = user_idle_seconds() > BORED_AFTER_S
            except Exception:
                bored = False
            if bored:
                kind = "bored"
            else:   # 평소엔 일상 대사·명대사·날씨를 섞는다
                wk = self._weather_kind()
                if wk and random.random() < 0.3:
                    kind = wk
                else:
                    kind = "quotes" if random.random() < 0.4 else "idleChat"
            self._say(*self._pick_line(kind))
            self._rest()
        else:
            self._rest()

    def _start_walk(self):
        scr = self._screen()
        span = random.uniform(*self._profile()["dist"]) * self.scale
        direction = random.choice((-1, 1))
        x = self.x() + direction * span
        # 화면 밖으로 나가려 하면 반대로 튼다
        if x < scr.left() or x > scr.right() - self.width():
            direction = -direction
            x = self.x() + direction * span
        self._walk_to = max(scr.left(), min(x, scr.right() - self.width()))
        if abs(self._walk_to - self.x()) < 8:
            self._rest(1500)
            return
        self._behavior = "walk"
        self._walk_last = time.monotonic()
        self._enter("running-right" if self._walk_to > self.x() else "running-left")

    # ---- 전체화면 앱이 뜨면 비켜준다 ----
    def _fullscreen_tick(self):
        try:
            hide = fullscreen_app_active()
        except Exception:
            return
        if hide == self._hidden_by_fullscreen:
            return
        self._hidden_by_fullscreen = hide
        if hide:
            self.bubble.hide()
            self.panel.hide()
            self.hide()
        elif not self._hidden_by_user:
            self.show()
            self._refresh_bubble()

    def set_visible_by_user(self, visible):
        """트레이에서 보이기/숨기기. 전체화면 때문에 숨은 상태와 구분해 둔다."""
        self._hidden_by_user = not visible
        if visible and not self._hidden_by_fullscreen:
            self.show()
            self._refresh_bubble()
        elif not visible:
            self.bubble.hide()
            self.panel.hide()
            self.hide()

    def _wander_tick(self):
        if not self.isVisible():
            return
        if self._throw:                       # 날아가는 중엔 물리만 돌린다
            now = time.monotonic()
            dt = min(0.05, now - getattr(self, "_throw_last", now))
            self._throw_last = now
            self._throw_step(dt)
            return
        self._throw_last = time.monotonic()
        self._proximity_check()
        if not self._can_wander():
            if self._behavior == "walk":
                self._rest(2000)
            return
        if self._behavior == "rest":
            if time.monotonic() >= self._rest_until:
                self._pick_action()
            return
        # 걷는 중 — 경과 시간만큼 이동
        now = time.monotonic()
        step = WANDER_SPEED * self.scale * (now - self._walk_last)
        self._walk_last = now
        dx = self._walk_to - self.x()
        if abs(dx) <= step:
            self.move(int(self._walk_to), self.y())
            self._rest()
            return
        self.move(int(self.x() + math.copysign(step, dx)), self.y())
        if self.bubble.isVisible():
            self._reposition_bubble()

    # ---- PetState 폴링 ----
    def read_sessions(self):
        """살아 있는 세션들을 우선순위·최신순으로. 작업 목록 패널과 집계가 함께 쓴다."""
        now = time.time_ns()
        rows = []
        try:
            sources = os.listdir(SESSIONS_DIR)
        except OSError:
            return rows
        for src in sources:
            sdir = os.path.join(SESSIONS_DIR, src)
            if not os.path.isdir(sdir):
                continue
            try:
                files = os.listdir(sdir)
            except OSError:
                continue
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(sdir, fn), encoding="utf-8") as f:
                        d = json.load(f)
                except (OSError, ValueError):
                    continue
                ts = d.get("ts", 0) or 0
                if now - ts > STALE_NS:      # 오래된 세션 무시
                    continue
                ph = d.get("phase", "idle")
                exp = d.get("expires_at")
                if ph in ("done", "failed") and exp and now > exp:
                    ph = "idle"
                if ph == "idle":
                    continue
                rows.append({"phase": ph, "title": d.get("title", ""),
                             "detail": d.get("detail", ""), "ts": ts,
                             "started": d.get("started_at", 0) or 0,
                             "transcript": d.get("transcript", ""),
                             "source": d.get("source", src)})
        rows.sort(key=lambda r: (PRIORITY.get(r["phase"], 0), r["ts"]), reverse=True)
        return rows

    def _aggregate(self):
        """세션들을 우선순위(waiting>failed>working>done>idle)로 묶어 대표 상태 하나."""
        rows = self.read_sessions()
        if not rows:
            return None
        working = sum(1 for r in rows if r["phase"] == "working")
        r = rows[0]
        ph, title, detail = r["phase"], r["title"], r["detail"]
        tr, source, started = r["transcript"], r["source"], r["started"]
        if ph == "working" and working > 1:   # 여러 세션 동시 작업
            title = (title + f"  · 외 {working - 1}개") if title else f"{working}개 작업 중"
        return ph, title, detail, tr, source, started

    def _poll_status(self):
        active = self._aggregate()
        phase, title, detail, tr, source, started = active if active else ("idle", "", "", "", "", 0)
        self._transcript = tr
        self.source = source
        self.bubble.set_started(started)
        key = (phase, title, detail, source)
        if key == self._last_key:
            return
        self._last_key = key
        self.title = title
        self.hook_detail = detail
        self.tail_detail = ""
        prev = self.phase
        self.phase = phase
        self._refresh_bubble()
        if self.dragging:
            return
        if self.oneshot_after is not None:
            self.oneshot_after = PHASE_ANIM.get(phase, "idle")
            return
        self._apply_phase(phase, prev)

    def _apply_phase(self, phase, prev):
        if phase == "done":
            if prev != "done":
                self._begin_done()
        elif phase in ("working", "waiting", "failed"):
            target = PHASE_ANIM[phase]
            if self.anim != target:
                self._enter(target)
        elif phase == "idle":
            self._enter("idle")
            self._rest()      # 작업이 끝났으니 잠시 뒤부터 다시 돌아다닌다

    def _begin_done(self):
        self._enter("review")
        self._done_gen += 1
        gen = self._done_gen
        QtCore.QTimer.singleShot(int(self.cfg["completedDisplaySeconds"] * 1000),
                                 lambda: self._after_done(gen))

    def _after_done(self, gen):
        # 세대 토큰이 다르면(그 사이 새 완료 발생) 이전 타이머는 무시
        if gen != self._done_gen:
            return
        if self.phase == "done" and not self.dragging:
            self.phase = "idle"
            self._enter("waving", oneshot_after="idle")

    # ---- transcript tailer: 공개 assistant 텍스트로 진행 문장 보충 ----
    def _tail_transcript(self):
        if self.phase != "working":
            return
        path = self._transcript
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                f.seek(0, 2); size = f.tell()
                f.seek(max(0, size - 400000))
                chunk = f.read().decode("utf-8", "ignore")
        except Exception:
            return
        text = None
        for line in chunk.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "assistant":
                content = d.get("message", {}).get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip():
                            text = c["text"]
        if text:
            snip = summarize(text)
            if snip and snip != self.tail_detail:
                self.tail_detail = snip
                self._refresh_bubble()

    # ---- 마우스 ----
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.dragging = True; self._moved = False
            self._press_pos = e.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._last_mouse = self._press_pos
            self._throw = None
            self._drag_track = [(time.monotonic(), self._press_pos.x(), self._press_pos.y())]
            e.accept()

    def mouseMoveEvent(self, e):
        if not (self.dragging and (e.buttons() & QtCore.Qt.LeftButton)):
            return
        p = e.globalPosition().toPoint()
        if (p - self._press_pos).manhattanLength() > CLICK_MOVE_TOL:
            self._moved = True
        dx = p.x() - self._last_mouse.x()
        if dx > DRAG_RUN_THRESHOLD and self.anim != "running-right":
            self._run_loop("running-right")
        elif dx < -DRAG_RUN_THRESHOLD and self.anim != "running-left":
            self._run_loop("running-left")
        self._last_mouse = p
        self.move(p - self._drag_offset)
        self._reposition_bubble()
        # 놓을 때 던지려면 최근 이동 속도가 필요하다. 0.12초치만 남긴다
        now = time.monotonic()
        self._drag_track.append((now, p.x(), p.y()))
        self._drag_track = [t for t in self._drag_track if now - t[0] <= 0.12] or self._drag_track[-2:]
        e.accept()

    def _run_loop(self, name):
        self.anim = name; self.frame_idx = 0
        self._show(self.frames(name)[0]); self.anim_timer.stop()
        QtCore.QTimer.singleShot(0, self._drag_run_step)

    def _drag_run_step(self):
        if not self.dragging or self.anim not in ("running-right", "running-left"):
            return
        durs = self.anim_durs[self.anim]
        self.frame_idx = (self.frame_idx + 1) % len(durs)
        self._show(self.frames(self.anim)[self.frame_idx])
        QtCore.QTimer.singleShot(durs[self.frame_idx], self._drag_run_step)

    def mouseReleaseEvent(self, e):
        if not self.dragging:
            return
        self.dragging = False
        if not self._moved:
            self._on_click()
            self._enter("review" if self.phase == "done" else PHASE_ANIM.get(self.phase, "idle"))
            self._rest(random.randint(2000, 4000))
            return
        # 완료 연출 중 드래그했다 놓으면 review 유지(녹색체크 말풍선만 남는 문제 방지)
        self._enter("review" if self.phase == "done" else PHASE_ANIM.get(self.phase, "idle"))
        if not self._begin_throw():
            self._rest(random.randint(2000, 4000))   # 놓자마자 걸어가면 어색하니 잠시 서 있는다

    def contextMenuEvent(self, e):
        m = QtWidgets.QMenu(self)
        m.setStyleSheet(MENU_QSS)
        m.setWindowFlag(QtCore.Qt.NoDropShadowWindowHint, False)
        a_wave = m.addAction("손 흔들기"); a_jump = m.addAction("점프")
        a_wander = m.addAction("자유롭게 돌아다니기")
        a_wander.setCheckable(True); a_wander.setChecked(bool(self.cfg.get("wander", True)))
        m.addSeparator()
        m.addAction(SliderAction(m, self, "size"))
        m.addAction(SliderAction(m, self, "opacity"))
        m.addSeparator()

        pets = pet_list()
        if len(pets) > 1:                       # 갈아탈 펫이 있을 때만 보여준다
            pm = m.addMenu("펫 바꾸기")
            cur = self.cfg.get("pet", "")
            pet_acts = {}
            for pid, name in pets:
                a = pm.addAction(name)
                a.setCheckable(True); a.setChecked(pid == cur)
                pet_acts[a] = pid
        else:
            pet_acts = {}

        cm = m.addMenu("클릭하면")
        click_acts = {}
        for key, label in (("panel", "작업 목록 열기"), ("app", "앱 창 띄우기"),
                           ("talk", "한마디 하기"), ("none", "아무것도 안 함")):
            a = cm.addAction(label)
            a.setCheckable(True); a.setChecked(self.cfg.get("clickAction", "panel") == key)
            click_acts[a] = key

        a_throw = m.addAction("던지기")
        a_throw.setCheckable(True); a_throw.setChecked(bool(self.cfg.get("throwEnabled", True)))
        a_through = m.addAction("클릭 통과 (트레이로만 해제)")
        a_through.setCheckable(True)
        a_through.setChecked(bool(self.cfg.get("clickThrough", False)))
        m.addSeparator()
        a_quit = m.addAction("종료")
        act = m.exec(e.globalPos())
        if act in pet_acts:
            self._switch_pet(pet_acts[act]); return
        if act in click_acts:
            self.cfg["clickAction"] = click_acts[act]
            self._save_cfg({"clickAction": click_acts[act]}); return
        if act == a_throw:
            self.cfg["throwEnabled"] = not self.cfg.get("throwEnabled", True)
            self._save_cfg({"throwEnabled": self.cfg["throwEnabled"]})
            return
        if act == a_through:
            self.cfg["clickThrough"] = not self.cfg.get("clickThrough", False)
            self._save_cfg({"clickThrough": self.cfg["clickThrough"]})
            self._apply_click_through()
            if self.tray:
                self._act_through.setChecked(self.cfg["clickThrough"])
            return
        if act == a_wave:
            self._enter("waving", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
        elif act == a_jump:
            self._enter("jumping", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
        elif act == a_wander:
            self._set_wander(not self.cfg.get("wander", True))
            if self.tray:
                self._act_wander.setChecked(self.cfg["wander"])
        elif act == a_quit:
            self._quit()


def main():
    logging.basicConfig(filename=os.path.join(BASE, "yui_pet.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    def _hook(t, v, tb):
        logging.error("uncaught", exc_info=(t, v, tb))
    sys.excepthook = _hook

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 숨겨도 트레이로 살아 있어야 한다
    load_bundled_fonts()   # Pretendard 등 번들 폰트 등록

    # 단일 인스턴스 보장(중복 실행 방지)
    name = "YuiPetSingleton"
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(200):
        logging.info("already running; exiting")
        return
    server = QLocalServer()
    QLocalServer.removeServer(name)
    server.listen(name)
    app._yui_server = server  # GC 방지

    logging.info("started")
    pet = YuiPet(); pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
