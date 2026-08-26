# Roadmap: growing this into a desktop pet

Last updated: 2026-08-26 (translated to English; private-repo references removed)

Ideas for widening this from a Claude Code status indicator into **a pet you actually keep
around**. Split by what the current implementation can already reach and what needs new
artwork first. Redrawing the sprites gates several items, so the drawing list is settled here.

---

## 0. Design principles

Desktop pets usually get uninstalled because they're irritating. Cute comes after that,
which is why the order is:

1. **Don't interrupt** — never eat a click, disappear during fullscreen, and be one action
   away from off at any time.
2. **Be alive** — a pet standing still is a wallpaper decal. It has to move on its own.
3. **Be cute** — it has to react. Poke it and something happens; it knows the time and the
   situation.
4. **Be useful** — nice-to-have, not need-to-have. Push this one and you break rule 1.

---

## 1. Reachable now (no new sprites)

### 1-A. Feeling alive: biggest effect per line of code

| Item | What | Effort |
|---|---|---|
| ~~**Jittered blinking**~~ ✅ | The idle loop was a fixed `dur = 2800`, so it blinked like a metronome. Jitter between 2.0 and 5.5 s alone is a big improvement. Cheapest win available. | 5 min |
| ~~**Autonomous wandering**~~ ✅ | Quiet while you're typing, free once your hands stop, decided from input-idle time. Walks along the bottom of the screen. `running-left`/`running-right` already exist. A probabilistic state machine (stand → pick a target → walk → arrive → stand) is enough. | half a day |
| ~~**Occasional idling about**~~ ✅ | Low chance of a jump or a wave while wandering. Reuses `jumping` and `waving`. | 30 min |
| ~~**Throw physics**~~ ✅ | On release, build an arc from the last few frames of drag velocity. Bounce off walls, land on the floor. No landing frames yet, so the last `jumping` frame stands in. | half a day |
| ~~**Stronger cursor reaction**~~ ✅ | It only looked at the cursor from a distance. Make it flinch or wave when the cursor comes right up to it. | 1 hour |

### 1-B. Not being irritating: required for daily use

| Item | What |
|---|---|
| ~~**Tray icon**~~ ✅ | Quit lived only in the right-click menu, so losing the pet off-screen or behind a window meant opening Task Manager. `QSystemTrayIcon` for show/hide, settings and quit. **High priority** |
| ~~**Fullscreen detection**~~ ✅ | Hide during games, video and presentations. Win32 will tell you whether the foreground window covers the screen. |
| ~~**Click-through mode**~~ ✅ | `WA_TransparentForMouseEvents` turns it into pure decoration. Toggle from the right-click menu. Note that once on, only the tray can turn it back off. |
| ~~**Opacity**~~ ✅ | One more slider. Fade it while working. |
| ~~**Configurable click action**~~ ✅ | Clicking used to toggle the VS Code window, which is odd for a desktop pet. Offer none / toggle app / say something. |
| **Multi-monitor** | `_screen()` exists, but repositioning after the pet moves between monitors needs checking. |

### 1-C. Cute: dialogue and a sense of time

| Item | What |
|---|---|
| ~~**Time-of-day greetings**~~ ✅ | First launch in the morning, around lunch, late evening, small hours. |
| ~~**Dialogue pool**~~ ✅ | Several lines per situation (greeting, bored, praise, encouragement) in JSON, picked at random. Reuses the existing bubble. No LLM involved. |
| ~~**Idle reaction**~~ ✅ | Bored lines when left alone for a while, then quiet again. |
| ~~**Rapid-click reaction**~~ ✅ | Several fast clicks and it's delighted, or dizzy. Works with dialogue plus `jumping` even without expression frames. |
| ~~**Anniversaries**~~ ✅ | The character's birthday (27 November), Christmas, New Year. Special lines on the day only. |
| ~~**Weather**~~ ✅ | Lines reacting to rain, snow and heat. Dialogue only, no props, so one API call covers it. |
| **Sound effects** | Footsteps and jumps, roughly. No voice clips lifted from the show, which is a rights problem. |

### 1-D. Useful: reusing the speech bubble

| Item | What |
|---|---|
| ~~**Pomodoro**~~ ✅ | 25 focus / 5 break. Silent during focus, waves when the interval ends. Existing bubble. |
| **Break reminder** | Suggest a stretch after a long sitting stretch. |
| **Timers and alarms** | "Tell me in 20 minutes" level. |
| ~~**General notification CLI**~~ ✅ | `yui done "training finished"`, a thin wrapper writing `sessions/cli/*.json`. Long scripts, renders and builds can all report in. **Nearly free by construction and gets used constantly** |
| **System warnings** | Low battery, low disk, CPU heat. Reuses the `failed` animation. |
| **Calendar reminders** | Google Calendar integration. |
| **Small to-do list** | A few todo lines in the right-click menu; congratulate on completion. |

