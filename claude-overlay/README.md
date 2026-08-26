# The overlay (Yui desktop pet)

A transparent overlay that draws a Codex Pet v2 sprite on the Windows desktop and
**shows what your Claude Code agent is doing**. Rendering is PySide6; the hooks that
feed it run in WSL and write status to files, which the overlay polls and turns into
animation and speech bubbles.

## Files

- `yui_pet.py` — the PySide6 transparent overlay: sprite animation, cursor-following
  gaze, drag-to-move, speech bubbles.
- `config.json` — display settings.
- `lines.json` — the dialogue list. Edit it freely.
- `유이펫-시작.bat` — launches without a console window (via `pythonw`).
- `../hooks/yui-pet-status.py`, `../hooks/yui-pet-status.sh` — the status writers the
  hooks call.

## How it works

```
Claude Code hook ──▶ sessions/<source>/<session_id>.json   (a shared PetState)
                              │  (each session writes its own)
                              ▼
                    overlay aggregates by priority
             (waiting > failed > working > done > idle)
                              ▼
                      pet animation + speech bubble
```

```
PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}
phase    = idle | working | waiting | done | failed
```

A badge on the left of the bubble says **which tool produced the status** — Claude Code
gets its logo plus `Claude`, the `yui` CLI gets `CLI`. The icon comes from
`icons/claude.png`; without it you get the text alone. Things the pet says on its own
carry no badge.

Phase to animation: working → heads-down work / waiting → waiting, orange / done →
review, green check, wave, back to idle / failed → failure, red dot / idle → breathing
plus cursor-following gaze.

## Setup

1. **Lay out the app and assets** in a deployment folder, e.g. `C:\Users\<user>\.yui-pet\`:
   - `yui_pet.py`, `config.json`, `fonts/`
   - `spritesheet.png` (or `.webp`) — **not in this repository.** Follow `SPRITE_SPEC.md`
     and draw your own, or supply a v2-format sheet you hold the rights to.
   - optional high-resolution `spritesheet-4x.png`, which stays sharp when scaled up.
     Generate it with `tools/upscale_spritesheet.py`. When present, the loader prefers
     `-4x` → `-3x` → `-2x` → the base sheet.
2. **Install PySide6** for the Windows Python you plan to run it with, e.g.
   `"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m pip install PySide6`
3. **Register the Claude Code hooks** in `~/.claude/settings.json`, one status writer per
   event. Existing hooks are preserved.
   - `UserPromptSubmit`, `PreToolUse`, `PostToolUse` → `bash <hooks>/yui-pet-status.sh working`
   - `Notification` (matchers `permission_prompt`, `elicitation_dialog`) → `… needs_input`
   - `Stop` → `… done` / `StopFailure` → `… error` / `SessionStart` → `… idle`
   - Point the writer at the deployment folder with the script's second argument or the
     `YUI_PET_DIR` environment variable. With neither, it looks for `/mnt/c/Users/*/.yui-pet`.
4. **Run it** — double-click `유이펫-시작.bat`, or from WSL:
   `setsid pythonw.exe "C:\…\yui_pet.py" </dev/null >/dev/null 2>&1 &`.
   A plain `&` dies with the shell, so it has to be detached.

## Wandering

While `idle` — that is, when the agent isn't working — the pet moves around on its own:
rest, pick a direction, walk, arrive, rest again. Now and then it jumps or waves. The
blink interval is jittered between 2 and 5.5 seconds so it doesn't look mechanical.

**Not interrupting you comes first, so it reads your input and behaves two different ways.**

| Situation | Test | Behaviour |
| --- | --- | --- |
| You're working | Keyboard or mouse input within the last 25 s | Rests 40–110 s, walks only short hops (60–170 px), 26% chance of walking at all |
| Your hands stopped | No input for over 25 s | Rests 9–30 s, walks 90–340 px, 55% chance |

It doesn't move at all while showing agent status, while held, or while hidden.
Turn it off from the right-click menu or the tray — **자유롭게 돌아다니기** (*Wander freely*),
stored as `wander` in `config.json`.

