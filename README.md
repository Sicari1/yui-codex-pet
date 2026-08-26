# Yui Codex Pet — a Claude Code desktop pet (engine)

A transparent, always-on-top **desktop pet** that reacts to what your **Claude Code**
agent is doing *right now* — idle, working, waiting for your input, reviewing, or
failed. It follows your cursor with its gaze, can be dragged anywhere, pops speech
bubbles with the current task, and merges several concurrent sessions by priority.

Built with **PySide6** (Qt) on Windows, driven by Claude Code hooks running in WSL.

<p align="center">
  <img src="preview/overlay-states.gif" width="420" alt="pet reacting to agent status: working, waiting, error"/>
</p>
<p align="center"><sub>Real capture. The pet mirrors your Claude Code agent: <b>working</b> (with the project name and how long it has been running), <b>waiting</b> for you (orange), an <b>error</b> (red), and it shows the session count (<code>≡ N</code>) when several tasks run at once.</sub></p>
<p align="center">
  <img src="preview/all-states.gif" width="130" alt="animation states"/>
  &nbsp;
  <img src="preview/16-directions.gif" width="130" alt="sixteen look directions"/>
  <br><sub>The nine animation states and the sixteen look directions.</sub>
</p>

---

## What it does — it mirrors your agent's live status

Each Claude Code session writes its phase through a hook; the overlay picks it up and
animates the matching state:

| When your agent is… | Yui… | |
|---|---|:---:|
| **idle / no session** | relaxes | <img src="preview/states/00-idle.gif" width="90"/> |
| **actively working** | works away | <img src="preview/states/07-active-work.gif" width="90"/> |
| **waiting for your input** | looks over and waits | <img src="preview/states/06-waiting.gif" width="90"/> |
| **reviewing / wrapping up** | reads through | <img src="preview/states/08-review.gif" width="90"/> |
| **hit an error** | reacts | <img src="preview/states/05-failed.gif" width="90"/> |
| **switching tasks** | runs across | <img src="preview/states/01-running-right.gif" width="90"/> |
| **greeting you** | waves | <img src="preview/states/03-waving.gif" width="90"/> |

## Features

- **Live agent status** — hooks report each session's phase; the pet animates it in real time.
- **Multi-session priority** — with several Claude Code sessions open, it shows the one that
  needs you most: `waiting > failed > working > done > idle`.
- **Speech bubbles** — surfaces the current task's title/detail so you can glance and know.
- **Cursor-follow gaze** — sixteen look directions track your mouse around the screen.
- **Wander · drag-and-throw · transparent · always-on-top · system tray** — it strolls around when idle, and you can grab and fling it.
- **Swappable pets** — right-click to switch characters (Codex Pet v2 package format).

## The cast

Five characters are animated as one visual set — same atlas format, same nine states,
same timing table. Right-click the pet to switch between the ones you have art for.

<p align="center">
  <img src="preview/roster.png" width="720" alt="the five pets side by side"/>
</p>

| | Pet | Identity | Package |
|:---:|---|---|---|
| <img src="preview/pets/yui-idle.gif" width="80"/> | **Hirasawa Yui** | right-handed Gibson Les Paul | `pets/current-yui/` |
| <img src="preview/pets/mio-idle.gif" width="80"/> | **Akiyama Mio** | left-handed sunburst Jazz Bass | `pets/current-mio/` |
| <img src="preview/pets/ritsu-idle.gif" width="80"/> | **Tainaka Ritsu** | drumsticks · Mellow Yellow Hipgig kit | `pets/ritsu/` |
| <img src="preview/pets/tsumugi-idle.gif" width="80"/> | **Kotobuki Tsumugi** | KORG TRITON Extreme 76-key | `pets/tsumugi/` |
| <img src="preview/pets/azusa-idle.gif" width="80"/> | **Nakano Azusa** | Candy Apple Red Fender Mustang | `pets/azusa/` |