### 1-E. More status sources: the extension point already exists

Write the same `PetState` into `sessions/<source>/<id>.json` and it is aggregated
automatically. Codex, an editor extension, cron jobs, CI, any pipeline you run, and all of them
can report in the same way. Splitting priority or assigning a character per source is the
path toward the band arrangement.

### 1-F. Swapping pets ✅ (done 2026-07-25)

`pets/chibi-yui/` already exists. The right-click menu switches between the current design
and the chibi one. Building the list from `pet.json` means band members drop in the same way
later.

---

## 2. Needs new artwork first

Everything below this line needs drawings. **Drawing them in one pass during the redraw is
far cheaper.** Adding a few later means the style drifts and they never quite sit together.

### 2-A. Motions to draw (priority order)

| Motion | Why | Frame estimate |
|---|---|---|
| **Sitting** (seated idle + stand↔sit) | Perching on a window title bar. The signature desktop-pet move, and the one most missed today | seated breathing 4–6, transition 3–4 |
| **Playing guitar** | It's the character's whole identity and it isn't there. An occasional short riff while idle carries her by itself | 6–8 |
| **Sleeping / dozing** | Idle and small hours. Nodding off → lying down → Z | doze 4, sleep 4 |
| **Dangling** | While dragged. Currently reuses the running animation; dangling from a grip is what actually happens | 4 |
| **Falling / landing** | Throw physics, and when a window she was on closes | fall 2, land 3 |
| **Startled** | Cursor arriving suddenly, or a window vanishing | 3–4 |
| **Delighted / petting reaction** | Rapid clicks and petting. Eyes shut, smiling | 4–6 |
| **Hanging / climbing** | Screen edges and window corners. The Shimeji signature, but lower priority than the above | 4 each |
| **Mouth flaps** | Adding voice makes a motionless mouth jarring (see 2-D). Real lip-sync is not needed | 2–3 |

### 2-B. ⚠ Sheet layout: don't break Codex compatibility

The current sheet is **8 columns × 11 rows**, which is the Codex Pet v2 format
(`spriteVersionNumber: 2` in `pet.json`). Adding rows can fail Codex's own validation.

**Recommended: split it across two sheets.**

- `spritesheet.png` — the existing 8×11, unchanged. Still usable as a Codex pet.
- `spritesheet-extra.png` — a separate sheet holding only the extra motions above. Read by
  this overlay alone.

The overlay derives cell size from the sheet resolution, so the only requirement is that
both sheets use the same cell size. Add a sheet discriminator to `ROW_DEF` and you're done,
something like `("extra", row, durs)`.

### 2-C. Fix during the redraw: the sixteen-direction failure, measured (2026-07-25)

Checked by cropping each of the sixteen faces at 1:1 against the original. **This is a
generation-quality problem, not a resolution problem**, so upscaling cannot fix it.

| Frame | Intended | Actual |
|---|---|---|
| 13·14·15 (292.5°/315°/337.5°, upper-left) | looking up-left | **nearly front-facing.** Indistinguishable from one another |
| 12 (270°, left) | left profile | hair covers most of the face |
| 6·7 (135°/157.5°) | looking down-right | back of the head only |
| 0–4 (up through right) | | these are fine |

**The left half is markedly worse.** Park the pet on the right of the screen and the cursor
spends most of its time to the left, so the worst frames are the ones you see most.

The direction-semantics QA from that production run (the record itself is private) passed
all of it: the four cardinal directions passed, and the intermediate angles came back with a
"cues are subtle under blind review" warning that was accepted as `"ok": true`. Meanwhile the
overlay carries a `LOOK_REMAP` that snaps 13·14·15 away. QA passed them, using it did not,
and the code quietly covered for it. **The redraw's QA should treat this as the precedent and
accept no warnings.**

Short-term mitigation (not applied): widen `LOOK_REMAP` so the broken frames (6·7·12–15) are
never shown and only the good ones are snapped to. Gaze precision drops; the broken artwork
stops being visible.

---

## 2-D. Voice: designed, not built

Attaching a voice to the dialogue is structurally easy. **Which voice to use is the open
question**, so what follows is a design that stays independent of the audio source. Once a
source is chosen it is a matter of plugging it in.

### Position on audio sources