## Dialogue

While `idle` the pet occasionally says something. Four seconds after launch it greets you
according to the time of day; after that, talking is just one of the things wandering can
pick, at low probability. With no input for over ten minutes it switches to the bored lines.

Lines live in `lines.json` and are yours to edit — delete it and the defaults are written
back. Each entry is `{"ko": "…", "ja": "…"}`, and the bubble shows the Korean in bold with
the Japanese under it in grey. Set `showJapanese` to `false` in `config.json` for Korean only.

| Category | Contents |
| --- | --- |
| `morning` `afternoon` `evening` `night` `lateNight` | Time-of-day greetings |
| `bored` | No input for over ten minutes |
| `idleChat` | Ordinary day-to-day lines |
| `quotes` | **Actual lines from the show.** Mixed with the ordinary ones at roughly 4:6 |
| `special` | Anniversaries, keyed `"MM-DD"` — the character's birthday on 11-27, Christmas, New Year |

The dialogue and persona were written against the source material, and the Korean prefers
the dub and established fan translations. There is no voice playback in this build; the
design for it is in `ROADMAP.md` §2-D.

The `_persona` entry holds a summary of the character to write against when you add lines.
This is a non-commercial fan project, and quotation is limited to short lines.

Time-of-day bands: 05–11 morning, 11–17 afternoon, 17–21 evening, 21–02 night,
02–05 late night. The pet stays quiet while an agent-status bubble is up.

## Pomodoro

Start it from the tray menu — **뽀모도로 시작** (*Start Pomodoro*). It alternates 25 minutes
of focus with a 5-minute break (`pomodoroFocusMin` and `pomodoroBreakMin` in `config.json`).

During focus the pet says nothing at all. The remaining time appears **only in the tray
tooltip** — a bubble that never goes away is exactly the interruption you were avoiding.
It speaks and waves only when an interval ends.

## Notification CLI

Drop `tools/yui` at `~/.local/bin/yui` and any script can tell the pet it finished. It is a
thin wrapper that writes the same `PetState` into `sessions/cli/`, so the overlay picks it up
with no extra wiring.

```bash
yui run -t "training" -- python train.py   # shows working, then done/failed by exit code
yui start "rendering"                       # set status by hand
yui done  "rendering" "took 12 minutes"
yui fail  "build" "tests failed"
yui clear
```

`run` passes the exit code straight through, so it is safe to wedge into a pipeline.
Running several at once, distinguish them with `YUI_ID`; display duration is `YUI_TTL`
in seconds.

## Tray icon

The pet lives in the tray so you can get it back after losing it off-screen or behind a
window. Double-click the icon to toggle hidden/shown; the right-click menu has
**펫 보이기** (*Show pet*), **자유롭게 돌아다니기** (*Wander freely*),
**부팅 시 자동 실행** (*Start with Windows*) and **종료** (*Quit*).

