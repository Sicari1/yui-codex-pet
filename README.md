# Yui Codex Pet — a Claude Code desktop pet (engine)

A transparent **PySide6 desktop overlay** that shows your Claude Code agent's live
status as an animated character — idle, working, waiting for you, or done — driven by
Claude Code hooks. It tracks your cursor with its gaze, can be dragged around, shows
speech bubbles, and aggregates multiple concurrent sessions by priority.

This repository is the **engine + sprite spec** — the runtime, hooks, and tooling.
The character artwork is intentionally **not** included (see *License & assets*).

## Preview

![All animation states](preview/all-states.gif)
![Sixteen look directions](preview/16-directions.gif)

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

## What's in here

- `claude-overlay/yui_pet.py` — the PySide6 transparent overlay (renderer): sprite
  animation, cursor-follow gaze, drag-to-move, speech bubbles.
- `claude-overlay/config.json`, `lines.json` — display settings and editable dialogue.
- `hooks/` — the Claude Code hooks that record per-session `PetState`.
- `tools/` — hook registration helper, a `yui` notification CLI, and a sprite upscaler.
- `pets/*/pet.json` — pet package manifests (Codex Pet v2 format).
- `SPRITE_SPEC.md` — the full sprite-atlas specification so you can **draw your own**
  character (1536×2288 atlas, 8×11 cells, 9 states, 16 look directions).
- `install.sh` — one-command deployment.

## Bring your own sprite

The runtime loads a Codex Pet v2 atlas (`spritesheet.webp`) referenced by `pet.json`.
That art is not shipped here — follow `SPRITE_SPEC.md` to make your own, or point it at
any Codex Pet v2 sprite sheet you have the rights to use.

## Inspiration

Inspired by **Codex Pet v2** and the classic desktop-mascot tradition (Shimeji and
friends), with my own overlay/hook architecture and animation set built on top.

## License & assets

- **Source code** — MIT © 2026 SeongJin Kim (see `LICENSE`). Please keep the credit.
- **Bundled font** — `PretendardVariable.ttf` by Kil Hyung-jin, under the SIL Open Font
  License (freely redistributable).
- **Preview images** — © 2026 SeongJin Kim. They illustrate my own sprite work and are
  **not** licensed for reuse; please make your own art.
- **Hirasawa Yui / K-ON!** are © Kakifly · Houbunsha · TBS · Kyoto Animation. This is a
  **non-commercial fan project** and is not affiliated with or endorsed by the rights holders.