Extracting and cloning a voice actor's performance from the show is out of scope for this
repository. It is a real person's voice, their consent cannot be verified, and nothing here
gets built on consent that cannot be verified.

What is usable:

| Option | Notes |
|---|---|
| **VOICEVOX** | Free, offline, local HTTP API. The character voices exist for other people to use, so following the terms is the whole requirement. No paid tier as of 2026; credit attribution is the condition. **Terms differ per character; check that character's page before use** |
| COEIROINK / AquesTalk | Same family of alternatives |
| A Korean TTS | Reads the `ko` text directly. May sit better than a Japanese voice |
| Sound effects only | Footsteps, jumps, a short sound when the bubble appears. Lightest and safest |

### How it attaches

`_say(ko, ja)` already funnels every line through one place, so that is the only hook needed.

```
_say(ko, ja) ──▶ show bubble (today)
             └─▶ voice.speak(ja or ko)   ← the only addition
                    │
                    ├ cache lookup (text hash → wav)
                    ├ on miss, ask the engine adapter to synthesise (async)
                    └ play through QMediaPlayer
```

- **Engine adapters** — split into `voicevox` / `coeiroink` / `custom` (generic HTTP).
  VOICEVOX is a two-step `audio_query` → `synthesis`; absorb that inside its adapter.
- **Async is mandatory** — fire through `QNetworkAccessManager` and play from the callback.
  Slow synthesis must not freeze the UI, and anything that arrives late is simply dropped
  (the bubble is long gone).
- **Cache** — few lines, heavily repeated, so store the wav under a hash of the text and
  every later playback is instant. Put it in `.yui-pet/voice-cache/`; edited lines naturally
  produce a new hash.
- **Fail silently** — no TTS running means bubble only. Never an error popup.
- **What to read** — `lines.json` already carries `ja` alongside `ko`, so it can be used
  as-is. Pass `ko` instead if you're using a Korean TTS.

### Proposed config

```json
"voice": {
  "enabled": false,
  "engine": "voicevox",
  "endpoint": "http://127.0.0.1:50021",
  "speaker": 0,
  "field": "ja",
  "volume": 0.7
}
```

Put an on/off toggle and a volume control in the tray menu. Default off, because sound is far
easier to find irritating than wandering is. Stay silent while a fullscreen app is up or the
pet is hidden.

### Knock-on effect for the sprites

Adding a voice makes **a motionless mouth jarring.** The redraw needs `mouth flaps` (2–3
frames) on the 2-A list. Precise lip-sync is unnecessary; opening and closing the mouth
while audio plays is enough.

---

## 3. Sitting on windows: implementation notes

The most characteristically "desktop pet" feature, so it gets its own section.

1. Collect the rectangles of visible windows with `EnumWindows`. `activate_vscode()` already
   does this, so the groundwork exists.
2. Treat each window's **top edge y** as a shelf. The bottom of the screen (above the
   taskbar) is one more shelf.
3. The pet walks along shelves and sometimes sits. At the end of a shelf it turns around or
   drops to the one below.
4. If the window it's sitting on moves, it rides along; if the window closes, it falls.
5. A 500 ms–1 s refresh is plenty. Walking the window list every frame is expensive.

Watch out: frequent window enumeration burns CPU. Cache it, and stop entirely when a
fullscreen app appears.

---

## 4. Suggested order

| Step | What | Why here |
|---|---|---|
| ~~**1**~~ ✅ | ~~Jittered blinking + wandering + occasional idling about~~ (done 2026-07-25) | "Alive" without any new artwork. Cheapest thing with the largest felt difference |
| ~~**2**~~ ✅ | ~~Tray icon + fullscreen detection + start with Windows~~ (done 2026-07-25) | Living with it for a few days is painful without these |
| ~~**3**~~ ✅ | ~~Dialogue pool + time-of-day greetings + idle reaction~~ (done 2026-07-25) | Cute, from code alone |
| ~~**4**~~ ✅ | ~~Notification CLI + Pomodoro~~ (done 2026-07-25) | Becomes useful. Cheap, since it reuses the bubble |
| **5** | **Sprite redraw** (all of 2-A) | This is where the long part starts. Live with 1–4 for a few days first, add whatever you find yourself missing to the list, then begin |
| **6** | Sitting on windows + throw physics + sleeping | After the sitting and falling frames exist |
| **7** | Pet swapping → the band arrangement | Once member sprites exist |

**Steps 1–4 don't have to wait for artwork.** Ship them, live with the pet for a few days,
and fold whatever you end up missing into the 2-A list before starting the redraw.