Start-with-Windows touches no registry key — it adds and removes a single batch file in the
startup folder (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\유이펫.bat`).

## Fullscreen apps

When a window covers the whole screen — a game, a video — the pet hides itself within
1.5 seconds and comes back when you leave. The desktop and the taskbar don't count as
fullscreen.

## Task list

With several jobs running, **☰ N** appears to the right of the bubble. **Click the pet** to
open the list (that's the default click action). Each row shows the source (Claude logo or
CLI), the title, what it's doing right now, and its status; clicking a row raises or lowers
that job's window.

Click again, or move the cursor away from both the pet and the list, and it folds away.
It keeps updating while open. Clicking with nothing running gets you a remark instead of an
empty list.

Window lookup matches on title first and falls back to an editor or terminal window.
Several Claude Code sessions are often terminals inside one editor window, so sessions do
not necessarily have a window each.

## Interaction

| Action | Result |
| --- | --- |
| Click | Depends on `clickAction` — `panel` (task list, default), `app` (raise the app window), `talk` (say something), `none`. A line triggered by clicking appears **even while agent status is showing** |
| Click again mid-line | Ends the line immediately and returns to the status display. No waiting |
| Three clicks within 1.4 s | Delighted, jumps |
| Cursor arriving very close | Startled. A 25-second cooldown keeps it from being annoying |
| Drag and throw | Only flies **if you really fling it** — over 1400 px/s and still moving when you let go. Ordinary repositioning won't trigger it. Can be disabled from the right-click menu |
| Right-click | Menu — wave, jump, wander, size, opacity, change pet, click action, click-through, quit |

Turning on **클릭 통과** (*click-through*) makes the pet pure decoration. The mouse passes
through it, which means the right-click menu is gone too — the tray icon is the only way back.

## Changing pets

Put a `pet.json` and a sprite sheet in `.yui-pet/pets/<id>/` and the pet appears in the
right-click menu automatically. `pet.json` files whose `displayName` collide (two entries
both called "유이", say) are disambiguated in the menu with the folder name in parentheses —
"유이 (기본)", "유이 (치비)". Add a friendlier label to `PET_LABELS` in `yui_pet.py`.

## Weather lines

Set `weatherEnabled` to `true` in `config.json`. Lines that react to rain, snow, heat and
cold are then mixed into the ordinary dialogue. It uses Open-Meteo, which needs no API key,
calls once an hour, and fails silently. `weatherLat` and `weatherLon` default to the old
Toyosato Elementary School in Shiga — the building Sakuragaoka High is drawn from. Set them
to where you actually are.

## Resizing

Right-click the pet and drag the **size bar**; it grows and shrinks live. Release and the
value is saved to `config.json` and survives a restart. It grows from a fixed foot line, so
it never gets pushed off screen.

The ceiling is whatever the sheet supports — 1.7× with only the base (1×) sheet, up to 4×
(832 px) with `spritesheet-4x.png` present.

Clicks are only accepted on the character silhouette. The window keeps the cell aspect
(192×208), which leaves wide transparent margins on either side; at 832 px that's 180 px a
side of empty space that would otherwise swallow clicks meant for the window behind. A mask
built from the alpha channel lets the margin through — it is generated from a downscaled
copy and cached, so it stays under 4 ms regardless of size.

> **Filename trap:** never suffix the high-resolution sheet `@2x` or `@4x`. Qt reads it as a
> high-density asset and raises `devicePixelRatio`, so the window grows while the artwork is
> drawn at 1/N size with the rest left unpainted. Use the `-4x` form. The code also calls
> `setDevicePixelRatio(1.0)` right after loading as a second guard.

## config.json

| Key | Meaning |
| --- | --- |
| `petHeight` | Display height in px. The size bar writes this. Past the sheet's scale it goes soft. |
| `bubbleWidth` | Maximum bubble width. |
| `bubbleMaxLines` | Maximum bubble lines; the rest is ellipsised. |
| `completedDisplaySeconds` | How long the green completion check stays up. |
| `wander` | `true` (default) lets it walk around while idle. |
| `opacity` | 0.2–1.0. Tied to the opacity bar in the right-click menu. |
| `clickAction` | On click — `panel` (default), `app`, `talk`, `none`. |
| `clickThrough` | `true` lets the mouse pass through. Only the tray can undo it. |
| `pet` | Which pet to use. Empty means the default sheet at the deploy root; otherwise `pets/<id>/`. |
| `throwEnabled` | `false` means no fling, however hard you throw. |
| `pomodoroFocusMin` · `pomodoroBreakMin` | Pomodoro focus and break minutes. |
| `weatherEnabled` · `weatherLat` · `weatherLon` | Weather lines. Off by default. Coordinates default to the old Toyosato Elementary School; set them to your own location. |
| `privacyMode` | `true` (default) shows the **project name** as the title and only **filename plus the kind of work** as detail. Prompt text, responses, raw notification text and English tool descriptions never reach the screen. `false` uses the session's first prompt as the title and fills the progress line from the conversation. |

## Other agents

Anything that writes the same `PetState` into `sessions/<source>/…` is aggregated
automatically — Codex, an editor extension, a CI job, your own script. The source name is
what drives the badge.
