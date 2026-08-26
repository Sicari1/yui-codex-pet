<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="preview/logo-dark.png">
  <img src="preview/logo-light.png" width="360" alt="Yui Codex Pet">
</picture>

A desktop pet that mirrors what your **Claude Code** and **Codex** agents are doing.

**English** · [한국어](README.ko.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

A small character lives on your desktop and shows what your coding agent is doing —
**Claude Code** and **Codex** both. When the agent starts working, she starts working.
When it stops and waits for your answer, she turns and waits too. When something fails,
you see it from across the room without switching windows.

The window is transparent and always on top, so it sits over whatever you are doing
without covering it. Built with **PySide6** (Qt) on Windows; the hooks that feed it run
in WSL.

<p align="center">
  <img src="preview/overlay-states.gif" width="420" alt="pet reacting to agent status: working, waiting, error"/>
</p>
<p align="center"><sub>Real capture. <b>Working</b> shows the project name and elapsed time, <b>waiting</b> turns orange, an <b>error</b> turns red, and <code>≡ N</code> appears when several sessions are running at once.</sub></p>
<p align="center">
  <img src="preview/all-states.gif" width="240" alt="animation states"/>
  &nbsp;
  <img src="preview/16-directions.gif" width="240" alt="sixteen look directions"/>
  <br><sub>Nine animation states, sixteen look directions.</sub>
</p>

---

## The status it mirrors

Claude Code writes its phase to a small file through a hook; Codex needs no setup at all,
because the overlay reads the logs Codex already keeps. Either way the overlay polls and
plays the matching animation.

| Your agent | The pet | |
|---|---|:---:|
| idle, or no session open | relaxes | <img src="preview/states/00-idle.png" width="90"/> |
| working | works away | <img src="preview/states/07-active-work.png" width="90"/> |
| waiting for your input | looks over and waits | <img src="preview/states/06-waiting.png" width="90"/> |
| reviewing, wrapping up | reads through | <img src="preview/states/08-review.png" width="90"/> |
| hit an error | reacts | <img src="preview/states/05-failed.png" width="90"/> |
| switching tasks | runs across | <img src="preview/states/01-running-right.png" width="90"/> |
| greeting you | waves | <img src="preview/states/03-waving.png" width="90"/> |

Run four sessions and you get one pet, not four. The overlay ranks them
`waiting > failed > working > done > idle` and shows the one that needs you soonest,
with a session count in the corner.

## The cast

Right-click to switch. Only characters you have art for appear in the menu.

<p align="center">
  <img src="preview/roster.png" width="720" alt="the five pets side by side"/>
</p>

| | Pet | Identity | Package |
|:---:|---|---|---|
| <img src="preview/pets/yui-idle.png" width="80"/> | **Hirasawa Yui** | right-handed Gibson Les Paul | `pets/yui/` |
| <img src="preview/pets/mio-idle.png" width="80"/> | **Akiyama Mio** | left-handed sunburst Jazz Bass | `pets/mio/` |
| <img src="preview/pets/ritsu-idle.png" width="80"/> | **Tainaka Ritsu** | drumsticks, Mellow Yellow Hipgig kit | `pets/ritsu/` |
| <img src="preview/pets/tsumugi-idle.png" width="80"/> | **Kotobuki Tsumugi** | KORG TRITON Extreme 76-key | `pets/tsumugi/` |
| <img src="preview/pets/azusa-idle.png" width="80"/> | **Nakano Azusa** | Candy Apple Red Fender Mustang | `pets/azusa/` |

<details>
<summary><b>All nine states, per character</b></summary>
<p align="center">
  <img src="preview/pets/yui-all-states.gif" width="240" alt="Yui, nine states"/>
  <img src="preview/pets/mio-all-states.gif" width="240" alt="Mio, nine states"/>
  <img src="preview/pets/ritsu-all-states.gif" width="240" alt="Ritsu, nine states"/>
  <img src="preview/pets/tsumugi-all-states.gif" width="240" alt="Tsumugi, nine states"/>
  <img src="preview/pets/azusa-all-states.gif" width="240" alt="Azusa, nine states"/>
</p>
<p align="center"><sub>idle · running-right · running-left · waving · jumping · failed · waiting · active-work · review</sub></p>
</details>

The `pet.json` manifests are here so you can read the package format. The spritesheets
are not; see [Bring your own sprite](#bring-your-own-sprite).

## What else it does

It wanders across the screen when nothing is happening and blinks at irregular intervals.
It climbs onto the top edge of your windows and walks along them, and scales the screen
edges. Grab it and it runs in the direction you drag; let go while moving and it flies off
on an arc and bounces at the edge of the screen.

It looks at you when the mouse comes close. Three to five seconds when the cursor arrives,
when you click, or when the status changes. Not continuously, and never first while you're
typing.

The right-click menu has wave, jump, climb a wall, Pomodoro (25 on, 5 off), switch pets and
the music player. Everything else is in a settings window: language, size, opacity, click
behaviour, which autonomous behaviours are on, dialogue and voice, music folders,
agent-status options. It also sits in the system tray, which is how you get click-through
back off once it's on.

It plays audio from your own folders in a player window, with search, shuffle and filtering
by song, instrumental or background music. Music ducks while the pet speaks.

The interface and the pet's dialogue can be Korean, English or Japanese, switched live with
no restart.

The bubble carries the task title and a line of detail. `privacyMode` is on by default, so it
describes the tool action rather than quoting your conversation. Turn it off in `config.json`
to see the real text. Set `showJapanese` and the bubble carries a Japanese line under the
Korean one.

It hides itself when a fullscreen app takes over, and comes back after.

## How it works

```
Claude Code hook ──▶ sessions/<source>/<session_id>.json   (a small PetState file)
                                │   (each session writes its own)
                                ▼
                     overlay polls and aggregates by priority
                (waiting > failed > working > done > idle)
                                ▼
                       animated pet + speech bubble
```

```
PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}
phase    = idle | working | waiting | done | failed
```


## Install

```bash
./install.sh          # deploys the overlay and registers the Claude Code hooks
./install.sh --dry-run
```

You need Python and PySide6 on the Windows side; the hooks run in WSL. Existing hooks in
your `settings.json` are preserved, and `--uninstall` takes it all back out.
`overlay/README.md` has the details.

## Drive it from your own scripts

The bundled `yui` CLI writes the same `PetState`. Wrap a long-running job with it and the
pet shows that job's state:

```bash
yui start "training"                     # switches to working
yui done  "training" "3 epochs finished" # green check, then a wave
yui fail  "build"    "tests failed"      # red
yui wait  "needs a decision"             # orange, looks over at you
yui clear                                # back to idle

# or wrap a command; the exit code decides done/fail and is passed through
yui run -t "training" -- python train.py
```

Each caller writes to `sessions/cli/<id>.json`. A CLI job and three Claude Code sessions
coexist without stepping on each other.

## Switching pets

Right-click the pet, then **펫 바꾸기** (*Change pet*). The choice is saved to
`config.json`:

```jsonc
{ "pet": "" }        // "" = the default sheet at the deploy root
{ "pet": "ritsu" }   // = pets/ritsu/spritesheet.webp
```

The overlay finds packages by scanning the deployed `pets/*/` for a manifest and a sheet:

```text
~/.yui-pet/
├── spritesheet.webp        ← default pet, at the deploy root
├── config.json
└── pets/
    ├── mio/{pet.json, spritesheet.webp}
    ├── ritsu/{pet.json, spritesheet.webp}
    └── …
```

A manifest is five fields:

```json
{
  "id": "ritsu",
  "displayName": "Tainaka Ritsu",
  "description": "…",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

Drop in a folder with those two files and it appears in the menu. No code change, and no
per-pet tuning: every pet shares one timing table and one `lines.json`.

## Bring your own sprite

The runtime loads a Codex Pet v2 atlas named in `pet.json`. **That art is not shipped
here.** `SPRITE_SPEC.md` has the full spec — 1536×2288, 8×11 cells of 192×208, nine state
rows and two look rows — so you can draw your own character, or point the loader at any
sheet you have the rights to.

## What's in here

| Path | |
|---|---|
| `overlay/yui_pet.py` | the PySide6 transparent overlay |
| `overlay/config.json`, `lines.json` | display settings and editable dialogue |
| `hooks/` | status writers shared by Claude Code and Codex, recording each session's `PetState` |
| `tools/` | hook registration helper, the `yui` CLI, a sprite upscaler |
| `pets/*/pet.json` | package manifests for the five characters |
| `preview/` | state animations, look directions, cast roster |
| `SPRITE_SPEC.md` | the atlas spec, for drawing your own |
| `install.sh` | one-command deploy |
| `README.{ko,ja,zh-CN}.md` | the same README in Korean, Japanese, and Simplified Chinese |

## License

- Code — MIT © 2026 SeongJin Kim (`LICENSE`)
- Font — `PretendardVariable.ttf` by Kil Hyung-jin, SIL Open Font License
- Character art — *K-ON!* characters, rights held by their owners (© Kakifly · Houbunsha ·
  TBS · Kyoto Animation). Fan-made and non-commercial, offered under no license. Only
  low-resolution previews are published; the spritesheets are not distributed.
