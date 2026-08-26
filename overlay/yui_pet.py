# -*- coding: utf-8 -*-
"""
유이 윈도우 데스크톱 펫 — Codex Pet v2 스프라이트 규격 호환.
자율 행동(배회·대사·반응)이 기본이고, 클로드 코드 등 에이전트 작업 상태 표시는 선택 기능인 오버레이.

상태 소스(status.json = 공통 PetState) ──▶ 이 오버레이(렌더러)
  PetState: {source, session_id, phase, title, detail, transcript, ts(ns), expires_at?}
  phase: idle | working | waiting | done | failed
  - 생명주기(phase)·제목·기본 detail은 클로드 훅이 기록.
  - 진행 문장은 transcript의 '공개 assistant 텍스트'로 보충(raw thinking 미노출).
"""
import os
import re
import sys
import json
import math
import time
import random
import datetime
import html
import logging
import ctypes
from ctypes import wintypes

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6 import QtNetwork
from PySide6.QtNetwork import QLocalServer, QLocalSocket

try:
    from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput
except ImportError:           # PySide6-Addons가 없으면 소리만 빠지고 나머지는 그대로 돈다
    QSoundEffect = QMediaPlayer = QAudioOutput = None

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
# 스프라이트 발밑은 셀 아래쪽에서 살짝 떠 있다(4x 시트에서 y=813/832 → 논리 4.5px).
# 창 위나 바닥에 세울 때 이만큼 내려 놓아야 발이 바닥에 닿아 보인다.
FOOT_PAD = 4.5
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
# 기본 유이의 up-left 프레임(292.5·315·337.5°)만 방향이 어긋난다.
# 다른 v2 펫에는 자신의 검증된 16방향을 그대로 써야 한다.
LOOK_REMAP_BY_PET = {"": {13: 12, 14: 12, 15: 0}}   # 12=270 left, 0=000 up

POLL_MS, TRACK_MS, TAIL_MS = 300, 70, 600
DRAG_RUN_THRESHOLD, CLICK_MOVE_TOL = 2, 5
MIN_SCALE = 0.35            # 최소 73px — 아주 작게
DISPLAY_MAX_SCALE = 4.0     # 시트 해상도와 무관하게 모든 펫을 유이만큼 확대
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
# ---- 시선 ----
# 계속 바라보면 그건 응시가 된다. 사람 사이에서 편안한 상호 응시가 3~5초까지고 그 사이에도
# 1~2초씩 눈을 뗀다는 관찰을 그대로 가져왔다. 그래서 시선을 상태가 아니라 사건으로 두었다.
# 무슨 일이 있을 때만 _notice()로 잠깐 보고 정면으로 돌아온다.
GAZE_HOLD_S = (3.0, 5.0)          # 한 번 눈을 주면 이 사이의 시간만
GAZE_LOOK_S = (1.2, 2.5)          # 이만큼 이어 보다가
GAZE_AVERT_S = (0.8, 1.6)         # 이만큼 눈을 뗀다(시선 회피)
GAZE_NEAR_RATIO = 1.6             # 창 크기의 이 배수 안으로 커서가 들어오면 알아챈다
GAZE_NOTICE_COOLDOWN_S = 6.0      # 커서가 오갈 때마다 다시 보지는 않는다
GAZE_GLANCE_P = 0.30              # 손을 멈췄을 때 쉬면서 이쪽을 흘끗 볼 확률
# 던지기 물리. MIN_SPEED가 낮으면 그냥 옮기려던 것도 날아가 버린다.
# 확 뿌리는 동작에서만 걸리도록 높게 잡고, 놓기 직전까지 움직이고 있어야 한다.
THROW_GRAVITY, THROW_BOUNCE, THROW_MIN_SPEED = 2600, 0.45, 1400
# 제자리에서 떨어질 때는 던졌을 때보다 느리게. 같은 중력을 쓰면 한 프레임에
# 사라져 "떨어졌다"가 아니라 "순간이동"으로 보인다.
FALL_GRAVITY = 1500
FALL_START_VY = 60

# ---- 창 위 올라가기(선반) ----
SHELF_TICK_MS = 700          # 창 목록을 다시 훑는 주기. 매 프레임 훑으면 무겁다
SHELF_MIN_W = 260            # 이보다 좁은 창은 발판으로 쓰지 않는다
SHELF_MIN_H = 140
SHELF_EDGE_PAD = 10          # 선반 끝에서 이만큼 남기고 돌아선다
SHELF_HOP_MAX = 300          # 이 높이 차이까지는 뛰어올라간다(208px 기준, 크기에 비례)
SHELF_HOP_MS = 460
CLIMB_SPEED = 70             # 벽을 오르는 속도(208px 기준 초당 px)
TRACK_HINT_COOLDOWN_S = 12   # 커서가 가까이 올 때 곡명을 다시 알려줄 간격
THROW_MAX_IDLE_S = 0.08          # 놓기 전 이만큼 멈춰 있었으면 던지지 않는다
WEATHER_REFRESH_MS = 60 * 60 * 1000      # 날씨는 한 시간에 한 번이면 충분

ICON_DIR = os.path.join(BASE, "icons")
# 말풍선 왼쪽에 붙는 출처 배지. 아이콘 파일이 없으면 글자만 나온다.
SOURCE_BADGE = {"claude": ("Claude", "claude.png"),
                "codex": ("Codex", "codex.png"),
                "cli": ("CLI", "")}

SAY_MS = 4500                     # 대사 말풍선 표시 시간
PHASE_VOICE_COOLDOWN_S = 300      # 작업 완료·실패 목소리는 이 간격을 두고만 낸다
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
            "lang": "ko", "showJapanese": True,
            "pomodoroFocusMin": 25, "pomodoroBreakMin": 5,
            "clickAction": "panel", "clickThrough": False, "opacity": 1.0, "pet": "",
            "weatherEnabled": False, "weatherLat": 35.202944, "weatherLon": 136.233694,
            "throwEnabled": True, "chatEnabled": True, "gazeEnabled": True,
            "voiceEnabled": True, "voiceVolume": 0.7,
            "musicDirs": [], "musicVolume": 0.45, "musicShuffle": True,
            "musicFilter": "song",
            "climbWindows": True, "climbWalls": True,
            "projectAliases": {},
            # Codex 대화 기록을 직접 읽어 상태를 만든다. codexHomes가 비면 이 계정의
            # ~/.codex 하나만 본다(데스크톱·CLI가 같은 자리를 쓴다).
            "codexWatch": True, "codexHomes": []}


# ---- 표시 언어 -------------------------------------------------------------
# 한국어 원문을 그대로 키로 쓴다. 표에 없으면 원문이 나가므로 번역을 빠뜨려도
# 화면이 비지 않고, 코드를 읽을 때도 무슨 문구인지 바로 보인다.
LANGS = (("ko", "한국어"), ("en", "English"), ("ja", "日本語"))
LANG_CODES = [c for c, _ in LANGS]
_LANG = "ko"


def set_lang(code):
    global _LANG
    _LANG = code if code in LANG_CODES else "ko"


def cur_lang():
    return _LANG


def T(s):
    """한국어 원문을 지금 언어로. 표에 없으면 원문 그대로."""
    return s if _LANG == "ko" else TR.get(_LANG, {}).get(s, s)


TR = {
    "en": {
        # 앱 · 창 제목
        "유이 펫": "Yui Pet", "설정": "Settings", "유이 펫 — 음악": "Yui Pet — Music",
        "유이 펫 — %s %d:%02d 남음": "Yui Pet — %s %d:%02d left",
        "집중": "Focus", "휴식": "Break",
        "스프라이트를 읽지 못했어요": "Could not load the sprite sheet",
        # 펫 이름
        "유이 (기본)": "Yui (default)", "유이 (치비)": "Yui (chibi)", "미오": "Mio",
        "리츠": "Ritsu", "츠무기": "Tsumugi", "아즈사": "Azusa",
        # 메뉴 · 동작
        "펫 보이기": "Show pet", "설정…": "Settings…", "종료": "Quit",
        "손 흔들기": "Wave", "점프": "Jump", "벽 타 보기": "Climb a wall",
        "창 위로 올라가 보기": "Hop onto a window", "작업 목록 열기": "Open task list",
        "펫 바꾸기": "Change pet", "클릭하면": "On click",
        "앱 창 띄우기": "Bring up the app window", "한마디 하기": "Say something",
        "아무것도 안 함": "Do nothing",
        "자유롭게 돌아다니기": "Wander freely", "마우스 쳐다보기": "Follow the cursor",
        "대사": "Chat lines", "목소리": "Voice", "던지기": "Throwing",
        "창 위에 올라가기": "Climb onto windows", "벽 타기": "Climb walls",
        "클릭 통과": "Click-through", "뽀모도로 시작": "Start Pomodoro",
        "부팅 시 자동 실행": "Start with Windows",
        "크기": "Size", "투명도": "Opacity",
        # 음악
        "음악": "Music", "음악 폴더가 비어 있음": "Music folder is empty",
        "폴더 다시 훑기": "Rescan folders", "다시 훑기": "Rescan",
        "플레이어 열기…": "Open player…", "지금: ": "Now: ",
        "일시정지": "Pause", "재생": "Play", "다음 곡": "Next", "이전 곡": "Previous",
        "정지": "Stop", "무작위 순서": "Shuffle", "무작위": "Shuffle",
        "무엇을 틀까": "What to play", "음량": "Volume",
        "노래": "Songs", "반주": "Instrumental", "배경음악": "Soundtrack", "전부": "All",
        "곡·앨범 이름으로 찾기 (예: Cagayake / GO! / ふわふわ)":
            "Search by track or album (e.g. Cagayake / GO! / ふわふわ)",
        "%d곡 표시  ·  노래 %d · 반주 %d · 배경음악 %d  (전체 %d)":
            "%d shown  ·  songs %d · inst %d · OST %d  (total %d)",
        "노래 %d곡 찾았어~": "Found %d tracks~",
        "음악 폴더가 비었어~": "The music folder is empty~",
        # 작업 목록 · 상태
        "작업 %d개  ·  줄을 누르면 창 열기/내리기":
            "%d tasks  ·  click a row to raise or hide its window",
        "도는 작업이 없어요": "Nothing is running",
        "작업 중": "Working", "입력 대기": "Waiting", "실패": "Failed", "완료": "Done",
        "확인 필요": "Needs a look",
        "요청을 살펴보는 중": "Reading the request",
        "명령을 실행하는 중": "Running a command",
        "코드를 고치는 중": "Editing code",
        "자료를 검색하는 중": "Searching for information",
        "그림을 그리는 중": "Generating an image",
        "도구를 쓰는 중": "Using a tool",
        "이미지를 살펴보는 중": "Looking at an image",
        "확인을 기다리고 있어요": "Waiting for your go-ahead",
        "작업을 마쳤어요": "All done",
        "문제가 생겼어요": "Something went wrong",
        "파일을 살펴보는 중": "Reading a file",
        "파일을 작성하는 중": "Writing a file",
        "코드를 검색하는 중": "Searching the code",
        "파일을 찾는 중": "Looking for files",
        "웹 페이지를 읽는 중": "Reading a web page",
        "노트북을 손보는 중": "Editing a notebook",
        "물어볼 걸 정리하는 중": "Putting a question together",
        "할 일을 정리하는 중": "Updating the to-do list",
        "결과를 기다리는 중": "Waiting for a result",
        "브라우저를 보는 중": "Looking at the browser",
        "하위 작업을 맡기는 중": "Handing off a subtask",
        "하위 작업을 기다리는 중": "Waiting on a subtask",
        "하위 작업을 살피는 중": "Checking on subtasks",
        "할 일을 더 얹는 중": "Adding more to do",
        "하위 작업에 말을 거는 중": "Messaging a subtask",
        "하위 작업을 멈추는 중": "Stopping a subtask",
        "작업하는 중": "Working",
        "다음 단계를 준비하는 중": "Getting the next step ready",
        "%d초": "%ds", "%d분": "%dm", "%d시간 %d분": "%dh %dm",
        "%d분째": "%dm in", "%d시간 %d분째": "%dh %dm in",
        "  · 외 %d개": "  · +%d more", "%d개 작업 중": "%d tasks running",
        # 설정 창
        "일반": "General", "행동": "Behavior", "대사·목소리": "Talk & Voice",
        "작업 표시": "Work status", "언어": "Language",
        "바꾸면 바로 저장돼요": "Saved the moment you change it",
        "화면": "Screen", "시작": "Startup",
        "윈도우 켤 때 유이도 같이 켜져요": "Yui starts up with Windows",
        "펫": "Pet", "클릭 통과 (끄려면 트레이 메뉴에서)":
            "Click-through (turn it off from the tray menu)",
        "스스로 하는 행동": "On its own", "뽀모도로": "Pomodoro",
        "집중 시간(분)": "Focus (min)", "쉬는 시간(분)": "Break (min)",
        "일본어 원문 같이 보기": "Show the Japanese line too",
        "목소리 음량": "Voice volume",
        "날씨": "Weather", "날씨에 맞춘 대사": "Weather-aware lines",
        "재생 방식": "Playback",
        "위도": "Latitude", "경도": "Longitude",
        "음악 폴더": "Music folders", "폴더 추가…": "Add folder…", "빼기": "Remove",
        "고른 폴더 아래를 전부 훑어요": "Everything under the folder gets scanned",
        "음악 폴더 고르기": "Choose a music folder",
        "말풍선": "Speech bubble", "폭(px)": "Width (px)", "최대 줄 수": "Max lines",
        "완료 표시 시간(초)": "Keep 'done' for (sec)",
        "대화 내용 가리기": "Hide conversation text",
        "명령이나 질문 원문 대신 무엇을 하는 중인지만 보여줘요":
            "Shows what it is doing instead of the command or question itself",
        "Codex 기록 읽기": "Read Codex history",
        "훅을 안 걸어도 Codex 상태를 잡아줘요": "Picks up Codex status even without hooks",
        "닫기": "Close",
        "%d곡": "%d tracks", "음악 폴더를 아직 안 정했어요": "No music folder yet",
    },
    "ja": {
        "유이 펫": "ゆいペット", "설정": "設定", "유이 펫 — 음악": "ゆいペット — 音楽",
        "유이 펫 — %s %d:%02d 남음": "ゆいペット — %s 残り%d:%02d",
        "집중": "集中", "휴식": "休憩",
        "스프라이트를 읽지 못했어요": "スプライトを読み込めませんでした",
        "유이 (기본)": "唯（標準）", "유이 (치비)": "唯（ちび）", "미오": "澪",
        "리츠": "律", "츠무기": "紬", "아즈사": "梓",
        "펫 보이기": "ペットを表示", "설정…": "設定…", "종료": "終了",
        "손 흔들기": "手をふる", "점프": "ジャンプ", "벽 타 보기": "壁をのぼる",
        "창 위로 올라가 보기": "ウィンドウの上へ", "작업 목록 열기": "作業リストを開く",
        "펫 바꾸기": "ペットを変える", "클릭하면": "クリックしたら",
        "앱 창 띄우기": "アプリの窓を出す", "한마디 하기": "ひとこと言う",
        "아무것도 안 함": "何もしない",
        "자유롭게 돌아다니기": "自由に歩き回る", "마우스 쳐다보기": "カーソルを目で追う",
        "대사": "セリフ", "목소리": "ボイス", "던지기": "投げる",
        "창 위에 올라가기": "ウィンドウに登る", "벽 타기": "壁をのぼる",
        "클릭 통과": "クリックを通す", "뽀모도로 시작": "ポモドーロ開始",
        "부팅 시 자동 실행": "Windows起動時に開始",
        "크기": "大きさ", "투명도": "透明度",
        "음악": "音楽", "음악 폴더가 비어 있음": "音楽フォルダが空です",
        "폴더 다시 훑기": "フォルダを再スキャン", "다시 훑기": "再スキャン",
        "플레이어 열기…": "プレイヤーを開く…", "지금: ": "再生中: ",
        "일시정지": "一時停止", "재생": "再生", "다음 곡": "次の曲", "이전 곡": "前の曲",
        "정지": "停止", "무작위 순서": "シャッフル", "무작위": "シャッフル",
        "무엇을 틀까": "何をかける", "음량": "音量",
        "노래": "歌", "반주": "インスト", "배경음악": "サントラ", "전부": "すべて",
        "곡·앨범 이름으로 찾기 (예: Cagayake / GO! / ふわふわ)":
            "曲・アルバム名で検索（例: Cagayake / GO! / ふわふわ）",
        "%d곡 표시  ·  노래 %d · 반주 %d · 배경음악 %d  (전체 %d)":
            "%d曲表示  ·  歌 %d · インスト %d · サントラ %d  (全%d)",
        "노래 %d곡 찾았어~": "%d曲みつけたよ～",
        "음악 폴더가 비었어~": "音楽フォルダが空っぽだよ～",
        "작업 %d개  ·  줄을 누르면 창 열기/내리기":
            "作業%d件  ·  行を押すと窓を出す・しまう",
        "도는 작업이 없어요": "動いている作業はありません",
        "작업 중": "作業中", "입력 대기": "入力待ち", "실패": "失敗", "완료": "完了",
        "확인 필요": "確認が必要",
        "요청을 살펴보는 중": "リクエストを読んでいます",
        "명령을 실행하는 중": "コマンドを実行しています",
        "코드를 고치는 중": "コードを直しています",
        "자료를 검색하는 중": "調べものをしています",
        "그림을 그리는 중": "画像を作っています",
        "도구를 쓰는 중": "ツールを使っています",
        "이미지를 살펴보는 중": "画像を見ています",
        "확인을 기다리고 있어요": "確認を待っています",
        "작업을 마쳤어요": "作業が終わりました",
        "문제가 생겼어요": "問題が起きました",
        "파일을 살펴보는 중": "ファイルを読んでいます",
        "파일을 작성하는 중": "ファイルを書いています",
        "코드를 검색하는 중": "コードを検索しています",
        "파일을 찾는 중": "ファイルを探しています",
        "웹 페이지를 읽는 중": "ウェブページを読んでいます",
        "노트북을 손보는 중": "ノートブックを直しています",
        "물어볼 걸 정리하는 중": "質問をまとめています",
        "할 일을 정리하는 중": "やることを整理しています",
        "결과를 기다리는 중": "結果を待っています",
        "브라우저를 보는 중": "ブラウザを見ています",
        "하위 작업을 맡기는 중": "サブ作業をお願いしています",
        "하위 작업을 기다리는 중": "サブ作業を待っています",
        "하위 작업을 살피는 중": "サブ作業を見ています",
        "할 일을 더 얹는 중": "やることを追加しています",
        "하위 작업에 말을 거는 중": "サブ作業に話しかけています",
        "하위 작업을 멈추는 중": "サブ作業を止めています",
        "작업하는 중": "作業しています",
        "다음 단계를 준비하는 중": "次の準備をしています",
        "%d초": "%d秒", "%d분": "%d分", "%d시간 %d분": "%d時間%d分",
        "%d분째": "%d分経過", "%d시간 %d분째": "%d時間%d分経過",
        "  · 외 %d개": "  · ほか%d件", "%d개 작업 중": "%d件 作業中",
        "일반": "一般", "행동": "ふるまい", "대사·목소리": "セリフ・ボイス",
        "작업 표시": "作業表示", "언어": "言語",
        "바꾸면 바로 저장돼요": "変えたらすぐ保存されます",
        "화면": "画面", "시작": "起動",
        "윈도우 켤 때 유이도 같이 켜져요": "Windowsを起動すると唯も一緒に出てきます",
        "펫": "ペット", "클릭 통과 (끄려면 트레이 메뉴에서)":
            "クリックを通す（解除はトレイメニューから）",
        "스스로 하는 행동": "自分からするふるまい", "뽀모도로": "ポモドーロ",
        "집중 시간(분)": "集中（分）", "쉬는 시간(분)": "休憩（分）",
        "일본어 원문 같이 보기": "日本語の原文も表示",
        "목소리 음량": "ボイス音量",
        "날씨": "天気", "날씨에 맞춘 대사": "天気に合わせたセリフ",
        "재생 방식": "再生",
        "위도": "緯度", "경도": "経度",
        "음악 폴더": "音楽フォルダ", "폴더 추가…": "フォルダを追加…", "빼기": "外す",
        "고른 폴더 아래를 전부 훑어요": "選んだフォルダの下をすべて読み込みます",
        "음악 폴더 고르기": "音楽フォルダを選ぶ",
        "말풍선": "吹き出し", "폭(px)": "幅（px）", "최대 줄 수": "最大行数",
        "완료 표시 시간(초)": "完了表示の長さ（秒）",
        "대화 내용 가리기": "会話の中身を隠す",
        "명령이나 질문 원문 대신 무엇을 하는 중인지만 보여줘요":
            "コマンドや質問の原文ではなく「何をしているか」だけを表示します",
        "Codex 기록 읽기": "Codexの記録を読む",
        "훅을 안 걸어도 Codex 상태를 잡아줘요": "フックがなくてもCodexの状態を拾います",
        "닫기": "閉じる",
        "%d곡": "%d曲", "음악 폴더를 아직 안 정했어요": "音楽フォルダはまだ未設定です",
    },
}


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