<details>
<summary><b>All nine states, per character</b> — click to expand</summary>
<p align="center">
  <img src="preview/pets/yui-all-states.gif" width="120" alt="Yui, nine states"/>
  <img src="preview/pets/mio-all-states.gif" width="120" alt="Mio, nine states"/>
  <img src="preview/pets/ritsu-all-states.gif" width="120" alt="Ritsu, nine states"/>
  <img src="preview/pets/tsumugi-all-states.gif" width="120" alt="Tsumugi, nine states"/>
  <img src="preview/pets/azusa-all-states.gif" width="120" alt="Azusa, nine states"/>
</p>
<p align="center"><sub>idle → running-right → running-left → waving → jumping → failed → waiting → active-work → review</sub></p>
</details>

> The `pet.json` **manifests** are here so you can see the package format. The
> **spritesheets are not** — see [Bring your own sprite](#bring-your-own-sprite).

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

`PetState = {source, session_id, phase, title, detail, transcript, ts, expires_at?}`

## Run it

```bash
./install.sh          # deploys the overlay + registers the Claude Code hooks
./install.sh --dry-run
```

The overlay needs Python + PySide6 on the Windows side; the hooks run in WSL. See
`claude-overlay/README.md` for details.

## Drive it from your own scripts

Claude Code hooks are only one producer. The bundled `yui` CLI writes the same
`PetState`, so **any** long job can talk to the pet:

```bash
yui start "training"                     # pet switches to working
yui done  "training" "3 epochs finished" # green check, then waves
yui fail  "build"    "tests failed"      # red dot
yui wait  "needs a decision"             # orange, looks over at you
yui clear                                # back to idle

# or wrap a command — the exit code decides done/fail, and is passed through
yui run -t "training" -- python train.py
```

Each caller writes `sessions/cli/<id>.json`; the overlay merges every producer by
priority, so a CLI job and three Claude Code sessions coexist without stepping on
each other.

## Switching pets

Right-click the pet → **펫 바꾸기** (*Change pet*). The choice persists in `config.json`:

```jsonc
{ "pet": "" }        // "" = the default sheet at the deploy root
{ "pet": "ritsu" }   // = pets/ritsu/spritesheet.webp
```

The overlay discovers packages by scanning the deployed `pets/*/` for a `pet.json`
plus a sheet:

```text
~/.yui-pet/
├── spritesheet.webp        ← default pet, deploy root
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

Drop in a folder with those two files and it shows up in the menu — no code change.
All pets share one `lines.json` and one timing table, so a new package needs no tuning.

## What's in here

- `claude-overlay/yui_pet.py` — the PySide6 transparent overlay (renderer).
- `claude-overlay/config.json`, `lines.json` — display settings and editable dialogue.
- `hooks/` — the Claude Code hooks that record per-session `PetState`.
- `tools/` — hook registration helper, a `yui` notification CLI, a sprite upscaler.
- `pets/*/pet.json` — pet package manifests for the five characters (Codex Pet v2 format).
- `preview/` — state animations, the sixteen look directions, and the cast roster.
- `SPRITE_SPEC.md` — the full sprite-atlas spec so you can **draw your own** character.
- `install.sh` — one-command deploy.

## Bring your own sprite

The runtime loads a Codex Pet v2 atlas (`spritesheet.webp`) named in `pet.json`. That
art is **not shipped here** — follow `SPRITE_SPEC.md` to make your own (1536×2288 atlas,
8×11 cells, 9 states, 16 look directions), or point it at any sheet you have rights to.

## Inspiration

Inspired by **Codex Pet v2** and the classic desktop-mascot tradition (Shimeji and
friends). The overlay, the hook-driven live-status architecture, and the animation set
are my own work on top of that idea.

## License & assets

- **Source code** — MIT © 2026 SeongJin Kim (see `LICENSE`).
- **Font** — `PretendardVariable.ttf` by Kil Hyung-jin, under the SIL Open Font License.
- **Character art (previews)** — these depict **Hirasawa Yui, Akiyama Mio, Tainaka Ritsu,
  Kotobuki Tsumugi and Nakano Azusa** from *K-ON!*, characters owned by their rights
  holders (© Kakifly · Houbunsha · TBS · Kyoto Animation). The drawings here are
  **fan-made and non-commercial**, are **not offered under any license**, and shouldn't
  be reused — please make your own character instead. Only low-resolution preview
  animations are published; the spritesheets themselves are not distributed. This
  project is unaffiliated with and not endorsed by the rights holders.
