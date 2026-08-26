# Sprite production spec

What a **high-resolution redraw** of the pet sprites has to satisfy. Written so it can be
handed to an image-generation run as-is.

The high-resolution sheet in use today was upscaled by AI from the 192×208 original, so it
is invented detail — the bigger you draw it, the further it drifts from the source. This
document exists to replace it with real artwork.

---

## 1. Deliverables — three sheets

| File | Size | Purpose |
|---|---|---|
| `spritesheet.png` / `.webp` | **1536 × 2288** (192×208 cells, 8 cols × 11 rows) | The Codex Pet v2 format. Change this size and Codex's own validation rejects it |
| `spritesheet-4x.png` | **6144 × 9152** (768×832 cells, 8 × 11) | For the overlay — stays sharp when scaled up |
| `spritesheet-extra-4x.png` | 768×832 cells, 8 columns fixed, as many rows as needed | Extra motions (§2). **Kept separate so the Codex format stays intact** |

**Draw at 4× (768×832 cells) and downscale to 1536×2288.** The other direction does not
work — you cannot upscale back.

> **Never put an `@2x` / `@4x` suffix in the filename.** Qt reads it as a high-density
> asset, raises `devicePixelRatio`, and you get a window that grows while the artwork is
> drawn at 1/N size. Use the `-4x` form.

---

## 2. Frame layout

### 2-1. Base sheet (8 × 11, 73 frames plus the neutral-look cell)

Changing the row order or the frame counts means changing `ROW_DEF` in the overlay too.
**Keep them as they are unless you have a reason not to.**

| Row | Name | Frames | Per-frame duration (ms) | Playback |
|---|---|---|---|---|
| 0 | `idle` | 6 | 280·110·110·140·140·320 | loop (breathing + blink) |
| 1 | `running-right` | 8 | 120×7·220 | loop |
| 2 | `running-left` | 8 | 120×7·220 | loop |
| 3 | `waving` | 4 | 140·140·140·280 | one-shot |
| 4 | `jumping` | 5 | 140×4·280 | one-shot |
| 5 | `failed` | 8 | 140×7·240 | loop |
| 6 | `waiting` | 6 | 150×5·260 | loop |
| 7 | `running` | 6 | 120×5·220 | loop (heads-down work) |
| 8 | `review` | 6 | 150×5·280 | loop (reviewing) |
| 9 | look 000°–157.5° | 8 | — | still |
| 10 | look 180°–337.5° | 8 | — | still |

Leave unused cells fully transparent.

### 2-2. Extra motion sheet (not drawn yet)

Motions a desktop pet really wants, in priority order.

| Motion | Frames | Used for |
|---|---|---|
| **sitting (hold)** | 4–6 loop | Perching on a window title bar. **The one that's missed most** |
| **sit transition** | 3–4 one-shot | Standing ↔ sitting |
| **playing guitar** | 6–8 loop | It's the character's whole identity and it isn't there. Even a short occasional riff carries her |
| **dozing** | 4 loop | Idle, late night |
| **sleeping** | 4 loop | Long idle |
| **held** | 4 loop | While dragged. Currently reuses the running animation, but dangling from a grip is what it should be |
| **falling** | 2 loop | Throws, and when a window she was on closes |
| **landing** | 3 one-shot | Pairs with the above |
| **startled** | 3–4 one-shot | Cursor arriving suddenly |
| **delighted** | 4–6 one-shot | Rapid clicks, petting. Eyes shut, smiling |
| **mouth flaps** | 2–3 loop | With voice enabled, a still mouth is jarring. Full lip-sync is not needed |
| **hanging** | 4 loop | Screen edges. Lower priority than everything above |

---

## 3. Sixteen look directions — this is what failed last time

Rows 9 and 10 are the sixteen stills of the pet looking toward the cursor.
**0° is up, then clockwise in 22.5° steps.**

```
        0 (up)
   14        2
 12 (left)    4 (right)
   10        6
        8 (down)
```

### What came out last time (measured against the original 1:1)

| Frame | Intended | Actual |
|---|---|---|
| 13·14·15 (292.5/315/337.5°, upper-left) | up and to the left | **nearly front-facing, and indistinguishable from each other** |
| 12 (270°, left) | left profile | hair covers most of the face |
| 6·7 (135/157.5°) | down and to the right | back of the head only |
| 0–4 (up through right) | | these are fine |