# 폴더 id를 사람이 읽을 이름으로. 폴더명이 영문이라 pet.json의 displayName을 그대로
# 쓰면 "유이 (기본)" 옆에 "Nakano Azusa (azusa)"가 서는 식으로 뒤죽박죽이 된다.
# 목록에 세울 이름은 여기서 한국어로 정해 둔다.
PET_NAMES = {"": "유이 (기본)", "mio": "미오", "ritsu": "리츠",
             "tsumugi": "츠무기", "azusa": "아즈사",
             "chibi-yui": "유이 (치비)"}
# 목록에 세우는 차례 — 밴드 결성 순서대로 두고 옛 디자인을 뒤에 붙인다.
# 여기 없는 폴더는 이름순으로 맨 뒤에 붙는다(새 펫을 넣어도 목록에서 사라지지 않게).
PET_ORDER = ["", "mio", "ritsu", "tsumugi", "azusa", "chibi-yui"]


def pet_list():
    """[(id, 표시이름)] — 기본 펫 + BASE/pets/*/ 에 있는 것들.

    PET_ORDER 차례로 세우고, 거기 없는 폴더는 pet.json의 displayName에 폴더 이름을
    괄호로 붙여(둘 다 "유이"인 경우가 있다) 이름순으로 뒤에 붙인다.
    """
    found = []
    try:
        for d in sorted(os.listdir(os.path.join(BASE, "pets"))):
            if any(os.path.exists(os.path.join(BASE, "pets", d, n)) for n in SHEET_NAMES):
                found.append(d)
    except OSError:
        pass

    def label(pid):
        if pid in PET_NAMES:
            return T(PET_NAMES[pid])
        name = pid
        try:
            with open(os.path.join(BASE, "pets", pid, "pet.json"), encoding="utf-8") as f:
                name = json.load(f).get("displayName") or pid
        except Exception:
            pass
        return "%s (%s)" % (name, pid)

    out = [("", T(PET_NAMES[""]))]
    out += [(d, label(d)) for d in PET_ORDER if d and d in found]
    out += [(d, label(d)) for d in found if d not in PET_ORDER]
    return out


def load_lines(pet_id=""):
    """대사 목록. 펫별 lines.json이 있으면 그걸 먼저 쓴다.

    캐릭터마다 말투가 달라서 대사도 갈라야 한다. 펫 폴더에 없으면 공용을 쓰므로,
    대사를 따로 만들지 않은 펫은 지금까지처럼 공용 대사로 말한다.
    """
    path = os.path.join(BASE, "lines.json")
    cand = [path]
    if pet_id:
        cand.insert(0, os.path.join(BASE, "pets", pet_id, "lines.json"))
    for p in cand:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            continue
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_LINES, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return DEFAULT_LINES


def voice_dir(pet_id):
    """목소리 폴더. 펫별 폴더가 있으면 그걸 쓰고, 없으면 공용(BASE/voices)."""
    if pet_id:
        p = os.path.join(BASE, "pets", pet_id, "voices")
        if os.path.isdir(p):
            return p
    return os.path.join(BASE, "voices")


class VoicePlayer:
    """대사 음성 재생.

    QSoundEffect는 PCM wav만 받는 대신 지연 없이 바로 난다. 파일은 미리 물려 두고
    (setSource는 비동기라 첫 재생이 씹힌다) 재생할 때 볼륨만 얹는다.
    """
    MIN_GAP_S = 0.30            # 연타로 소리가 겹치지 않게 두는 최소 간격

    def __init__(self, cfg, pet_id=""):
        self.cfg = cfg
        self._effects = {}
        self._cur = None
        self._last = 0.0
        self.duck = None            # 음악을 잠시 낮출 콜백(MusicPlayer.duck)
        self.set_pet(pet_id)

    def set_pet(self, pet_id):
        """펫이 바뀌면 목소리 폴더도 따라간다."""
        self.dir = voice_dir(pet_id)
        self._effects.clear()
        self._cur = None
        self.preload()

    def available(self):
        return QSoundEffect is not None and os.path.isdir(self.dir)

    def preload(self):
        """폴더의 wav를 전부 물려 둔다. 40개 안팎이라 메모리는 몇 MB 수준이다."""
        if not self.available():
            return
        try:
            names = [n for n in os.listdir(self.dir) if n.lower().endswith(".wav")]
        except OSError:
            return
        for n in names:
            try:
                eff = QSoundEffect()
                eff.setSource(QtCore.QUrl.fromLocalFile(os.path.join(self.dir, n)))
                eff.playingChanged.connect(self._playing_changed)
                self._effects[n] = eff
            except Exception:
                logging.exception("voice load failed: %s", n)
        logging.info("voices loaded: %d from %s", len(self._effects), self.dir)

    def play(self, name):
        if not name or not self.cfg.get("voiceEnabled", True) or not self.available():
            return
        now = time.monotonic()
        if now - self._last < self.MIN_GAP_S:
            return
        eff = self._effects.get(name)
        if eff is None or eff.status() == QSoundEffect.Error:
            return
        self.stop()
        try:
            eff.setVolume(max(0.0, min(1.0, float(self.cfg.get("voiceVolume", 0.7)))))
            eff.play()
        except Exception:
            logging.exception("voice play failed: %s", name)
            return
        self._cur, self._last = eff, now
        if self.duck:                    # 음악이 흐르는 중이면 잠시 낮춘다
            self.duck(True)

    def _playing_changed(self):
        """목소리가 다 끝났으면 음악 음량을 되돌린다."""
        if not self.duck:
            return
        if not any(e.isPlaying() for e in self._effects.values()):
            self.duck(False)

    def stop(self):
        if self._cur is not None:
            try:
                if self._cur.isPlaying():
                    self._cur.stop()
            except Exception:
                pass


# 음악으로 받아들일 확장자. QMediaPlayer가 윈도우 코덱으로 재생한다.
MUSIC_EXT = (".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus", ".wma")
MUSIC_MAX = 800                 # 목록이 이보다 커지면 스캔을 멈춘다
MUSIC_DUCK = 0.3                # 목소리가 겹칠 때 음악을 이 배수로 낮춘다

# 노래·반주·배경음악을 섞어 틀면 곤란하다. 파일명 태그와 폴더 이름으로 갈라 놓는다.
MUSIC_KIND_LABEL = {"song": "노래", "inst": "반주", "bgm": "배경음악", "all": "전부"}
_RE_INST = re.compile(
    r"\[(instrumental|inst|off\s*vocal|karaoke|guitar|bass|drums?|keyboards?|piano)"
    r"[\s._-]*\d*\]|オフボーカル|カラオケ|インスト", re.I)
_RE_BGM = re.compile(r"original\s*soundtrack|\bO\.?S\.?T\b|サウンドトラック", re.I)


def track_kind(path):
    """곡을 노래 / 반주 / 배경음악으로 가른다.

    파일명 태그가 가장 확실하고(`[instrumental]`·`[guitar]`), 없으면 폴더 이름을 본다.
    밴드 스코어 앨범에는 파트별 트랙과 원곡이 섞여 있어서 폴더만으로는 못 가른다.
    """
    name = os.path.basename(path)
    if _RE_INST.search(name):
        return "inst"
    parent = os.path.dirname(path)
    for _ in range(3):                       # 앨범 → 분류 폴더까지 거슬러 본다
        base = os.path.basename(parent)
        if not base:
            break
        if _RE_BGM.search(base):
            return "bgm"
        parent = os.path.dirname(parent)
    return "song"


def default_music_dirs():
    """음악 폴더를 못 정해뒀을 때 훑어볼 자리들."""
    return [os.path.join(BASE, "music"),
            os.path.join(os.path.expanduser("~"), "Music")]


class MusicPlayer(QtCore.QObject):
    """배경 음악 재생. 목록은 폴더를 훑어 만들고, 곡이 끝나면 다음으로 넘어간다.

    목소리(QSoundEffect)와 달리 파일이 크고 형식이 다양해 QMediaPlayer를 쓴다.
    """

    def __init__(self, cfg, on_track=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_track = on_track        # 곡이 바뀔 때 알려줄 콜백
        self.tracks = []
        self.kinds = []                 # 트랙별 노래/반주/배경음악
        self.idx = -1
        self._order = []                # 셔플 순서(원본 인덱스 목록)
        self._opos = -1
        self._ducked = False
        self.player = None
        if QMediaPlayer is None:
            return
        self.out = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.out)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(
            lambda *a: logging.warning("music error: %s", self.player.errorString()))
        self.scan()
        self._apply_volume()

    # ---- 목록 ----
    def dirs(self):
        got = [d for d in (self.cfg.get("musicDirs") or []) if d]
        return got or default_music_dirs()

    def scan(self):
        found = []
        for d in self.dirs():
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                for n in sorted(files):
                    if n.lower().endswith(MUSIC_EXT):
                        found.append(os.path.join(root, n))
                        if len(found) >= MUSIC_MAX:
                            break
                if len(found) >= MUSIC_MAX:
                    break
        self.tracks = found
        self.kinds = [track_kind(p) for p in found]
        self._reorder()
        counts = {k: self.kinds.count(k) for k in ("song", "inst", "bgm")}
        logging.info("music: %d tracks %s from %s", len(found), counts, self.dirs())

    def filter(self):
        f = self.cfg.get("musicFilter", "song")
        return f if f in ("song", "inst", "bgm", "all") else "song"

    def set_filter(self, kind):
        self.cfg["musicFilter"] = kind
        self._reorder()

    def picked(self):
        """지금 필터에 걸리는 트랙 인덱스."""
        f = self.filter()
        return [i for i, k in enumerate(self.kinds) if f == "all" or k == f]

    def _reorder(self):
        self._order = self.picked()
        if not self._order:                   # 필터로 다 걸러졌으면 전부를 쓴다
            self._order = list(range(len(self.tracks)))
        if self.cfg.get("musicShuffle", True):
            random.shuffle(self._order)
        self._opos = -1

    # ---- 진행 위치 ----
    def position(self):
        return self.player.position() if self.player else 0

    def duration(self):
        return self.player.duration() if self.player else 0

    def seek(self, ms):
        if self.player:
            self.player.setPosition(int(ms))

    def available(self):
        return self.player is not None and bool(self.tracks)

    def playing(self):
        return (self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlayingState)

    def title(self):
        if 0 <= self.idx < len(self.tracks):
            return os.path.splitext(os.path.basename(self.tracks[self.idx]))[0]
        return ""

    # ---- 조작 ----
    def _apply_volume(self):
        if self.player is None:
            return
        v = max(0.0, min(1.0, float(self.cfg.get("musicVolume", 0.45))))
        self.out.setVolume(v * (MUSIC_DUCK if self._ducked else 1.0))

    def duck(self, on):
        if self._ducked != bool(on):
            self._ducked = bool(on)
            self._apply_volume()

    def play_at(self, i):
        if not self.available() or not (0 <= i < len(self.tracks)):
            return
        self.idx = i
        if i in self._order:
            self._opos = self._order.index(i)
        self.player.setSource(QtCore.QUrl.fromLocalFile(self.tracks[i]))
        self._apply_volume()
        self.player.play()
        if self.on_track:
            self.on_track(self.title())

    def step(self, d=1):
        if not self.available():
            return
        if not self._order:
            self._reorder()
        self._opos = (self._opos + d) % len(self._order)
        self.play_at(self._order[self._opos])

    def toggle(self):
        if not self.available():
            return
        if self.playing():
            self.player.pause()
        elif self.idx >= 0 and self.player.source().isValid():
            self.player.play()
        else:
            self.step(1)

    def stop(self):
        if self.player is not None:
            self.player.stop()

    def _on_status(self, st):
        if st == QMediaPlayer.EndOfMedia:      # 한 곡이 끝나면 다음 곡으로
            self.step(1)


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


def visible_rect(hwnd):
    """창의 보이는 경계. GetWindowRect는 드롭섀도까지 포함해 좌우가 7px쯤 넓다.

    그 값으로 발판을 잡으면 펫이 창 테두리 밖 허공까지 걸어간다. DWM이 알려주는
    확장 프레임 경계를 쓰고, 실패하면 GetWindowRect로 물러선다.
    """
    r = wintypes.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    try:
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(r), ctypes.sizeof(r))
        if hr == 0 and (r.right - r.left) > 0:
            return r
    except Exception:
        pass
    return r if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)) else None


def window_shelves(exclude, screen):
    """보이는 창들의 위쪽 모서리를 발판(선반)으로 모은다.

    화면을 통째로 덮는 창(바탕화면·전체화면)과 도구 창은 뺀다. 그것들의 위쪽은
    화면 맨 위라 발판으로 쓰면 펫이 허공에 서 있는 것처럼 보인다.
    """
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
    out = []

    def cb(hwnd, _):
        if hwnd == exclude or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if not user32.GetWindowTextLengthW(hwnd):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        r = visible_rect(hwnd)
        if r is None:
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < SHELF_MIN_W or h < SHELF_MIN_H:
            return True
        if r.top <= screen.top() + 30:          # 화면 위에 붙은 창(최대화 등)은 제외
            return True
        if r.top >= screen.bottom() - 60:       # 거의 화면 밖
            return True
        out.append({"hwnd": hwnd,
                    "left": max(r.left, screen.left()),
                    "right": min(r.right, screen.right()),
                    "top": r.top})
        return True

    user32.EnumWindows(proc(cb), 0)
    # 넓은 것부터. 좁은 발판은 뒤로 밀어 두면 올라갈 곳을 고를 때 자연스럽다
    out.sort(key=lambda s: s["right"] - s["left"], reverse=True)
    return out


def window_process(hwnd):
    """창을 띄운 프로그램의 실행 파일 이름. 못 알아내면 빈 문자열."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    # PROCESS_QUERY_LIMITED_INFORMATION — 권한 상승 없이 이름만 물어본다
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(h)


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT),
                ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT)]


def window_size(hwnd):
    """창을 펼쳤을 때의 크기. 접혀 있어도 원래 크기를 돌려준다."""
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    if ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        r = wp.rcNormalPosition
        return max(0, r.right - r.left), max(0, r.bottom - r.top)
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return max(0, r.right - r.left), max(0, r.bottom - r.top)


# 이보다 작으면 사람이 보는 창이 아니라고 본다(트레이·IME 같은 껍데기 창).
MIN_APP_WIN = (300, 200)


def find_windows_by_process(names):
    """이 실행 파일들이 띄운 진짜 창들. 제목이 뻔한 앱을 짚을 때 쓴다.

    Electron 앱은 트레이·IME·전원 감시용으로 160x28짜리 껍데기 창을 예닐곱 개 달고 다닌다.
    남의 창에 딸린 것(owner 있음)·도구 창·너무 작은 창을 걷어내고, 안 접힌 큰 창을 앞에 둔다.
    창을 닫아 트레이로 내려간 앱은 여기서 빈 목록이 나온다(껍데기를 올려 봐야 소용없다).
    """
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    want = {n.lower() for n in names}
    found = []

    def cb(hwnd, _):
        if not (user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd)):
            return True
        if user32.GetWindow(hwnd, 4):              # GW_OWNER — 딸린 창은 본체가 아니다
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x80:  # GWL_EXSTYLE & WS_EX_TOOLWINDOW
            return True
        if window_process(hwnd).lower() not in want:
            return True
        w, h = window_size(hwnd)
        if w < MIN_APP_WIN[0] or h < MIN_APP_WIN[1]:
            return True
        found.append((bool(user32.IsIconic(hwnd)), -(w * h), hwnd))
        return True

    user32.EnumWindows(proc(cb), 0)
    found.sort()                                   # 안 접힌 큰 창부터
    return [h for _, _, h in found]


def front_window():
    """펫 자신을 뺀, 지금 화면 맨 앞에 있는 진짜 창.

    `GetForegroundWindow()`를 쓰면 안 된다. 사용자가 펫을 누르는 순간 포그라운드가 펫으로
    넘어가서 "그 창이 앞에 있나"를 물어볼 수가 없다. 그래서 Z-순서를 위에서부터 훑어
    우리 창이 아닌 첫 창을 앞에 있는 창으로 본다.
    """
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    mine = kernel32.GetCurrentProcessId()
    hwnd = user32.GetTopWindow(0)
    while hwnd:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (pid.value != mine and user32.IsWindowVisible(hwnd)
                and not user32.IsIconic(hwnd)
                and user32.GetWindowTextLengthW(hwnd)
                and not user32.GetWindow(hwnd, 4)               # 딸린 창 제외
                and not user32.GetWindowLongW(hwnd, -20) & 0x80):  # 도구 창 제외
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.right - r.left) > 200 and (r.bottom - r.top) > 120:
                return hwnd
        hwnd = user32.GetWindow(hwnd, 2)                        # GW_HWNDNEXT
    return 0


def raise_window(hwnd):
    """가려져 있든 접혀 있든 앞으로 끌어온다.

    윈도우는 포그라운드가 아닌 프로세스의 SetForegroundWindow를 막는다. 펫 창은 클릭해도
    활성화되지 않게 만들어 놔서 그냥 부르면 작업표시줄만 깜빡인다. 그래서 지금 앞에 있는
    창의 입력 큐에 잠깐 붙었다가(AttachThreadInput) 올린다.
    """
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                 # SW_RESTORE
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other) and bool(user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        # 첫 요청이 한 번 미끄러지는 앱이 있다(Electron 계열에서 봤다). 한 번 더 밀어 준다.
        if user32.GetForegroundWindow() != hwnd:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)


# 소스별로 열어 줄 앱. Codex 데스크톱의 창은 제목이 그냥 "ChatGPT"라 제목으로는
# 못 짚는다(브라우저 창과 헷갈린다). 그래서 실행 파일 이름으로 찾는다.
SOURCE_APP = {"codex": ("ChatGPT.exe", "Codex.exe")}


def toggle_window(match=None, source=""):
    """맞는 창을 토글한다. 앞에 나와 있으면 내리고, 아니면 끌어올린다.

    세션마다 창이 따로 있는 게 아니라(터미널 여러 개가 편집기 창 하나를 쓴다)
    소스에 딸린 앱이 있으면 그 앱 창을 먼저 짚고, 없으면 제목이 맞는 창, 그것도 없으면
    편집기 창으로 떨어진다. Codex 데스크톱처럼 제목이 뻔한 앱은 제목으로 찾으면 엉뚱한
    창(브라우저 등)을 집기 때문에 앱을 먼저 본다.

    '접혀 있나'가 아니라 '지금 앞에 있나'로 판단한다. 창이 떠 있어도 다른 창에 가려져
    있으면 눌렀을 때 올라와야지, 내려가면 안 된다. 앞에 있는지는 `front_window()`로 본다
    (누르는 순간 포그라운드가 펫으로 넘어가서 GetForegroundWindow는 못 쓴다).
    """
    user32 = ctypes.windll.user32
    if source in SOURCE_APP:
        # 제 앱이 있는 소스는 그 앱만 본다. 창을 닫아 트레이로 내려가 있으면 아무것도 안 한다.
        # 여기서 편집기로 떨어지면 Codex 줄을 눌렀는데 VS Code가 내려가는 꼴이 된다.
        found = find_windows_by_process(SOURCE_APP[source])
    else:
        found = (find_windows(match) if match else []) or find_windows()
    if not found:
        return False
    hwnd = found[0]
    if hwnd == front_window():
        user32.ShowWindow(hwnd, 6)                 # SW_MINIMIZE
    else:
        raise_window(hwnd)
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


def _assistant_text(d):
    """대화 기록 한 줄에서 '공개 assistant 텍스트'만 꺼낸다. 없으면 빈 문자열.

    클로드와 Codex는 기록 형식이 다르다. 어느 쪽이든 사람에게 보여 준 말만 집고,
    생각(reasoning)·도구 호출은 건드리지 않는다.
      클로드 : {"type":"assistant","message":{"content":[{"type":"text","text":…}]}}
      Codex  : {"type":"event_msg","payload":{"type":"agent_message","message":…}}
               {"type":"response_item","payload":{"type":"message","role":"assistant",
                                                  "content":[{"type":"output_text","text":…}]}}
    """
    if d.get("type") == "assistant":                       # 클로드
        body = d.get("message") or {}
    else:                                                  # Codex
        body = d.get("payload") or {}
        if not isinstance(body, dict):
            return ""
        kind = body.get("type")
        if kind == "agent_message":
            return (body.get("message") or "").strip()
        if kind != "message" or body.get("role") != "assistant":
            return ""
    content = body.get("content")
    if not isinstance(content, list):
        return ""
    out = ""
    for c in content:
        if isinstance(c, dict) and c.get("type") in ("text", "output_text") \
                and (c.get("text") or "").strip():
            out = c["text"]
    return out.strip()


def elapsed_text(started_ns, short=False):
    """작업 시작 이후 경과. 말풍선은 1분이 넘어야 표시하고, 목록 패널은 초부터 보여준다."""
    if not started_ns:
        return ""
    sec = int((time.time_ns() - started_ns) / 1_000_000_000)
    if sec < 0:
        return ""
    if sec < 60:
        return "" if not short else T("%d초") % sec
    m, h = sec // 60, sec // 3600
    if h:
        return (T("%d시간 %d분") if short else T("%d시간 %d분째")) % (h, m - h * 60)
    return (T("%d분") if short else T("%d분째")) % m


# ---- Codex 상태 읽기 -------------------------------------------------------
# Codex는 훅을 걸어도 '검토 후 승인'을 받기 전에는 명령을 실행하지 않고, 데스크톱판은
# 그 승인 화면이 없어 훅이 영영 안 돈다. 그래서 Codex가 스스로 남기는 대화 기록
# (rollout-*.jsonl)을 직접 읽어 상태를 만든다. Codex 쪽 설정이 필요 없고 데스크톱·CLI가
# 똑같이 잡힌다. 훅이 도는 환경이면 sessions/codex/ 기록이 우선한다.

# 기록에 찍히는 이벤트 → (단계, 말풍선 문구). 여기 없는 이벤트는 상태를 바꾸지 않는다.
# 문구가 빈 칸이면 단계만 바꾸고 하던 말은 그대로 둔다.
# (실제 기록을 세어 보고 맞췄다. 데스크톱은 도구를 exec_command_begin 이 아니라
#  custom_tool_call 로 남기고, 턴 경계만 task_started·task_complete 로 남긴다.)
CODEX_EVENT = {
    "user_message":                ("working", "요청을 살펴보는 중"),
    "task_started":                ("working", "요청을 살펴보는 중"),
    "exec_command_begin":          ("working", "명령을 실행하는 중"),
    "patch_apply_begin":           ("working", "코드를 고치는 중"),
    "web_search_begin":            ("working", "자료를 검색하는 중"),
    "image_generation_begin":      ("working", "그림을 그리는 중"),
    "image_generation_end":        ("working", ""),
    "mcp_tool_call_begin":         ("working", "도구를 쓰는 중"),
    "view_image_tool_call":        ("working", "이미지를 살펴보는 중"),
    "agent_message":               ("working", ""),
    "exec_approval_request":       ("waiting", "확인을 기다리고 있어요"),
    "apply_patch_approval_request": ("waiting", "확인을 기다리고 있어요"),
    "request_user_input":          ("waiting", "확인을 기다리고 있어요"),
    "elicitation_request":         ("waiting", "확인을 기다리고 있어요"),
    "task_complete":               ("done",    "작업을 마쳤어요"),
    "turn_aborted":                ("idle",    ""),
    "stream_error":                ("failed",  "문제가 생겼어요"),
}
# 도구 호출(custom_tool_call·function_call)의 이름 → 문구.
CODEX_TOOL = {
    "exec": "명령을 실행하는 중", "shell": "명령을 실행하는 중",
    "apply_patch": "코드를 고치는 중", "read_file": "파일을 살펴보는 중",
    "update_plan": "할 일을 정리하는 중", "web_search": "자료를 검색하는 중",
    "view_image": "이미지를 살펴보는 중", "image_generation": "그림을 그리는 중",
    "wait": "결과를 기다리는 중", "browser": "브라우저를 보는 중",
    # 여러 에이전트를 굴릴 때 나오는 것들
    "spawn_agent": "하위 작업을 맡기는 중", "wait_agent": "하위 작업을 기다리는 중",
    "list_agents": "하위 작업을 살피는 중", "followup_task": "할 일을 더 얹는 중",
    "send_message": "하위 작업에 말을 거는 중", "interrupt_agent": "하위 작업을 멈추는 중",
}
_codex_cache = {}                  # 경로 → (크기, mtime, 결과 dict)


def codex_homes(cfg):
    """볼 Codex 홈 목록. 설정이 없으면 이 계정의 홈 하나를 본다."""
    homes = cfg.get("codexHomes")
    if homes:
        return [h for h in homes if h]
    return [os.path.join(os.path.expanduser("~"), ".codex")]


def _iso_ns(ts):
    """rollout의 ISO8601(UTC) 시각을 ns로. 실패하면 0."""
    try:
        t = ts.replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(t).timestamp() * 1_000_000_000)
    except (ValueError, AttributeError):
        return 0


# Codex 데스크톱이 자기 작업 폴더를 만들 때 붙이는 경로 꼬리표.
# 예: hatch-pet-c-users-alice-codex → hatch-pet
_CODEX_SLUG_TAIL = re.compile(r"-(?:[a-z]-)?(?:users|home|mnt)-.*$")


_codex_origin_cache = {}


def codex_app(transcript):
    """이 Codex 세션을 누가 띄웠나 보고, 눌렀을 때 열어 줄 앱을 정한다.

    데스크톱에서 돈 세션만 Codex 앱 창을 갖는다. 터미널(codex-tui·exec)에서 돌린 것은
    앱 창이 없으니 평소처럼 편집기·터미널 창으로 가야 한다. 안 그러면 눌러도 아무 일도
    안 일어난다. 기록 첫 줄만 보면 되고, 경로마다 한 번만 읽어 둔다.
    """
    if not transcript:
        return ""
    hit = _codex_origin_cache.get(transcript)
    if hit is None:
        try:
            with open(transcript, encoding="utf-8", errors="replace") as f:
                payload = json.loads(f.readline()).get("payload") or {}
            hit = (payload.get("originator") or "").strip()
        except (OSError, ValueError):
            hit = ""
        if len(_codex_origin_cache) > 200:
            _codex_origin_cache.clear()
        _codex_origin_cache[transcript] = hit
    return "codex" if hit == "Codex Desktop" else ""


def _codex_meta(path, aliases):
    """기록 첫 줄(session_meta)에서 짧은 이름과 부모 스레드를 뽑는다.

    Codex가 스레드마다 별명(agent_nickname: Singer·Feynman…)을 붙여 주므로 그게 있으면
    그대로 쓴다. 없으면(주 스레드) 작업 폴더 이름을 쓰되, 데스크톱이 자동으로 만든
    폴더는 뒤에 경로를 슬러그로 붙여 놔서 그 꼬리를 떼고 앞부분만 남긴다.
    하위 에이전트는 `parent_thread_id`가 있어서 목록에서 부모 밑에 붙일 수 있다.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            payload = json.loads(f.readline()).get("payload") or {}
    except (OSError, ValueError):
        return "", ""
    parent = (payload.get("parent_thread_id") or "").strip()
    nick = (payload.get("agent_nickname") or "").strip()
    if nick:
        return nick, parent
    cwd = (payload.get("cwd") or "").replace("\\\\?\\", "")
    name = os.path.basename(cwd.replace("\\", "/").rstrip("/"))
    if name in aliases:
        return aliases[name], parent
    short = _CODEX_SLUG_TAIL.sub("", name)
    return aliases.get(short, short or name), parent