**The left half is markedly worse.** Park the pet on the right of the screen and the cursor
spends most of its time to the left, so the worst frames are the ones you see most. The
overlay currently papers over this with `LOOK_REMAP`.

The direction-semantics QA from that production run (the record itself is private) passed
all of it: the four cardinal directions passed outright, and the intermediate angles came
back with a "cues are subtle under blind review" warning that was accepted as `"ok": true`.
**Do not accept that warning this time.**

### Rules for the redraw

1. **Laid out in order, the sixteen frames must sweep a full turn smoothly.** No frame that jumps.
2. **The face must be visible in every frame.** A frame showing only the back of the head is
   unusable for a desktop pet. Convey direction with **the eyes plus a slight head angle**,
   not a full head turn.
3. **Left and right must be unmistakable.** If the three upper-left frames read as
   front-facing, the sheet has failed.
4. With the labels hidden, up/down and left/right must each still read correctly.

---

## 4. Alignment — this is what makes or breaks the animation

Measuring the original shows **the foot line sits at the same y in every frame.** Match that.

```
idle f0    x  45–145   y   5–202   feet 202
idle f3    x  46–145   y   5–202   feet 202
run-R f0   x  34–156   y   5–202   feet 202
wave f0    x  49–141   y   5–202   feet 202
```

- **Fixed foot line** — y=202 in a 208-tall cell (y=808 at 4×, cell height 832). Let it wobble
  per frame and the pet bounces vertically as it walks.
- **Fixed horizontal centre** — keep the character near the middle of the cell. Deliberate
  displacement, like the jump arc, is the exception.
- The character occupies about half the cell width (101 of 192). Leave the side margins as
  they are — the overlay builds its click hitbox from the alpha channel, so empty margin
  does not swallow clicks.

---

## 5. Alpha and colour

- **A real alpha channel.** Transparent background, no matte (white or green fringing).
- No coloured halo on the silhouette. If it came off a chroma key, despill it before delivery.
- Semi-transparent pixels (hair tips and the like) are fine — the overlay uses the alpha directly.
- Save lossless: PNG RGBA, or WebP with the lossless option.

---

## 6. Character consistency

Match the high-resolution reference stills produced for the original run (912×1724 and
1024×1536). **They are not in this repository** — the reference and deliverable artwork is
private. Redrawing from scratch means establishing your own reference first.

The written constants for the default character:

- **Guitar**: Gibson Les Paul Standard, heritage cherry sunburst. **Right-handed** — never mirror it.
- **Hairpins**: yellow, right side of the head. Always present; they are part of the character.
- **Uniform**: Sakuragaoka winter set — navy blazer, white shirt, **light-blue ribbon**, grey
  skirt, black tights, brown shoes.
- Short brown hair, brown eyes.
- Keep the drawing style in the same family as the existing sheet. It should not look freshly redrawn.

---

## 7. QA checklist

All of it has to pass before delivery. One warning means redraw.

- [ ] Sheet is exactly 6144×9152 (4×) / 1536×2288 (base)
- [ ] No frame's pixels cross a cell boundary
- [ ] Foot line identical in every frame (y=808 at 4×)
- [ ] Unused cells fully transparent (alpha 0)
- [ ] No coloured halo, no matte
- [ ] Playing each animation row at its stated timing produces no jumping frame
- [ ] Walk-left and walk-right each look natural in their own right, not mirrored (the guitar must not flip)
- [ ] **The sixteen look directions sweep a full turn smoothly when played in order**
- [ ] **The face is visible in all sixteen** — no back-of-head frames
- [ ] **Up/down and left/right still read with the labels hidden** (three independent reviewers)
- [ ] No `@Nx` in any filename
- [ ] Downscaling to 192×208 does not mush the silhouette (checks the Codex format)

---

## 8. Production notes

- High-resolution rendering and upscaling want a machine with a current NVIDIA GPU; on
  anything less this stage dominates the schedule.
- `tools/upscale_spritesheet.py` needs CUDA. Once real artwork exists, that tool is obsolete.
- When the redraw lands, update `pets/yui/` and discard the upscaled `spritesheet-4x.png`.
- The overlay derives cell size from the sheet resolution, so as long as the format matches
  it **loads with no code change.**