def group_sessions(rows):
    """하위 에이전트를 부모 세션 바로 밑으로 모으고 `depth`를 매긴다.

    부모가 목록에 없으면(먼저 끝났거나 오래돼 빠졌으면) 그냥 제자리에 둔다.
    원래 순서(우선순위·최신순)는 부모들 사이에서 그대로 지킨다.
    """
    have = {r.get("session_id") for r in rows if r.get("session_id")}
    kids = {}
    for r in rows:
        p = r.get("parent")
        if p and p in have and p != r.get("session_id"):
            kids.setdefault(p, []).append(r)
    out = []
    for r in rows:
        p = r.get("parent")
        if p and p in have and p != r.get("session_id"):
            continue                              # 부모 밑에서 다시 낸다
        r["depth"] = 0
        out.append(r)
        for kid in kids.get(r.get("session_id"), []):
            kid["depth"] = 1
            out.append(kid)
    return out


def _read_codex_rollout(path, aliases):
    """파일 하나를 읽어 PetState 한 줄로. 크기·수정시각이 그대로면 캐시를 쓴다."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_size, st.st_mtime_ns)
    hit = _codex_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]

    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 200000))
            chunk = f.read().decode("utf-8", "ignore")
    except OSError:
        return None

    title, parent = _codex_meta(path, aliases)
    phase, detail, started, last_ts = "idle", "", 0, 0
    for line in chunk.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue                      # 앞쪽이 잘린 첫 줄
        payload = d.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        if kind in ("custom_tool_call", "function_call"):
            step = ("working", CODEX_TOOL.get(payload.get("name"), "작업하는 중"))
        elif kind in ("custom_tool_call_output", "function_call_output"):
            step = ("working", "")          # 도구가 끝났을 뿐, 하던 말은 그대로 둔다
        else:
            step = CODEX_EVENT.get(kind)
        if not step:
            continue
        ns = _iso_ns(d.get("timestamp", ""))
        last_ts = ns or last_ts
        phase, new_detail = step
        if new_detail:
            detail = new_detail
        if kind in ("task_started", "user_message"):
            started = ns
        elif phase != "working":
            started = 0

    if phase == "idle":
        row = None
    else:
        # 마지막으로 알아본 이벤트 시각과 파일이 커진 시각 중 늦은 쪽을 활동 시각으로 본다.
        # 한참 떠드는 중이라 우리가 아는 이벤트가 안 나오는 구간에서도 살아 있게 보인다.
        row = {"phase": phase, "title": title, "detail": detail, "parent": parent,
               "app": codex_app(path),
               "ts": max(last_ts, st.st_mtime_ns), "started": started if phase == "working" else 0,
               "transcript": path, "source": "codex",
               # 파일 이름은 rollout-<시각>-<세션id>.jsonl 이다. 훅이 도는 환경에서
               # 같은 세션을 두 번 세지 않도록 세션 id를 똑같이 맞춰 둔다.
               "session_id": os.path.basename(path)[:-6][-36:]}
    _codex_cache[path] = (key, row)
    if len(_codex_cache) > 200:           # 오래된 항목이 쌓이지 않게
        for k in list(_codex_cache)[:100]:
            _codex_cache.pop(k, None)
    return row


def codex_rows(cfg):
    """Codex 홈들에서 최근에 움직인 기록만 골라 PetState 목록으로."""
    rows = []
    now = time.time_ns()
    aliases = cfg.get("projectAliases") or {}
    today = datetime.date.today()
    for home in codex_homes(cfg):
        base = os.path.join(home, "sessions")
        # 날짜 폴더(YYYY/MM/DD)라 오늘과 어제만 보면 충분하다(자정 넘긴 작업 대비).
        for delta in (0, 1):
            day = today - datetime.timedelta(days=delta)
            d = os.path.join(base, "%04d" % day.year, "%02d" % day.month, "%02d" % day.day)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for fn in names:
                if not (fn.startswith("rollout-") and fn.endswith(".jsonl")):
                    continue
                p = os.path.join(d, fn)
                try:
                    if now - os.stat(p).st_mtime_ns > STALE_NS:
                        continue
                except OSError:
                    continue
                row = _read_codex_rollout(p, aliases)
                if not row:
                    continue
                # 완료·실패는 훅 쪽과 같은 감각으로 잠깐만 띄우고 내린다.
                keep = {"done": 4, "failed": 8}.get(row["phase"])
                if keep and now - row["ts"] > keep * 1_000_000_000:
                    continue
                rows.append(row)
    return rows


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
            "QLabel{background:transparent;font-family:'Pretendard Variable','Pretendard','Noto Sans KR','맑은 고딕','Malgun Gothic','Yu Gothic UI','Meiryo';line-height:150%;}")
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
        # 훅·Codex 기록이 남긴 상태 문구는 한국어다. 표에 있으면 지금 언어로 바꾸고,
        # 프로젝트 이름처럼 표에 없는 것은 그대로 나간다.
        if phase != "say":
            title, detail = T(title or ""), T(detail or "")
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
      font-family:'Pretendard Variable','Pretendard','Noto Sans KR','맑은 고딕','Malgun Gothic','Yu Gothic UI','Meiryo';font-size:12px;color:#2c2c33;}
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

    kind="size"는 표시 높이를, kind="opacity"는 불투명도를, kind="voice"는 음량을 조절한다.
    """
    CAPTION = {"size": "크기", "opacity": "투명도", "voice": "목소리", "music": "노래"}

    def __init__(self, parent, pet, kind="size"):
        super().__init__(parent)
        self.pet = pet
        self.kind = kind
        box = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(box)
        lay.setContentsMargins(16, 4, 16, 8)
        lay.setSpacing(10)

        cap = QtWidgets.QLabel(T(self.CAPTION.get(kind, kind)))
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
        elif kind == "voice":
            self.slider.setMinimum(0)
            self.slider.setMaximum(100)
            self.slider.setValue(int(round(float(pet.cfg.get("voiceVolume", 0.7)) * 100)))
            self.slider.setEnabled(pet.voice.available())
            self.slider.sliderReleased.connect(self._voice_released)
        elif kind == "music":
            self.slider.setMinimum(0)
            self.slider.setMaximum(100)
            self.slider.setValue(int(round(float(pet.cfg.get("musicVolume", 0.45)) * 100)))
            self.slider.sliderReleased.connect(
                lambda: self.pet._save_cfg({"musicVolume": self.slider.value() / 100.0}))
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

    def _voice_released(self):
        """놓을 때 저장하고, 지금 정한 음량을 한 번 들려준다."""
        vol = self.slider.value() / 100.0
        self.pet._save_cfg({"voiceVolume": vol})
        if vol > 0:
            self.pet._say_line("petted", force=True)

    def _sync_label(self, v):
        self.val.setText(f"{int(round(LOGICAL_H * v / 100))}px" if self.kind == "size"
                         else f"{v}%")

    def _changed(self, v):
        self._sync_label(v)
        if self.kind == "size":
            self.pet.set_scale(v / 100.0)
        elif self.kind == "voice":
            self.pet.cfg["voiceVolume"] = v / 100.0
        elif self.kind == "music":
            self.pet.cfg["musicVolume"] = v / 100.0
            self.pet.music._apply_volume()      # 끌면서 바로 들리게
        else:
            self.pet.cfg["opacity"] = v / 100.0
            self.pet._apply_opacity()


PLAYLIST_QSS = """
QWidget{background:#fbfbfd;color:#2c2c33;font-size:13px;}
QLineEdit{border:1px solid #dcdce4;border-radius:8px;padding:7px 11px;font-size:14px;
          background:#ffffff;}
QLineEdit:focus{border-color:#8b7cf6;}
QListWidget{border:1px solid #e6e6ee;border-radius:8px;background:#ffffff;
            outline:none;padding:4px;}
QListWidget::item{padding:6px 9px;border-radius:6px;}
QListWidget::item:selected{background:#eceaff;color:#3a2fa8;}
QListWidget::item:hover{background:#f4f2ff;}
QLabel#hint{color:#8b8b95;font-size:11px;}
QLabel#now{font-size:15px;font-weight:600;color:#2a2a31;}
QPushButton{border:1px solid #dcdce4;border-radius:7px;padding:5px 12px;background:#fff;}
QPushButton:hover{background:#f2f2f7;}
QPushButton#ctl{font-size:15px;padding:6px 0;}
QPushButton#kind:checked, QPushButton#ctl:checked{background:#8b7cf6;color:#fff;
                                                  border-color:#8b7cf6;}
QPushButton:checked{background:#8b7cf6;color:#fff;border-color:#8b7cf6;}
QSlider::groove:horizontal{height:4px;background:#e6e6ee;border-radius:2px;}
QSlider::sub-page:horizontal{background:#8b7cf6;border-radius:2px;}
QSlider::handle:horizontal{width:13px;height:13px;margin:-5px 0;border-radius:7px;
                           background:#fff;border:1.5px solid #8b7cf6;}
QSlider::handle:horizontal:hover{background:#f4f2ff;}
"""


def album_of(path):
    """곡이 속한 앨범 이름. 'Disc 1', 'Disc 2 Live Mix' 같은 하위 폴더면 그 위를 쓴다."""
    d = os.path.dirname(path)
    name = os.path.basename(d)
    if re.match(r"(disc|cd|vol)[\s._-]*\d+", name, re.I) or name.isdigit():
        name = os.path.basename(os.path.dirname(d)) or name
    # '[2009.04.22] けいおん! | Cagayake!GIRLS' 처럼 앞에 붙은 날짜 태그는 떼어낸다
    return re.sub(r"^\[[^\]]*\]\s*", "", name)


def ms_text(ms):
    s = max(0, int(ms // 1000))
    return "%d:%02d" % (s // 60, s % 60)


class PlaylistWindow(QtWidgets.QWidget):
    """음악 플레이어. 곡이 수백 개라 메뉴로는 못 찾으니 버튼과 검색을 한자리에 둔다."""

    KINDS = (("song", "노래"), ("inst", "반주"), ("bgm", "배경음악"), ("all", "전부"))

    def __init__(self, pet):
        super().__init__(None, QtCore.Qt.Tool)
        self.pet = pet
        self.setWindowTitle(T("유이 펫 — 음악"))
        self.setStyleSheet(PLAYLIST_QSS)
        self.resize(520, 620)
        self._seeking = False

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(9)

        # ── 지금 나오는 곡 ──
        self.now = QtWidgets.QLabel("—")
        self.now.setObjectName("now")
        self.now.setWordWrap(False)
        lay.addWidget(self.now)
        self.album = QtWidgets.QLabel("")
        self.album.setObjectName("hint")
        lay.addWidget(self.album)

        # ── 진행 바 ──
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(8)
        self.t_pos = QtWidgets.QLabel("0:00")
        self.t_pos.setObjectName("hint")
        self.seek = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_done)
        self.t_dur = QtWidgets.QLabel("0:00")
        self.t_dur.setObjectName("hint")
        bar.addWidget(self.t_pos)
        bar.addWidget(self.seek, 1)
        bar.addWidget(self.t_dur)
        lay.addLayout(bar)

        # ── 조작 버튼 ──
        ctl = QtWidgets.QHBoxLayout()
        ctl.setSpacing(6)
        self.b_prev = QtWidgets.QPushButton("⏮")
        self.b_play = QtWidgets.QPushButton("▶")
        self.b_next = QtWidgets.QPushButton("⏭")
        self.b_stop = QtWidgets.QPushButton("■")
        for b in (self.b_prev, self.b_play, self.b_next, self.b_stop):
            b.setObjectName("ctl")
            b.setFixedWidth(46)
            ctl.addWidget(b)
        self.b_prev.clicked.connect(lambda: (self.pet.music.step(-1), self.refresh()))
        self.b_next.clicked.connect(lambda: (self.pet.music.step(1), self.refresh()))
        self.b_play.clicked.connect(lambda: (self.pet.music.toggle(), self.refresh()))
        self.b_stop.clicked.connect(lambda: (self.pet.music.stop(), self.refresh()))

        self.b_shuffle = QtWidgets.QPushButton(T("무작위"))
        self.b_shuffle.setCheckable(True)
        self.b_shuffle.setChecked(bool(pet.cfg.get("musicShuffle", True)))
        self.b_shuffle.clicked.connect(self._toggle_shuffle)
        ctl.addWidget(self.b_shuffle)

        ctl.addSpacing(8)
        vol_cap = QtWidgets.QLabel(T("음량"))
        vol_cap.setObjectName("hint")
        ctl.addWidget(vol_cap)
        self.vol = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(110)
        self.vol.setValue(int(round(float(pet.cfg.get("musicVolume", 0.45)) * 100)))
        self.vol.valueChanged.connect(self._vol_changed)
        self.vol.sliderReleased.connect(
            lambda: self.pet._save_cfg({"musicVolume": self.vol.value() / 100.0}))
        ctl.addWidget(self.vol)
        lay.addLayout(ctl)

        # ── 종류 고르기 ──
        kinds = QtWidgets.QHBoxLayout()
        kinds.setSpacing(6)
        self.kind_btns = {}
        cur_kind = pet.music.filter()
        for key, label in self.KINDS:
            b = QtWidgets.QPushButton(T(label))
            b.setCheckable(True)
            b.setChecked(key == cur_kind)
            b.setObjectName("kind")
            b.clicked.connect(lambda _=False, k=key: self._set_kind(k))
            self.kind_btns[key] = b
            kinds.addWidget(b)
        kinds.addStretch(1)
        b_scan = QtWidgets.QPushButton(T("다시 훑기"))
        b_scan.clicked.connect(lambda: (self.pet._music_rescan(), self.refresh()))
        kinds.addWidget(b_scan)
        lay.addLayout(kinds)

        # ── 검색 · 목록 ──
        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText(T("곡·앨범 이름으로 찾기 (예: Cagayake / GO! / ふわふわ)"))
        self.q.textChanged.connect(self._apply_search)
        self.q.returnPressed.connect(self._play_current)
        lay.addWidget(self.q)

        self.list = QtWidgets.QListWidget()
        self.list.itemActivated.connect(lambda _: self._play_current())
        self.list.itemDoubleClicked.connect(lambda _: self._play_current())
        # 긴 제목은 잘라서 보여준다. 가로 스크롤이 생기면 목록을 훑기 불편하다
        self.list.setTextElideMode(QtCore.Qt.ElideRight)
        self.list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(False)
        lay.addWidget(self.list, 1)

        self.hint = QtWidgets.QLabel()
        self.hint.setObjectName("hint")
        lay.addWidget(self.hint)

        # 상태는 폴링으로 맞춘다. 시그널을 여러 개 잇는 것보다 흐름이 단순하다
        self.tick = QtCore.QTimer(self)
        self.tick.timeout.connect(self._sync)
        self.tick.start(400)

    # ---- 조작 ----
    def _toggle_shuffle(self):
        self.pet._set_shuffle(self.b_shuffle.isChecked())

    def _vol_changed(self, v):
        self.pet.cfg["musicVolume"] = v / 100.0
        self.pet.music._apply_volume()

    def _set_kind(self, kind):
        for k, b in self.kind_btns.items():
            b.setChecked(k == kind)
        self.pet.set_option("musicFilter", kind)
        self.refresh()

    def _seek_done(self):
        self._seeking = False
        dur = self.pet.music.duration()
        if dur > 0:
            self.pet.music.seek(dur * self.seek.value() / 1000.0)

    # ---- 표시 ----
    def _sync(self):
        """재생 상태·진행 위치를 주기적으로 UI에 반영한다."""
        m = self.pet.music
        self.b_play.setText("⏸" if m.playing() else "▶")
        title = m.title()
        if title:
            kind = m.kinds[m.idx] if 0 <= m.idx < len(m.kinds) else ""
            tag = T(MUSIC_KIND_LABEL.get(kind, ""))
            self.now.setText(("[%s] " % tag if tag else "") + title)
            self.album.setText(album_of(m.tracks[m.idx]) if 0 <= m.idx else "")
        else:
            self.now.setText("—")
            self.album.setText("")
        dur, pos = m.duration(), m.position()
        self.t_dur.setText(ms_text(dur))
        self.t_pos.setText(ms_text(pos))
        if not self._seeking:
            self.seek.setValue(int(pos * 1000 / dur) if dur > 0 else 0)

    def refresh(self):
        self._fill()
        self._apply_search(self.q.text())
        self._sync()

    def _fill(self):
        m = self.pet.music
        self.list.clear()
        for i, path in enumerate(m.tracks):
            name = os.path.splitext(os.path.basename(path))[0]
            album = album_of(path)
            kind = m.kinds[i] if i < len(m.kinds) else "song"
            # 앨범명까지 검색 대상이라, 곡명만 보이면 왜 걸렸는지 알 수 없다
            it = QtWidgets.QListWidgetItem(
                ("▶  " if i == m.idx else "     ")
                + name + ("    · " + album[:24] if album else ""))
            it.setToolTip("%s\n%s\n%s" % (T(MUSIC_KIND_LABEL.get(kind, "")), album, path))
            it.setData(QtCore.Qt.UserRole, i)
            it.setData(QtCore.Qt.UserRole + 1, (name + " " + album).lower())
            it.setData(QtCore.Qt.UserRole + 2, kind)
            self.list.addItem(it)

    def _apply_search(self, text):
        # 띄어쓰기로 나눈 조각이 모두 들어 있으면 통과 — 앨범명 일부만 알아도 찾힌다
        parts = [p for p in text.lower().split() if p]
        want = self.pet.music.filter()
        shown = 0
        first = None
        for r in range(self.list.count()):
            it = self.list.item(r)
            hay = it.data(QtCore.Qt.UserRole + 1) or ""
            ok = all(p in hay for p in parts) and \
                (want == "all" or it.data(QtCore.Qt.UserRole + 2) == want)
            it.setHidden(not ok)
            if ok:
                shown += 1
                if first is None:
                    first = r
                if it.data(QtCore.Qt.UserRole) == self.pet.music.idx:
                    self.list.setCurrentRow(r)
                    self.list.scrollToItem(it)
        if self.list.currentRow() < 0 or self.list.currentItem().isHidden():
            if first is not None:
                self.list.setCurrentRow(first)
        m = self.pet.music
        counts = {k: m.kinds.count(k) for k in ("song", "inst", "bgm")}
        self.hint.setText(
            T("%d곡 표시  ·  노래 %d · 반주 %d · 배경음악 %d  (전체 %d)")
            % (shown, counts["song"], counts["inst"], counts["bgm"], len(m.tracks)))

    def _play_current(self):
        it = self.list.currentItem()
        if it is None or it.isHidden():
            for r in range(self.list.count()):
                if not self.list.item(r).isHidden():
                    it = self.list.item(r)
                    break
        if it is None:
            return
        self.pet.music.play_at(int(it.data(QtCore.Qt.UserRole)))
        self.refresh()

    def show_near_pet(self):
        self.refresh()
        scr = self.pet._screen()
        g = self.pet.frameGeometry()
        x = min(max(scr.left() + 8, g.center().x() - self.width() // 2),
                scr.right() - self.width() - 8)
        y = min(max(scr.top() + 8, g.top() - self.height() - 10),
                scr.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.q.setFocus()
        self.q.selectAll()


_SETTINGS_QSS = """
QWidget{background:#fbfbfd;color:#2c2c33;font-size:13px;
        font-family:'Pretendard Variable','Pretendard','Noto Sans KR','맑은 고딕','Malgun Gothic','Yu Gothic UI','Meiryo';}
QListWidget#nav{background:#f2f2f6;border:none;border-right:1px solid #e6e6ee;
                outline:none;padding:12px 8px;}
QListWidget#nav::item{padding:9px 12px;border-radius:8px;color:#5a5a63;}
QListWidget#nav::item:selected{background:#8b7cf6;color:#ffffff;}
QListWidget#nav::item:hover:!selected{background:#e9e7fb;}
QLabel#group{color:#8b8b95;font-size:11px;font-weight:700;letter-spacing:0.6px;}
QLabel#hint{color:#8b8b95;font-size:11px;}
QLabel#foot{color:#a0a0aa;font-size:11px;}
QCheckBox{spacing:9px;padding:2px 0;}
QCheckBox::indicator{width:17px;height:17px;border-radius:5px;
                     border:1.5px solid #cfcfda;background:#ffffff;}
QCheckBox::indicator:hover{border-color:#b3a9f2;}
QCheckBox::indicator:checked{background:#8b7cf6;border-color:#8b7cf6;image:url(%s);}
QCheckBox::indicator:disabled{background:#ececf1;border-color:#dedee6;}
QCheckBox:disabled{color:#b4b4bd;}
QComboBox,QSpinBox,QDoubleSpinBox{border:1px solid #dcdce4;border-radius:7px;
                                  padding:5px 9px;background:#ffffff;}
QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus{border-color:#8b7cf6;}
QComboBox QAbstractItemView{border:1px solid #e0e0e8;background:#ffffff;outline:none;
                            selection-background-color:#eceaff;selection-color:#3a2fa8;}
QPushButton{border:1px solid #dcdce4;border-radius:7px;padding:5px 13px;background:#ffffff;}
QPushButton:hover{background:#f2f2f7;}
QListWidget#dirs{border:1px solid #e6e6ee;border-radius:8px;background:#ffffff;padding:3px;}
QListWidget#dirs::item{padding:4px 7px;border-radius:5px;}
QListWidget#dirs::item:selected{background:#eceaff;color:#3a2fa8;}
QScrollArea{border:none;}
QSlider::groove:horizontal{height:4px;background:#e6e6ee;border-radius:2px;}
QSlider::sub-page:horizontal{background:#8b7cf6;border-radius:2px;}
QSlider::handle:horizontal{width:13px;height:13px;margin:-5px 0;border-radius:7px;
                           background:#ffffff;border:1.5px solid #8b7cf6;}
"""


def check_mark_path():
    """체크박스 안에 그릴 체크 표시. 스타일시트는 그림 파일만 받으므로 없으면 만들어 둔다.

    윈도우 기본 체크박스는 테두리가 거의 안 보여서 켜졌는지 꺼졌는지 알기 어렵다.
    모양은 직접 그리되, 체크 표시만 그림이 필요해 여기서 한 번 만들어 재사용한다.
    """
    p = os.path.join(ICON_DIR, "check.png")
    if not os.path.exists(p):
        try:
            os.makedirs(ICON_DIR, exist_ok=True)
            pm = QtGui.QPixmap(34, 34)
            pm.fill(QtCore.Qt.transparent)
            g = QtGui.QPainter(pm)
            g.setRenderHint(QtGui.QPainter.Antialiasing)
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 4.4)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            g.setPen(pen)
            g.drawPolyline([QtCore.QPointF(9, 18), QtCore.QPointF(14.5, 24),
                            QtCore.QPointF(25, 11)])
            g.end()
            if not pm.save(p):
                return ""
        except Exception:
            logging.exception("check mark failed")
            return ""
    return p.replace("\\", "/")


def settings_qss():
    return _SETTINGS_QSS % check_mark_path()


class SettingsWindow(QtWidgets.QWidget):
    """설정을 한자리에 모은 창.

    항목이 늘면서 메뉴로는 무엇이 어디 있는지 찾기 어려워졌다. 여기서는 왼쪽 갈래로
    나눠 두고, 손대는 즉시 저장·반영한다(확인 버튼 없음). 값은 모두 pet.set_option()
    한 길로만 흘러서 메뉴에서 바꾸든 여기서 바꾸든 결과가 같다.
    """

    PAGES = (("일반", "_page_general"), ("행동", "_page_behavior"),
             ("대사·목소리", "_page_talk"), ("음악", "_page_music"),
             ("작업 표시", "_page_status"))

    def __init__(self, pet):
        super().__init__(None, QtCore.Qt.Tool)
        self.pet = pet
        self.binds = []          # (위젯, 값을 다시 넣는 함수) — sync()가 쓴다
        self.setWindowTitle("%s — %s" % (T("유이 펫"), T("설정")))
        self.setWindowIcon(pet._tray_icon())
        self.setStyleSheet(settings_qss())
        self.resize(660, 520)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QtWidgets.QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(158)
        self.stack = QtWidgets.QStackedWidget()

        right = QtWidgets.QWidget()
        rlay = QtWidgets.QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(self.stack, 1)

        foot = QtWidgets.QHBoxLayout()
        foot.setContentsMargins(20, 10, 18, 14)
        note = QtWidgets.QLabel(T("바꾸면 바로 저장돼요"))
        note.setObjectName("foot")
        b_close = QtWidgets.QPushButton(T("닫기"))
        b_close.clicked.connect(self.close)
        foot.addWidget(note)
        foot.addStretch(1)
        foot.addWidget(b_close)
        rlay.addLayout(foot)

        root.addWidget(self.nav)
        root.addWidget(right, 1)

        for title, builder in self.PAGES:
            self.nav.addItem(T(title))
            area = QtWidgets.QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(getattr(self, builder)())
            self.stack.addWidget(area)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

    # ---- 만들기 도우미 ----
    def _page(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(9)
        return w, lay

    def _group(self, lay, title):
        if lay.count():
            lay.addSpacing(10)
        lb = QtWidgets.QLabel(T(title).upper() if cur_lang() == "en" else T(title))
        lb.setObjectName("group")
        lay.addWidget(lb)

    def _hint(self, lay, text):
        lb = QtWidgets.QLabel(T(text))
        lb.setObjectName("hint")
        lb.setWordWrap(True)
        lay.addWidget(lb)

    def _row(self, lay, label, widget):
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(10)
        lb = QtWidgets.QLabel(T(label))
        lb.setMinimumWidth(120)
        h.addWidget(lb)
        h.addWidget(widget, 1)
        lay.addLayout(h)
        return widget

    def _check(self, lay, key, label, default=True, hint=""):
        b = QtWidgets.QCheckBox(T(label))
        b.setChecked(bool(self.pet.cfg.get(key, default)))
        b.toggled.connect(lambda on, k=key: self.pet.set_option(k, bool(on)))
        lay.addWidget(b)
        if hint:
            self._hint(lay, hint)
        self.binds.append((b, lambda w=b, k=key, d=default:
                           w.setChecked(bool(self.pet.cfg.get(k, d)))))
        return b

    def _spin(self, lay, key, label, lo, hi, default, step=1, suffix=""):
        s = QtWidgets.QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(int(self.pet.cfg.get(key, default)))
        if suffix:
            s.setSuffix(suffix)
        s.setFixedWidth(110)
        s.valueChanged.connect(lambda v, k=key: self.pet.set_option(k, int(v)))
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(10)
        lb = QtWidgets.QLabel(T(label))
        lb.setMinimumWidth(120)
        h.addWidget(lb); h.addWidget(s); h.addStretch(1)
        lay.addLayout(h)
        self.binds.append((s, lambda w=s, k=key, d=default:
                           w.setValue(int(self.pet.cfg.get(k, d)))))
        return s

    def _pct(self, lay, key, label, default, lo=0):
        """0~1 사이 값(음량·투명도)을 백분율 슬라이더로."""
        box = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        sl.setRange(lo, 100)
        sl.setValue(int(round(float(self.pet.cfg.get(key, default)) * 100)))
        val = QtWidgets.QLabel("%d%%" % sl.value())
        val.setObjectName("hint")
        val.setFixedWidth(38)
        val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        def moved(v, k=key):
            val.setText("%d%%" % v)
            self.pet.cfg[k] = v / 100.0      # 끄는 동안 바로 들리고 보이게
            if k == "musicVolume":
                self.pet.music._apply_volume()
            elif k == "opacity":
                self.pet._apply_opacity()

        sl.valueChanged.connect(moved)
        sl.sliderReleased.connect(lambda k=key: self.pet.set_option(k, sl.value() / 100.0))
        h.addWidget(sl, 1); h.addWidget(val)
        self._row(lay, label, box)
        self.binds.append((sl, lambda w=sl, k=key, d=default:
                           (w.setValue(int(round(float(self.pet.cfg.get(k, d)) * 100))),
                            val.setText("%d%%" % w.value()))))
        return sl

    def _combo(self, lay, key, label, items, default, on_pick=None):
        """items = ((값, 보일 이름), …)"""
        c = QtWidgets.QComboBox()
        for val, name in items:
            c.addItem(name, val)
        i = c.findData(self.pet.cfg.get(key, default))
        c.setCurrentIndex(max(0, i))

        def picked(_i, k=key):
            v = c.currentData()
            on_pick(v) if on_pick else self.pet.set_option(k, v)

        c.currentIndexChanged.connect(picked)
        self._row(lay, label, c)
        self.binds.append((c, lambda w=c, k=key, d=default:
                           w.setCurrentIndex(max(0, w.findData(self.pet.cfg.get(k, d))))))
        return c

    # ---- 갈래별 화면 ----
    def _page_general(self):
        w, lay = self._page()
        self._group(lay, "언어")
        self._combo(lay, "lang", "언어", [(c, n) for c, n in LANGS], "ko")

        self._group(lay, "시작")
        self.auto = QtWidgets.QCheckBox(T("부팅 시 자동 실행"))
        self.auto.setChecked(autostart_enabled())
        self.auto.toggled.connect(self._toggle_autostart)
        lay.addWidget(self.auto)
        self._hint(lay, "윈도우 켤 때 유이도 같이 켜져요")
        self.binds.append((self.auto, lambda w=self.auto: w.setChecked(autostart_enabled())))

        self._group(lay, "화면")
        pets = pet_list()
        self._combo(lay, "pet", "펫", [(pid, name) for pid, name in pets], "",
                    on_pick=self.pet._switch_pet)

        size = QtWidgets.QWidget()
        hs = QtWidgets.QHBoxLayout(size)
        hs.setContentsMargins(0, 0, 0, 0); hs.setSpacing(10)
        sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        sl.setRange(int(MIN_SCALE * 100), int(self.pet.max_scale * 100))
        sl.setValue(int(round(self.pet.scale * 100)))
        px = QtWidgets.QLabel()
        px.setObjectName("hint"); px.setFixedWidth(46)
        px.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        px.setText("%dpx" % round(LOGICAL_H * sl.value() / 100))
        sl.valueChanged.connect(
            lambda v: (px.setText("%dpx" % round(LOGICAL_H * v / 100)),
                       self.pet.set_scale(v / 100.0)))
        sl.sliderReleased.connect(self.pet._save_size)
        hs.addWidget(sl, 1); hs.addWidget(px)
        self._row(lay, "크기", size)
        self.binds.append((sl, lambda w=sl: w.setValue(int(round(self.pet.scale * 100)))))

        self._pct(lay, "opacity", "투명도", 1.0, lo=20)
        self._combo(lay, "clickAction", "클릭하면",
                    ((k, T(v)) for k, v in (("panel", "작업 목록 열기"),
                                            ("app", "앱 창 띄우기"),
                                            ("talk", "한마디 하기"),
                                            ("none", "아무것도 안 함"))), "panel")
        self._check(lay, "clickThrough", "클릭 통과 (끄려면 트레이 메뉴에서)", False)
        lay.addStretch(1)
        return w

    def _page_behavior(self):
        w, lay = self._page()
        self._group(lay, "스스로 하는 행동")
        self._check(lay, "wander", "자유롭게 돌아다니기")
        self._check(lay, "gazeEnabled", "마우스 쳐다보기")
        self._check(lay, "climbWindows", "창 위에 올라가기")
        self._check(lay, "climbWalls", "벽 타기")
        self._check(lay, "throwEnabled", "던지기")

        self._group(lay, "뽀모도로")
        self._spin(lay, "pomodoroFocusMin", "집중 시간(분)", 5, 180, 25, step=5)
        self._spin(lay, "pomodoroBreakMin", "쉬는 시간(분)", 1, 60, 5)
        lay.addStretch(1)
        return w

    def _page_talk(self):
        w, lay = self._page()
        self._group(lay, "대사")
        self._check(lay, "chatEnabled", "대사")
        jp = self._check(lay, "showJapanese", "일본어 원문 같이 보기")
        jp.setEnabled(cur_lang() != "ja")     # 일본어로 보면 같은 줄이 두 번 나온다

        self._group(lay, "목소리")
        self._check(lay, "voiceEnabled", "목소리")
        self._pct(lay, "voiceVolume", "목소리 음량", 0.7)

        self._group(lay, "날씨")
        self._check(lay, "weatherEnabled", "날씨에 맞춘 대사", False)
        for key, label, lo, hi, dv in (("weatherLat", "위도", -90.0, 90.0, 35.202944),
                                       ("weatherLon", "경도", -180.0, 180.0, 136.233694)):
            s = QtWidgets.QDoubleSpinBox()
            s.setDecimals(4); s.setRange(lo, hi); s.setSingleStep(0.1)
            s.setValue(float(self.pet.cfg.get(key, dv)))
            s.setFixedWidth(130)
            s.valueChanged.connect(lambda v, k=key: self.pet.set_option(k, float(v)))
            box = QtWidgets.QWidget()
            hb = QtWidgets.QHBoxLayout(box)
            hb.setContentsMargins(0, 0, 0, 0)
            hb.addWidget(s); hb.addStretch(1)
            self._row(lay, label, box)
            self.binds.append((s, lambda w=s, k=key, d=dv:
                               w.setValue(float(self.pet.cfg.get(k, d)))))
        lay.addStretch(1)
        return w

    def _page_music(self):
        w, lay = self._page()
        self._group(lay, "음악 폴더")
        self.dirs = QtWidgets.QListWidget()
        self.dirs.setObjectName("dirs")
        self.dirs.setFixedHeight(112)
        lay.addWidget(self.dirs)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        b_add = QtWidgets.QPushButton(T("폴더 추가…"))
        b_add.clicked.connect(self._add_dir)
        b_del = QtWidgets.QPushButton(T("빼기"))
        b_del.clicked.connect(self._drop_dir)
        b_scan = QtWidgets.QPushButton(T("다시 훑기"))
        b_scan.clicked.connect(self.pet._music_rescan)
        self.count = QtWidgets.QLabel()
        self.count.setObjectName("hint")
        row.addWidget(b_add); row.addWidget(b_del); row.addWidget(b_scan)
        row.addStretch(1); row.addWidget(self.count)
        lay.addLayout(row)
        self._hint(lay, "고른 폴더 아래를 전부 훑어요")

        self._group(lay, "재생 방식")
        self._pct(lay, "musicVolume", "음량", 0.45)
        self._check(lay, "musicShuffle", "무작위 순서")
        self._combo(lay, "musicFilter", "무엇을 틀까",
                    ((k, T(v)) for k, v in PlaylistWindow.KINDS), "song")
        b_open = QtWidgets.QPushButton(T("플레이어 열기…"))
        b_open.clicked.connect(self.pet._show_playlist)
        r = QtWidgets.QHBoxLayout()
        r.addWidget(b_open); r.addStretch(1)
        lay.addLayout(r)
        lay.addStretch(1)
        self._fill_dirs()
        self.binds.append((self.dirs, lambda: self._fill_dirs()))
        return w

    def _page_status(self):
        w, lay = self._page()
        self._check(lay, "privacyMode", "대화 내용 가리기", True,
                    hint="명령이나 질문 원문 대신 무엇을 하는 중인지만 보여줘요")
        self._check(lay, "codexWatch", "Codex 기록 읽기", True,
                    hint="훅을 안 걸어도 Codex 상태를 잡아줘요")

        self._group(lay, "말풍선")
        self._spin(lay, "bubbleWidth", "폭(px)", 240, 900, 400, step=20)
        self._spin(lay, "bubbleMaxLines", "최대 줄 수", 1, 6, 3)
        self._spin(lay, "completedDisplaySeconds", "완료 표시 시간(초)", 1, 30, 3)
        lay.addStretch(1)
        return w

    # ---- 동작 ----
    def _toggle_autostart(self, on):
        ok = set_autostart(bool(on))
        self.auto.blockSignals(True)
        self.auto.setChecked(autostart_enabled() if ok else not on)
        self.auto.blockSignals(False)

    def _music_dirs(self):
        return [d for d in (self.pet.cfg.get("musicDirs") or []) if d]

    def _fill_dirs(self):
        self.dirs.clear()
        for d in self._music_dirs():
            self.dirs.addItem(d)
        if not self.dirs.count():
            self.dirs.addItem(T("음악 폴더를 아직 안 정했어요"))
            self.dirs.item(0).setFlags(QtCore.Qt.NoItemFlags)
        self.count.setText(T("%d곡") % len(self.pet.music.tracks))

    def _add_dir(self):
        start = (self._music_dirs() or [os.path.expanduser("~")])[0]
        d = QtWidgets.QFileDialog.getExistingDirectory(self, T("음악 폴더 고르기"), start)
        if not d:
            return
        d = os.path.normpath(d)
        dirs = self._music_dirs()
        if d not in dirs:
            dirs.append(d)
            self.pet.set_option("musicDirs", dirs)

    def _drop_dir(self):
        it = self.dirs.currentItem()
        if it is None or not (it.flags() & QtCore.Qt.ItemIsEnabled):
            return
        dirs = [d for d in self._music_dirs() if d != it.text()]
        self.pet.set_option("musicDirs", dirs)

    def sync(self):
        """설정이 다른 데서 바뀌었을 때 위젯을 다시 맞춘다(신호는 막고)."""
        for w, apply in self.binds:
            w.blockSignals(True)
            try:
                apply()
            except Exception:
                logging.exception("settings sync failed")
            w.blockSignals(False)

    def show_near_pet(self):
        self.sync()
        scr = self.pet._screen()
        g = self.pet.frameGeometry()
        x = min(max(scr.left() + 8, g.center().x() - self.width() // 2),
                scr.right() - self.width() - 8)
        y = min(max(scr.top() + 8, g.top() - self.height() - 10),
                scr.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


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
        # 출처별 로고. 파일이 없는 소스는 글자 배지로 떨어진다.
        self.icons = {}
        for src, (_label, fn) in SOURCE_BADGE.items():
            if not fn:
                continue
            pm = QtGui.QPixmap(os.path.join(ICON_DIR, fn))
            if not pm.isNull():
                self.icons[src] = pm.scaled(14, 14, QtCore.Qt.KeepAspectRatio,
                                            QtCore.Qt.SmoothTransformation)

    def refresh(self, rows):
        # 하위 에이전트는 부모 밑으로 모아서 보여 준다(자르기 전에 묶어야 짝이 안 깨진다)
        self.rows = group_sessions(rows)[:8]    # 너무 길어지면 잘라 보여준다
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
            row = self.rows[i]
            title = row.get("title") or ""
            toggle_window(title.split("  ·")[0].strip() or None, row.get("app", ""))

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
                   T("작업 %d개  ·  줄을 누르면 창 열기/내리기") % len(self.rows))

        if not self.rows:
            p.setPen(QtGui.QColor(150, 150, 160))
            p.drawText(card, QtCore.Qt.AlignCenter, T("도는 작업이 없어요"))
            p.end(); return

        y = self.PAD + 18
        for i, r in enumerate(self.rows):
            rect = QtCore.QRectF(6, y, self.width() - 12, self.ROW_H - 2)
            if i == self.hover:
                p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(236, 234, 255))
                p.drawRoundedRect(rect, 8, 8)
            x = rect.left() + 10
            if r.get("depth"):                  # 하위 에이전트 — 한 칸 들여쓰고 ㄴ 표시
                f0 = QtGui.QFont(self.font()); f0.setPixelSize(11)
                p.setFont(f0); p.setPen(QtGui.QColor(176, 176, 186))
                p.drawText(QtCore.QRectF(x, rect.top(), 14, rect.height()),
                           QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "ㄴ")
                x += 15
            icon = self.icons.get(r["source"])
            if icon is not None:
                p.drawPixmap(int(x), int(rect.center().y() - 7), icon)
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
                       QtGui.QFontMetrics(f3).elidedText(T(r["title"]), QtCore.Qt.ElideRight, int(tw)))
            f4 = QtGui.QFont(self.font()); f4.setPixelSize(11)
            el = elapsed_text(r.get("started", 0) if r["phase"] == "working" else 0, short=True)
            ew = QtGui.QFontMetrics(f4).horizontalAdvance(el) + 8 if el else 0
            p.setFont(f4); p.setPen(QtGui.QColor(124, 124, 133))
            dx = x + tw + 6
            dw = rect.right() - dx - 60 - ew
            p.drawText(QtCore.QRectF(dx, rect.top(), dw, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                       QtGui.QFontMetrics(f4).elidedText(T(r["detail"]), QtCore.Qt.ElideRight, int(dw)))
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
                       T(PHASE_WORD.get(r["phase"], "")))
            y += self.ROW_H
        p.end()


class YuiPet(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        set_lang(self.cfg.get("lang", "ko"))
        self.scale = self.cfg["petHeight"] / LOGICAL_H   # 높이 기반 배율(매직넘버 제거)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.label = QtWidgets.QLabel(self)
        self.label.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.anim_durs = {name: durs for name, (row, durs) in ROW_DEF.items()}
        if not self._load_sheet(pet_sheet_path(self.cfg.get("pet", ""))):
            QtWidgets.QMessageBox.critical(self, T("유이 펫"), T("스프라이트를 읽지 못했어요"))
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
        self.app = ""                     # 대표 작업이 제 앱을 갖고 있으면 그 앱 키
        self.dragging = False
        self._drag_offset = self._last_mouse = self._press_pos = None
        self._moved = False
        self._look_state = False   # 지금 커서를 보고 있는지
        self._gaze_until = 0.0     # 이 시각까지만 본다(사건이 있을 때 _notice가 늘린다)
        self._avert_until = 0.0    # 보다가 잠깐 눈을 뗀 구간
        self._gaze_next_avert = 0.0
        self._gaze_notice_until = 0.0   # 커서 근접으로 다시 알아채기까지의 쿨다운
        self._cursor_near = False  # 커서가 응시 반경 안에 있었는지(들어오는 순간만 잡는다)
        self._done_gen = 0         # 완료 타이머 세대 토큰
        self._behavior = "rest"    # 자율 행동: rest | walk
        self._rest_until = 0.0
        self._walk_to = self._walk_last = 0.0
        self._hidden_by_fullscreen = False
        self._hidden_by_user = False
        self._say_until = 0.0
        self._phase_voice_until = 0.0
        self.lines = load_lines(self.cfg.get("pet", ""))
        self.voice = VoicePlayer(self.cfg, self.cfg.get("pet", ""))
        self.music = MusicPlayer(self.cfg, on_track=self._on_track, parent=self)
        self.voice.duck = self.music.duck   # 목소리가 나는 동안 음악을 낮춘다
        self.playlist = None                # 곡 고르기 창(처음 열 때 만든다)
        self.settings = None                # 설정 창(처음 열 때 만든다)
        self._track_said = 0.0              # 근접해서 곡명을 알려준 시각
        self._pomo = None          # 뽀모도로: None | {"kind": "focus"|"break", "until": ts}
        self._clicks = []          # 연속 클릭 판정용 타임스탬프
        self._prox_until = 0.0     # 근접 반응 쿨다운
        self._throw = None         # 던져진 상태: {"vx","vy","x","y"}
        self._shelves = []         # 창 위쪽 모서리 목록(발판)
        self._shelf = None         # 지금 올라가 있는 발판. None이면 바닥
        self._hop = None           # 발판으로 뛰는 중: {"x0","y0","x1","y1","t0"}
        self._climb = None         # 벽을 타는 중: {"wall":"left"|"right"}
        self._climb_intent = None  # 벽까지 걸어가는 중이면 어느 벽인지
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
        self.shelf_timer = QtCore.QTimer(self); self.shelf_timer.timeout.connect(self._shelf_tick)
        self.shelf_timer.start(SHELF_TICK_MS)
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
        self.tray.setToolTip(T("유이 펫"))
        self._build_tray_menu()
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _build_tray_menu(self):
        """트레이 메뉴. 자잘한 설정은 설정 창으로 넘기고 여기엔 자주 쓰는 것만 둔다.

        언어를 바꾸면 이미 만들어 둔 메뉴의 글자는 그대로라 통째로 다시 만든다.
        """
        if not self.tray:
            return
        m = QtWidgets.QMenu()
        m.setStyleSheet(MENU_QSS)
        self._act_show = m.addAction(T("펫 보이기"))
        self._act_show.setCheckable(True)
        self._act_show.setChecked(not self._hidden_by_user)
        self._act_show.toggled.connect(self.set_visible_by_user)
        self._act_wander = m.addAction(T("자유롭게 돌아다니기"))
        self._act_wander.setCheckable(True)
        self._act_wander.setChecked(bool(self.cfg.get("wander", True)))
        self._act_wander.toggled.connect(lambda on: self.set_option("wander", bool(on)))
        self._act_chat = m.addAction(T("대사"))
        self._act_chat.setCheckable(True)
        self._act_chat.setChecked(bool(self.cfg.get("chatEnabled", True)))
        self._act_chat.toggled.connect(lambda on: self.set_option("chatEnabled", bool(on)))
        self._act_through = m.addAction(T("클릭 통과"))
        self._act_through.setCheckable(True)
        self._act_through.setChecked(bool(self.cfg.get("clickThrough", False)))
        self._act_through.toggled.connect(lambda on: self.set_option("clickThrough", bool(on)))
        self._act_pomo = m.addAction(T("뽀모도로 시작"))
        self._act_pomo.setCheckable(True)
        self._act_pomo.setChecked(self._pomo is not None)
        self._act_pomo.toggled.connect(self._set_pomodoro)
        self._music_menu(m)
        m.addSeparator()
        m.addAction(T("설정…")).triggered.connect(self._show_settings)
        m.addAction(T("종료")).triggered.connect(self._quit)
        self.tray.setContextMenu(m)
        self._tray_menu = m

    def _tray_activated(self, reason):
        # 아이콘을 더블클릭하면 숨김/보임 토글
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self._act_show.setChecked(self._hidden_by_user)

    # ---- 설정 ----
    def set_option(self, key, value):
        """설정 한 항목을 바꾸고 저장한다. 곧바로 보여야 하는 것은 여기서 반영한다.

        메뉴·설정 창이 같은 길로 들어오게 해서 어느 쪽에서 바꾸든 결과가 같다.
        """
        old = self.cfg.get(key)
        self.cfg[key] = value
        self._save_cfg({key: value})
        if key == "clickThrough":
            self._apply_click_through()
        elif key == "opacity":
            self._apply_opacity()
        elif key == "voiceEnabled" and not value:
            self.voice.stop()
        elif key == "gazeEnabled":
            if self.anim == "idle" and not self.dragging:
                self._render_idle()      # 다음 프레임까지 기다리지 않고 바로 반영
        elif key == "chatEnabled" and not value:
            self.voice.stop()
            if self._saying():
                self._dismiss_say()
        elif key == "wander":
            self._rest(1000) if value else self._enter("idle")
        elif key == "climbWindows" and not value and self._shelf:
            self._shelf = None
            self._fall()
        elif key == "musicShuffle":
            self.music._reorder()
        elif key == "musicVolume":
            self.music._apply_volume()
        elif key == "musicFilter":
            self.music.set_filter(value)
        elif key == "musicDirs":
            self.music.scan()
            if self.playlist is not None and self.playlist.isVisible():
                self.playlist.refresh()
        elif key == "lang" and value != old:
            set_lang(value)
            # 지금 이 신호를 낸 위젯을 그 자리에서 지우면 위험하다. 한 박자 뒤에 갈아엎는다
            QtCore.QTimer.singleShot(0, self._retranslate)
        self._sync_controls()

    def _sync_controls(self):
        """메뉴 체크와 설정 창을 지금 설정에 맞춘다(어디서 바꾸든 같이 움직이게)."""
        for act, key, dv in ((getattr(self, "_act_wander", None), "wander", True),
                             (getattr(self, "_act_chat", None), "chatEnabled", True),
                             (getattr(self, "_act_through", None), "clickThrough", False)):
            if act is not None:
                act.blockSignals(True)
                act.setChecked(bool(self.cfg.get(key, dv)))
                act.blockSignals(False)
        if self.settings is not None:
            self.settings.sync()

    def _show_settings(self):
        if self.settings is None:
            self.settings = SettingsWindow(self)
        self.settings.show_near_pet()

    def _retranslate(self):
        """언어가 바뀌었다. 이미 만들어 둔 화면을 새 언어로 다시 만든다."""
        self._build_tray_menu()
        self._pomo_tooltip()
        if self.playlist is not None:
            vis = self.playlist.isVisible()
            self.playlist.close(); self.playlist.deleteLater(); self.playlist = None
            if vis:
                self._show_playlist()
        if self.settings is not None:
            vis, page = self.settings.isVisible(), self.settings.nav.currentRow()
            geo = self.settings.geometry()
            self.settings.close(); self.settings.deleteLater(); self.settings = None
            if vis:
                self._show_settings()
                self.settings.setGeometry(geo)
                self.settings.nav.setCurrentRow(max(0, page))
        self._refresh_bubble()

    # ---- 음악 ----
    def _on_track(self, title):
        """곡이 바뀌면 무슨 곡인지 짧게 알려준다."""
        if not title:
            return
        self._say("♪ " + title, "", ms=2600, force=True)
        if self.phase == "idle" and not self.dragging and self.anim == "idle":
            self._enter("waving", oneshot_after="idle")

    def _music_menu(self, parent):
        """음악 메뉴를 만든다. 트레이 메뉴는 오래 살아 있으므로 열 때마다 다시 채운다."""
        m = parent.addMenu(T("음악"))
        self._fill_music_menu(m)
        m.aboutToShow.connect(lambda: self._fill_music_menu(m))
        return m

    def _fill_music_menu(self, m):
        m.clear()
        if not self.music.available():
            a = m.addAction(T("음악 폴더가 비어 있음"))
            a.setEnabled(False)
            m.addAction(T("폴더 다시 훑기")).triggered.connect(self._music_rescan)
            return
        # 자주 쓰는 것은 플레이어 창에 다 있다. 메뉴는 최소만 둔다
        m.addAction(T("플레이어 열기…")).triggered.connect(self._show_playlist)
        cur = self.music.title()
        if cur:
            a_cur = m.addAction(T("지금: ") + cur[:44])
            a_cur.setEnabled(False)
        m.addSeparator()
        a_play = m.addAction(T("일시정지") if self.music.playing() else T("재생"))
        a_play.triggered.connect(self.music.toggle)
        m.addAction(T("다음 곡")).triggered.connect(lambda: self.music.step(1))
        m.addAction(T("이전 곡")).triggered.connect(lambda: self.music.step(-1))
        a_stop = m.addAction(T("정지"))
        a_stop.triggered.connect(self.music.stop)
        a_sh = m.addAction(T("무작위 순서"))
        a_sh.setCheckable(True)
        a_sh.setChecked(bool(self.cfg.get("musicShuffle", True)))
        a_sh.toggled.connect(self._set_shuffle)
        m.addAction(SliderAction(m, self, "music"))
        km = m.addMenu(T("무엇을 틀까"))
        counts = {k: self.music.kinds.count(k) for k in ("song", "inst", "bgm")}
        cur_kind = self.music.filter()
        for key, label in PlaylistWindow.KINDS:
            n = len(self.music.tracks) if key == "all" else counts.get(key, 0)
            a = km.addAction("%s (%d)" % (T(label), n))
            a.setCheckable(True)
            a.setChecked(key == cur_kind)
            a.triggered.connect(lambda _=False, k=key: self._set_music_kind(k))
        m.addAction(T("폴더 다시 훑기")).triggered.connect(self._music_rescan)

    def _set_music_kind(self, kind):
        self.set_option("musicFilter", kind)
        if self.playlist is not None and self.playlist.isVisible():
            self.playlist._set_kind(kind)

    def _show_playlist(self):
        if self.playlist is None:
            self.playlist = PlaylistWindow(self)
        self.playlist.show_near_pet()

    def _music_rescan(self):
        self.music.scan()
        n = len(self.music.tracks)
        self._say(T("노래 %d곡 찾았어~") % n if n else T("음악 폴더가 비었어~"),
                  "", force=True)
        if self.playlist is not None and self.playlist.isVisible():
            self.playlist.refresh()
        if self.settings is not None:
            self.settings.sync()

    def _set_shuffle(self, on):
        self.set_option("musicShuffle", bool(on))

    def _set_wander(self, on):
        self.set_option("wander", bool(on))

    def _quit(self):
        self.voice.stop()
        self.music.stop()
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
        # 표시 상한은 모든 펫에 같게 주되, 더 큰 원본 시트는 그 해상도까지 허용한다.
        self.sheet_scale = CELL_H / LOGICAL_H
        self.max_scale = max(DISPLAY_MAX_SCALE, self.sheet_scale)
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
        self.voice.set_pet(pet_id)  # 펫별 목소리 폴더가 있으면 그쪽으로 갈아탄다
        self.lines = load_lines(pet_id)   # 대사도 펫 것이 있으면 같이 갈아탄다
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
        # 창 아래끝이 아니라 실제 발밑을 앵커로 잡는다. 크기가 커지면 하단 여백도
        # 같이 커지므로, 창 기준으로 맞추면 발이 조금씩 내려앉는다
        anchor_x, anchor_y = g.center().x(), self._foot_y()
        self.scale = scale
        self._apply_size()
        scr = self._screen()
        x = max(scr.left(), min(anchor_x - self.width() // 2, scr.right() - self.width()))
        y = max(scr.top(), min(self._y_on(anchor_y), self._y_on(scr.bottom())))
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
        # 세로는 바닥에 딱 맞춘다. 여백을 주면 공중에 떠서 걸어다니는 것처럼 보인다
        scr = self._screen()
        self.move(scr.right() - self.width() - 40, self._y_on(scr.bottom()))
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
        """대사 한 줄 → (본문, 곁들일 원문, 음성파일). 문자열만 있는 옛 형식도 받아준다.

        본문은 지금 언어로, 곁들이는 줄은 일본어 원문이다. 일본어로 보고 있으면
        같은 문장이 두 번 나오니 곁들이지 않는다. 그 언어 대사가 아직 없으면
        한국어 → 일본어 순으로 물러선다.
        """
        if not isinstance(item, dict):
            return str(item), "", ""
        ja = item.get("ja", "")
        main = item.get(cur_lang(), "") or item.get("ko", "") or ja
        sub = "" if (cur_lang() == "ja" or main == ja) else ja
        return main, sub, item.get("v", "")

    # 목소리가 붙은 대사를 이 확률로 우선한다. 남은 확률로는 글자만 있는 대사도 나와야
    # 대사 폭이 안 좁아진다.
    VOICED_BIAS = 0.7

    def _pick_line(self, kind=None):
        sp = self.lines.get("special", {}) or {}
        today = sp.get(time.strftime("%m-%d"))
        pool = today if (today and random.random() < 0.6) else \
            (self.lines.get(kind or time_bucket()) or [])
        if not pool:
            return "", "", ""
        if self.cfg.get("voiceEnabled", True) and random.random() < self.VOICED_BIAS:
            voiced = [i for i in pool
                      if isinstance(i, dict) and i.get("v") in self.voice._effects]
            if voiced:
                pool = voiced
        return self._split_line(random.choice(pool))

    def _say_line(self, kind=None, always=False, **kw):
        """상황에 맞는 대사를 하나 골라 말한다(목소리가 있으면 같이 낸다).

        대사를 꺼 두면 스스로 하는 말도, 눌렀을 때 하는 말도 나오지 않는다.
        사용자가 직접 켜 둔 뽀모도로의 구간 종료 알림만 always로 지나간다 —
        그것마저 막으면 남은 시간을 알 방법이 트레이 툴팁뿐이라 알림 구실을 못 한다.
        작업 상태 말풍선과 곡 제목은 대사가 아니라서 이 스위치와 무관하다.
        """
        if not always and not self.cfg.get("chatEnabled", True):
            return
        text, sub, v = self._pick_line(kind)
        self._say(text, sub, voice=v, **kw)

    def _say(self, text, sub="", ms=SAY_MS, force=False, voice=""):
        """말풍선으로 한마디. sub는 곁들이는 일본어 원문이다.

        평소엔 작업 상태 표시를 가리지 않으려고 idle일 때만 말한다.
        force=True(사용자가 직접 클릭)면 작업 중에도 말하고, 끝나면 상태 표시로 되돌린다.
        """
        if not text or not self.isVisible():
            return
        if not force and self.phase != "idle":
            return          # 말풍선을 접는 경우엔 소리도 내지 않는다
        self.voice.play(voice)
        self.bubble.set_badge("")
        self.bubble.set_more(0)
        self.bubble.set_state("say", text, sub if self.cfg.get("showJapanese", True) else "")
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
        # 세션을 열 때는 「おかえり」 같은 인사도 섞는다
        self._say_line("greet" if random.random() < 0.45 else None)

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
        self._notice()              # 눌렀으면 부른 것이니 이쪽을 본다
        self._clicks = [t for t in self._clicks if now - t <= CLICK_COMBO_MS / 1000.0]
        self._clicks.append(now)
        if len(self._clicks) >= CLICK_COMBO_N:      # 연달아 누르면 좋아한다
            self._clicks = []
            self._enter("jumping", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
            self._say_line("petted", force=True)
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
                self._say_line("idleChat", force=True)
        elif act == "app":
            try:
                # 지금 대표로 보여 주는 작업의 앱을 연다(데스크톱 Codex면 Codex, 그 외엔 편집기).
                toggle_window(None, self.app)
            except Exception:
                pass
        elif act == "talk":
            self._say_line("idleChat", force=True)

    def _proximity_check(self):
        """커서가 가까이 오면 반응한다.

        음악이 나오는 중이면 무슨 곡인지 알려준다(짧은 쿨다운). 그게 아니면 놀란다.
        """
        if self.phase != "idle" or self.dragging or self._throw or self.anim != "idle":
            return
        now = time.monotonic()
        dx, dy = self._cursor_vec()
        near = math.hypot(dx, dy) <= self.height() * PROXIMITY_RATIO
        if not near:
            return
        if self.music.playing():
            if now - self._track_said >= TRACK_HINT_COOLDOWN_S and not self._saying():
                self._track_said = now
                self._say("♪ " + self.music.title(), "", ms=3200, force=True)
            return
        if now < self._prox_until:
            return
        self._prox_until = now + PROXIMITY_COOLDOWN_S
        self._enter(random.choice(("jumping", "waving")), oneshot_after="idle")
        self._say_line("surprised")

    # ---- 창 위 올라가기 ----
    def _foot_pad(self):
        """스프라이트 아래쪽 빈 여백. 이만큼 파묻어야 발이 바닥에 닿아 보인다."""
        return int(round(FOOT_PAD * self.scale))

    def _y_on(self, top):
        """윗면 y좌표가 top인 발판에 설 때의 창 y좌표."""
        return int(top - self.height() + self._foot_pad())

    def _foot_y(self, y=None):
        """발밑 y좌표. 착지 판정은 이 값으로 한다."""
        return (self.y() if y is None else y) + self.height() - self._foot_pad()

    def _floor_y(self):
        """지금 서 있는 자리의 발판 높이(창 위 또는 화면 바닥)."""
        top = self._shelf["top"] if self._shelf else self._screen().bottom()
        return self._y_on(top)

    def _shelf_tick(self):
        """창 목록을 갱신하고, 올라가 있던 창이 움직이거나 사라진 것을 처리한다."""
        if not self.cfg.get("climbWindows", True) or not self.isVisible():
            self._shelves = []
            return
        try:
            self._shelves = window_shelves(int(self.winId()), self._screen())
        except Exception:
            logging.exception("shelf scan failed")
            return
        if not self._shelf or self.dragging or self._throw or self._hop:
            return
        cur = next((s for s in self._shelves if s["hwnd"] == self._shelf["hwnd"]), None)
        if cur is None:                      # 창이 닫혔거나 최소화됐다 → 떨어진다
            self._shelf = None
            self._fall()
            return
        moved_x = cur["left"] - self._shelf["left"]
        self._shelf = cur
        # 창을 옮기면 그 위에 있던 펫도 같이 따라간다
        x = self.x() + moved_x
        x = max(cur["left"], min(x, cur["right"] - self.width()))
        if x + self.width() * 0.5 < cur["left"] or x + self.width() * 0.5 > cur["right"]:
            self._shelf = None
            self._fall()
            return
        self.move(int(x), self._y_on(cur["top"]))
        if self._behavior == "walk":
            self._walk_to = max(cur["left"] + SHELF_EDGE_PAD,
                                min(self._walk_to + moved_x,
                                    cur["right"] - self.width() - SHELF_EDGE_PAD))
        if self.bubble.isVisible():
            self._reposition_bubble()

    def _fall(self):
        """제자리에서 자유낙하. 던지기 물리를 쓰되 중력을 낮춰 떨어지는 게 보이게 한다."""
        self._hop = None
        self._climb = None
        self._throw = {"vx": 0.0, "vy": float(FALL_START_VY), "g": FALL_GRAVITY,
                       "x": float(self.x()), "y": float(self.y())}
        self._throw_last = time.monotonic()
        self._enter("jumping")

    def _shelf_candidates(self):
        """지금 자리에서 뛰어올라 갈 만한 발판들."""
        cx = self.x() + self.width() * 0.5
        base = self.y()
        reach = SHELF_HOP_MAX * self.scale
        out = []
        for s in self._shelves:
            if s["right"] - s["left"] < self.width() * 1.4:
                continue
            top_y = self._y_on(s["top"])
            if not (base - reach <= top_y < base - 20):      # 위쪽, 손이 닿는 높이
                continue
            if s["left"] - reach * 0.5 <= cx <= s["right"] + reach * 0.5:
                out.append(s)
        return out

    def _try_hop(self):
        """창 위로 뛰어오른다. 올라갈 데가 없으면 False."""
        cands = self._shelf_candidates()
        if not cands:
            return False
        s = random.choice(cands)
        x1 = max(s["left"] + SHELF_EDGE_PAD,
                 min(self.x(), s["right"] - self.width() - SHELF_EDGE_PAD))
        self._hop = {"x0": float(self.x()), "y0": float(self.y()),
                     "x1": float(x1), "y1": float(self._y_on(s["top"])),
                     "t0": time.monotonic(), "shelf": s}
        self._behavior = "rest"
        self._rest_until = time.monotonic() + 9e9      # 착지할 때까지 딴짓 금지
        self._enter("jumping")
        return True

    def _hop_step(self):
        """포물선으로 올라간다. 도착하면 그 창을 발판으로 삼는다."""
        h = self._hop
        p = (time.monotonic() - h["t0"]) / (SHELF_HOP_MS / 1000.0)
        if p >= 1.0:
            self.move(int(h["x1"]), int(h["y1"]))
            self._shelf = h["shelf"]
            self._hop = None
            self._enter("idle")
            self._rest(random.randint(1800, 4000))
            return
        # 목표보다 조금 더 높이 솟았다가 내려앉는다
        lift = 42 * self.scale * math.sin(math.pi * p)
        self.move(int(h["x0"] + (h["x1"] - h["x0"]) * p),
                  int(h["y0"] + (h["y1"] - h["y0"]) * p - lift))
        if self.bubble.isVisible():
            self._reposition_bubble()

    # ---- 벽타기 ----
    def _try_climb(self, force=False):
        """벽을 타고 오른다. 벽에서 떨어져 있으면 먼저 벽까지 걸어간다."""
        if self._shelf or self._climb or self._hop:
            return False
        if not force and not self.cfg.get("climbWalls", True):
            return False
        scr = self._screen()
        near_left = self.x() - scr.left()
        near_right = (scr.right() - self.width()) - self.x()
        if min(near_left, near_right) <= 8:
            self._begin_climb("left" if near_left <= near_right else "right")
            return True
        # 아직 멀다 — 가까운 벽으로 걸어가고, 닿으면 그때 오른다
        wall = "left" if near_left <= near_right else "right"
        self._climb_intent = wall
        self._walk_to = float(scr.left() if wall == "left" else scr.right() - self.width())
        self._behavior = "walk"
        self._walk_last = time.monotonic()
        self._enter("running-left" if wall == "left" else "running-right")
        return True

    def _begin_climb(self, wall):
        self._climb_intent = None
        self._climb = {"wall": wall, "until": time.monotonic() + random.uniform(2.5, 6.0)}
        self._behavior = "rest"
        self._rest_until = time.monotonic() + 9e9
        self._climb_last = time.monotonic()
        # 벽에 딱 붙인다. 오르는 그림이 없어 달리는 프레임으로 대신한다
        self.move(self._screen().left() if wall == "left"
                  else self._screen().right() - self.width(), self.y())
        self._enter("running-right" if wall == "right" else "running-left")

    def _climb_step(self, dt):
        scr = self._screen()
        c = self._climb
        y = self.y() - CLIMB_SPEED * self.scale * dt
        top_stop = scr.top() + 10
        if y <= top_stop or time.monotonic() >= c["until"]:
            # 위에 붙은 창이 있으면 그 위로 올라서고, 없으면 떨어진다
            self._climb = None
            if not self._try_hop():
                self._fall()
            return
        self.move(self.x(), int(y))
        if self.bubble.isVisible():
            self._reposition_bubble()

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

    def _shelf_under(self, y_before, y_after, x):
        """내려오는 동안 발밑을 지나간 창을 찾는다(창 위에 착지하기 위해)."""
        cx = x + self.width() * 0.5
        foot0, foot1 = self._foot_y(y_before), self._foot_y(y_after)
        best = None
        for s in self._shelves:
            if not (s["left"] + 4 <= cx <= s["right"] - 4):
                continue
            if foot0 <= s["top"] <= foot1:
                if best is None or s["top"] < best["top"]:   # 먼저 만나는 것(위쪽)
                    best = s
        return best

    def _throw_step(self, dt):
        scr = self._screen()
        t = self._throw
        t["vy"] += t.get("g", THROW_GRAVITY) * dt
        t["x"] += t["vx"] * dt
        y_before = t["y"]
        t["y"] += t["vy"] * dt
        floor = self._y_on(scr.bottom())
        if t["x"] < scr.left() or t["x"] > scr.right() - self.width():   # 벽에서 튕김
            t["x"] = max(scr.left(), min(t["x"], scr.right() - self.width()))
            t["vx"] = -t["vx"] * THROW_BOUNCE
        # 내려오는 중이면 창 위에 올라설 수 있다
        if t["vy"] > 0 and self.cfg.get("climbWindows", True):
            s = self._shelf_under(y_before, t["y"], t["x"])
            if s is not None and abs(t["vy"]) < 900:
                self.move(int(t["x"]), self._y_on(s["top"]))
                self._shelf = s
                self._throw = None
                self._enter("idle")
                self._rest(random.randint(1500, 3500))
                return
        if t["y"] >= floor:                                              # 착지
            t["y"] = floor
            t["vy"] = -t["vy"] * THROW_BOUNCE
            t["vx"] *= 0.7
            if abs(t["vy"]) < 120:
                self.move(int(t["x"]), int(floor))
                self._throw = None
                self._shelf = None
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
            self.tray.setToolTip(T("유이 펫"))
            return
        left = max(0, int(self._pomo["until"] - time.monotonic()))
        label = T("집중") if self._pomo["kind"] == "focus" else T("휴식")
        self.tray.setToolTip(T("유이 펫 — %s %d:%02d 남음") % (label, left // 60, left % 60))

    def _pomo_tick(self):
        if not self._pomo:
            return
        self._pomo_tooltip()
        if time.monotonic() < self._pomo["until"]:
            return
        done = self._pomo["kind"]
        self._pomo_begin("break" if done == "focus" else "focus")
        self._say_line("pomoFocusEnd" if done == "focus" else "pomoBreakEnd",
                       ms=7000, always=True)
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

    def _notice(self, hold=None):
        """무슨 일이 생겨서 잠깐 이쪽을 본다. 시선은 오직 여기서만 시작된다."""
        if not self.cfg.get("gazeEnabled", True):
            return
        now = time.monotonic()
        self._gaze_until = now + (hold or random.uniform(*GAZE_HOLD_S))
        self._gaze_next_avert = now + random.uniform(*GAZE_LOOK_S)
        self._avert_until = 0.0

    def _looking(self):
        """지금 커서를 보고 있는지. 시선 구간 안에서도 중간중간 눈을 뗀다."""
        if not self.cfg.get("gazeEnabled", True):
            self._look_state = False     # 꺼 두면 정면 호흡만 한다
            return False
        now = time.monotonic()
        if now >= self._gaze_until or now < self._avert_until:
            self._look_state = False
            return False
        if now >= self._gaze_next_avert:      # 한동안 봤으면 눈을 뗄 차례다
            self._avert_until = now + random.uniform(*GAZE_AVERT_S)
            self._gaze_next_avert = self._avert_until + random.uniform(*GAZE_LOOK_S)
            self._look_state = False
            return False
        self._look_state = True
        return True

    def _watch_cursor(self):
        """커서가 반경 안으로 **들어오는 순간**에만 알아챈다.

        머무는 내내 다시 보면 결국 계속 쳐다보는 것과 같아진다. 오갈 때마다 반응하지
        않도록 쿨다운도 둔다.
        """
        if not self.cfg.get("gazeEnabled", True) or not self.isVisible():
            self._cursor_near = False
            return
        dx, dy = self._cursor_vec()
        near = math.hypot(dx, dy) <= max(self.width(), self.height()) * GAZE_NEAR_RATIO
        if near and not self._cursor_near and time.monotonic() >= self._gaze_notice_until:
            self._gaze_notice_until = time.monotonic() + GAZE_NOTICE_COOLDOWN_S
            self._notice()
        self._cursor_near = near

    def _render_idle(self):
        if self._looking():
            dx, dy = self._cursor_vec()
            idx = int(round((math.degrees(math.atan2(dx, -dy)) % 360) / 22.5)) % 16
            remap = LOOK_REMAP_BY_PET.get(self.cfg.get("pet", ""), {})
            idx = remap.get(idx, idx)   # 해당 펫에만 필요한 프레임 보정
            self._show(self.looks()[idx])
        else:
            self._show(self.frames("idle")[0])

    def _track(self):
        self._watch_cursor()         # 시선을 안 주는 동안에도 다가오는 건 알아채야 한다
        if self.dragging or self.phase != "idle" or self.oneshot_after is not None:
            return
        if self.anim != "idle":      # 걷는 중엔 시선 프레임이 걸음을 덮어쓰면 안 된다
            return
        if self._looking():          # 보는 동안만 부드럽게 갱신(나머지는 호흡 루프가 담당)
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
        self._climb_intent = None      # 벽으로 가던 길이 끊겼으면 계획도 접는다
        if ms is None:
            ms = random.randint(*self._profile()["rest"])
        self._rest_until = time.monotonic() + ms / 1000.0
        # 작업 표시 중에는 그 애니를 유지한다. idle 애니로 돌리는 건 idle일 때만.
        if self.anim != "idle" and self.phase == "idle":
            self._enter("idle")

    def _pick_action(self):
        # 손을 멈췄을 때만 가끔 이쪽을 흘끗 본다. 타이핑 중에는 먼저 쳐다보지 않는다.
        if self._profile() is FREE and random.random() < GAZE_GLANCE_P:
            self._notice()
        names, weights = zip(*self._profile()["actions"])
        act = random.choices(names, weights=weights)[0]
        if act == "walk":
            # 걸으려던 참에 가끔 창 위로 올라가거나 벽을 탄다.
            # 둘 중 뭘 먼저 시도할지 섞는다 — 창이 많으면 늘 창만 오르게 되기 때문이다
            if self._profile() is FREE and random.random() < 0.45:
                first, second = ((self._try_hop, self._try_climb)
                                 if random.random() < 0.55
                                 else (self._try_climb, self._try_hop))
                if first() or second():
                    return
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
            self._say_line(kind)
            self._rest()
        else:
            self._rest()

    def _walk_bounds(self):
        """걸어도 되는 좌우 범위. 창 위에 있으면 그 창 폭 안에서만 움직인다."""
        if self._shelf:
            return (self._shelf["left"] + SHELF_EDGE_PAD,
                    self._shelf["right"] - self.width() - SHELF_EDGE_PAD)
        scr = self._screen()
        return scr.left(), scr.right() - self.width()

    def _start_walk(self):
        lo, hi = self._walk_bounds()
        if hi <= lo:                      # 발판이 너무 좁아졌다
            self._fall() if self._shelf else self._rest(1500)
            return
        span = random.uniform(*self._profile()["dist"]) * self.scale
        direction = random.choice((-1, 1))
        x = self.x() + direction * span
        # 끝을 넘어가려 하면 반대로 튼다. 창 위에서는 가끔 그대로 뛰어내린다
        if x < lo or x > hi:
            if self._shelf and random.random() < 0.3:
                self._shelf = None
                self._fall()
                return
            direction = -direction
            x = self.x() + direction * span
        self._walk_to = max(lo, min(x, hi))
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
        if self._hop:                         # 창 위로 뛰어오르는 중
            self._hop_step()
            return
        if self._climb:                       # 벽을 타는 중
            now = time.monotonic()
            dt = min(0.05, now - getattr(self, "_climb_last", now))
            self._climb_last = now
            self._climb_step(dt)
            return
        self._climb_last = time.monotonic()
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
        # 걸을 때마다 발판 높이로 맞춘다. 안 그러면 한 번 뜬 높이가 계속 유지된다
        fy = self._floor_y()
        dx = self._walk_to - self.x()
        if abs(dx) <= step:
            self.move(int(self._walk_to), fy)
            if self._climb_intent:          # 벽까지 왔다 — 이제 오른다
                self._begin_climb(self._climb_intent)
                return
            self._rest()
            return
        self.move(int(self.x() + math.copysign(step, dx)), fy)
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
                tr = d.get("transcript", "")
                source = d.get("source", src)
                rows.append({"phase": ph, "title": d.get("title", ""),
                             "detail": d.get("detail", ""), "ts": ts,
                             "started": d.get("started_at", 0) or 0,
                             "transcript": tr, "source": source,
                             # 훅이 남긴 Codex 세션도 데스크톱에서 돈 것만 앱 창이 있다
                             "app": codex_app(tr) if source == "codex" else "",
                             "session_id": os.path.splitext(fn)[0]})

        # Codex는 훅이 안 도는 환경이 많아 대화 기록을 직접 읽어 보탠다.
        # 훅이 도는 세션은 위에서 이미 잡혔으니 같은 세션은 건너뛴다.
        if self.cfg.get("codexWatch", True):
            have = {r.get("session_id") for r in rows if r["source"] == "codex"}
            try:
                extra = [r for r in codex_rows(self.cfg) if r["session_id"] not in have]
            except Exception:                 # 기록이 깨져도 펫은 계속 돈다
                extra = []
            rows.extend(r for r in extra if now - r["ts"] <= STALE_NS)

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
        return ph, title, detail, tr, source, started, r.get("app", "")

    def _poll_status(self):
        active = self._aggregate()
        phase, title, detail, tr, source, started, app = \
            active if active else ("idle", "", "", "", "", 0, "")
        self._transcript = tr
        self.source = source
        self.app = app
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

    def _phase_voice(self, kind):
        """작업 완료·실패에 목소리만 얹는다. 말풍선은 상태 표시를 그대로 둔다.

        완료는 하루에도 수십 번이라 쿨다운을 크게 둔다. 안 그러면 성가시다.
        """
        if not self.cfg.get("voiceEnabled", True) or not self.isVisible():
            return
        now = time.monotonic()
        if now < self._phase_voice_until:
            return
        pool = [i for i in (self.lines.get(kind) or [])
                if isinstance(i, dict) and i.get("v") in self.voice._effects]
        if not pool:
            return
        self._phase_voice_until = now + PHASE_VOICE_COOLDOWN_S
        self.voice.play(random.choice(pool)["v"])

    def _apply_phase(self, phase, prev):
        if phase != prev:
            self._notice()          # 작업이 끝나거나 막혔으면 알릴 겸 이쪽을 본다
        if phase == "done":
            if prev != "done":
                self._begin_done()
                self._phase_voice("done")
        elif phase in ("working", "waiting", "failed"):
            target = PHASE_ANIM[phase]
            if self.anim != target:
                self._enter(target)
            if phase == "failed" and prev != "failed":
                self._phase_voice("failed")
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
            got = _assistant_text(d)
            if got:
                text = got
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
            self._throw = self._hop = self._climb = None
            self._shelf = self._climb_intent = None   # 들어올린 순간 발판에서 떨어진다
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
        if self._begin_throw():
            return
        # 살짝 놓았을 뿐이면 그 자리에서 떨어진다 — 아래 창이 있으면 그 위에 올라선다
        if self.phase == "idle" and self.y() < self._y_on(self._screen().bottom()) - 4:
            self._fall()
        else:
            self._rest(random.randint(2000, 4000))   # 놓자마자 걸어가면 어색하니 잠시 서 있는다

    def contextMenuEvent(self, e):
        """펫을 우클릭했을 때. '지금 시켜 보는 것'과 자주 만지는 것만 둔다.

        설정은 항목이 계속 늘어 메뉴로는 감당이 안 돼서 설정 창으로 옮겼다.
        여기 남긴 크기·투명도·펫 바꾸기는 눈으로 보며 맞추는 것이라 손에 닿는 자리가 낫다.
        """
        m = QtWidgets.QMenu(self)
        m.setStyleSheet(MENU_QSS)
        m.setWindowFlag(QtCore.Qt.NoDropShadowWindowHint, False)
        a_wave = m.addAction(T("손 흔들기")); a_jump = m.addAction(T("점프"))
        a_climbnow = m.addAction(T("벽 타 보기"))
        a_hopnow = m.addAction(T("창 위로 올라가 보기"))
        a_hopnow.setEnabled(bool(self._shelf_candidates()))
        a_panel = m.addAction(T("작업 목록 열기"))
        m.addSeparator()
        m.addAction(SliderAction(m, self, "size"))
        m.addAction(SliderAction(m, self, "opacity"))
        self._music_menu(m)

        pets = pet_list()
        if len(pets) > 1:                       # 갈아탈 펫이 있을 때만 보여준다
            pm = m.addMenu(T("펫 바꾸기"))
            cur = self.cfg.get("pet", "")
            pet_acts = {}
            for pid, name in pets:
                a = pm.addAction(name)
                a.setCheckable(True); a.setChecked(pid == cur)
                pet_acts[a] = pid
        else:
            pet_acts = {}
        m.addSeparator()

        a_wander = m.addAction(T("자유롭게 돌아다니기"))
        a_wander.setCheckable(True); a_wander.setChecked(bool(self.cfg.get("wander", True)))
        a_chat = m.addAction(T("대사"))
        a_chat.setCheckable(True)
        a_chat.setChecked(bool(self.cfg.get("chatEnabled", True)))
        m.addSeparator()
        a_settings = m.addAction(T("설정…"))
        a_quit = m.addAction(T("종료"))
        act = m.exec(e.globalPos())
        if act in pet_acts:
            self._switch_pet(pet_acts[act]); return
        if act == a_wander:
            self.set_option("wander", not self.cfg.get("wander", True))
        elif act == a_chat:
            self.set_option("chatEnabled", not self.cfg.get("chatEnabled", True))
        elif act == a_settings:
            self._show_settings()
        elif act == a_panel:
            self._toggle_panel()
        elif act == a_climbnow:
            self._try_climb(force=True)
        elif act == a_hopnow:
            self._try_hop()
        elif act == a_wave:
            self._enter("waving", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
        elif act == a_jump:
            self._enter("jumping", oneshot_after=PHASE_ANIM.get(self.phase, "idle"))
        elif act == a_quit:
            self._quit()


def main():
    # encoding을 지정하지 않으면 윈도우에서 cp949로 써서 한글 경로·곡명이 깨진다
    logging.basicConfig(filename=os.path.join(BASE, "yui_pet.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")

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
