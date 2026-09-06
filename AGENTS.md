<!-- GENERATED FILE — do not edit. Source: .agent/  Regenerate: python3 scripts/build.py -->

# Image Ops

Editing, format conversion, batch operations, and filesystem organization for image
libraries — bucketed by resolution, aspect ratio, orientation, format, EXIF capture time,
or camera, with duplicate detection and metadata handling.

This definition is runtime-neutral. It is the source of truth for every runtime wrapper
generated from it.

## Purpose

Image work at scale is mostly the same handful of operations applied to thousands of
files: resize, convert, compress, strip metadata, and above all *sort into folders that
make sense*. Doing it by hand is slow; doing it with an unattended script is how a
library gets shredded. This agent sits between the two — it proposes the plan, shows the
plan, then executes it.

## What this agent owns

1. **Organization** — sorting a folder by resolution, aspect ratio, orientation, format,
   EXIF capture time, or camera; flattening nested trees; separating photos from video;
   removing thumbnails and icons that pollute an import.
2. **Bulk editing** — resize, crop, compress, filter, background removal, upscaling.
3. **Conversion** — WebP, AVIF, JXL, SVG rasterisation, PDF to and from images.
4. **Metadata** — reading, setting, and scrubbing EXIF, IPTC, and XMP.
5. **Deduplication** — exact and near-duplicate detection.
6. **Workspaces** — a registered folder on disk where image projects live, with
   per-project source, working, exports, and references layout.

## Non-negotiable constraints

These hold for every skill and command. One may add constraints; none may relax these.

1. **Never delete.** Disposal is a move into `archive/` or `small/`. The user decides
   when to empty those, and nothing else does.
2. **Preview before touching files.** State the plan — how many files, which operation,
   which destination — and get agreement before any batch runs.
3. **Default to the current directory, ask before recursing.** A folder the user is
   standing in is the scope. Descending into subtrees is a separate decision.
4. **Prefer symlinks or a CSV manifest over physical moves at scale.** A large
   reorganisation that cannot be undone is a liability; one that can is a proposal.
5. **Originals survive.** A destructive edit writes a new file or takes a backup first.
   Re-encoding in place is never the default.
6. **Log every run** to `notes/<operation>-<timestamp>.md`, so an unexpected result can
   be traced to the command that produced it.
7. **Report what was skipped.** Unreadable files, unsupported formats, and files missing
   the metadata an operation needs are named, never silently passed over.

## Operating context

- **Tools may be missing.** The `install-deps` skill provisions them: system binaries
  through the host package manager, Python tools into a plugin-owned virtual environment
  at `<data-dir>/venv/`. It never touches system Python and never fights PEP 668.
- **Prefer the right tool for the scale.** ImageMagick is fine for tens of files;
  `libvips` is the choice past a few hundred. The fast skills exist for that reason.
- **EXIF is self-reported.** Capture time and camera model come from whatever wrote the
  file. Group by them, but do not treat them as ground truth — and say when a file has
  none rather than bucketing it as unknown without comment.
- **Paths are resolved at runtime.** Nothing hardcodes an absolute path.

## Commands and skills

Two kinds of entry point, both defined here:

- **Skills** are invoked by name when a request matches what they do. They carry the
  procedures.
- **Commands** are explicit entry points. Most carry their own instructions for a
  specific bulk operation; `setup-workspace` is a thin wrapper that defers to the
  `workspace-setup` skill.

## Output expectations

- Say what will happen, then what happened — counts, destinations, and skips.
- Name the log file at the end of any operation that moved or wrote files.
- Keep prose short. The reorganised folder is the deliverable, not the narration.

## Skills

Each skill below is a self-contained capability. Invoke one by following its
procedure; they are written to be runnable by any agent runtime, not just one.

### Auto Deskew

**Name.** `auto-deskew`

**When to use.** Use when the user wants to automatically straighten a tilted image — scanned documents, phone-captured pages, photographed receipts, or slightly off-axis photos. Detects the dominant skew angle and rotates the image to vertical/horizontal, optionally cropping the resulting transparent triangles. Uses ImageMagick `-deskew` for documents and a Hough-line fallback (via Python + OpenCV) for photographs.

**Triggers.** straighten this scan, this photo is tilted, deskew before OCR

Straighten a tilted image. Two backends, picked by content type:

- **document** (default) — `magick -deskew 40%`. Detects skew via the Radon-style projection profile that ImageMagick's deskew operator implements. Fast, robust on text/scans up to ±15°.
- **photo** — Python + OpenCV Hough-line transform. Detects the dominant horizontal/vertical line angle (horizons, building edges, table corners) and rotates by its negative. Use for photographs without a clean text baseline.

#### When to use

- Scanned documents that came in at an angle.
- Phone snapshots of pages, receipts, whiteboards.
- Slightly-tilted architectural / horizon photos (`--mode photo`).
- Pre-step before OCR — Tesseract accuracy degrades sharply past ±2° skew.

Do **not** use this skill when:
- The image is intentionally tilted (Dutch angle, artistic composition).
- Skew is severe (>15°) — usually means the document was captured upside down or sideways. Detect orientation first (`exiftool -Orientation`, or rotate by 90/180 multiples) before deskewing.
- The image has no straight reference lines (clouds, abstract textures) — Hough will return noise; rotation will be near-random.

#### Inputs

1. **Input** — file or directory. Required.
2. **Mode** — `document` (default) | `photo` | `auto` (heuristic: if `magick identify -format "%[colorspace]"` is `Gray` or the image has very low saturation → `document`; else `photo`).
3. **Recursive** — `--recursive` for directory descent.
4. **Output** — default in-place suffix `_deskew`. `--output-dir <path>` for sibling folder. `--overwrite` to replace.
5. **Threshold** (mode=document) — `-deskew` percentage. Default `40%` (ImageMagick's recommended value). Higher = more aggressive detection, more false positives.
6. **Max angle** — default `15°`. If detected skew exceeds this, refuse to rotate and flag the file (probably wrong orientation, not skew).
7. **Crop** — default `on`. After rotation, crop to the largest inscribed rectangle so there are no transparent / black triangle borders. `--no-crop` to keep the full rotated canvas.
8. **Background** — fill colour for the post-rotation triangles when `--no-crop`. Default `white`. Use `none` for transparent (PNG/WebP only).

#### Procedure

1. Verify ImageMagick 7+. For `photo` mode, also resolve the plugin's uv venv and verify it has `opencv-python-headless` and `numpy` (managed by `install-deps`; if missing, point at it):

   ```bash
   PLUGIN_DATA_DIR="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops"
   VENV_PY="$PLUGIN_DATA_DIR/venv/bin/python"
   test -x "$VENV_PY" || { echo "Plugin venv missing — run install-deps."; exit 1; }
   "$VENV_PY" -c 'import cv2, numpy' 2>/dev/null \
     || { echo "photo mode needs opencv-python-headless + numpy in the plugin venv — run install-deps."; exit 1; }
   ```

   Invoke Python as `"$VENV_PY"` directly, matching the convention `install-deps` establishes. Do not shell out to `uv run`.

2. Enumerate inputs (JPEG/JPG/PNG/TIFF/TIF/WebP). Skip and note RAW.

3. **document** mode:

   Measure first, then write — the max-angle guard in step 5 has to decide *before* the file is rotated. `-deskew` records what it detected in the `deskew:angle` artifact, so a throwaway pass to `null:` yields the angle without producing output:

   ```bash
   ANGLE=$(magick "$IN" -deskew "${THRESHOLD}%" -print '%[deskew:angle]\n' null:)
   ```

   Apply the guard (step 5), then do the real conversion:

   ```bash
   magick "$IN" -background "$BG" -deskew "${THRESHOLD}%" \
     $( [ "$CROP" = on ] && echo "+repage -fuzz 1% -trim +repage" ) \
     "$OUT"
   ```

   `-deskew` applies the rotation. `-trim` with a small fuzz removes the resulting fill border when `CROP=on`. `$ANGLE` from the measuring pass feeds both the guard and the summary.

4. **photo** mode (Python via the plugin's uv venv):

   ```python
   import cv2, numpy as np, sys
   img = cv2.imread(sys.argv[1])
   if img is None:
       # Unreadable / corrupt / unsupported — exit non-zero so the caller skips
       # the file rather than reading a "0.0" as "no skew detected".
       print("unreadable", file=sys.stderr)
       sys.exit(1)
   gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
   edges = cv2.Canny(gray, 50, 150, apertureSize=3)
   lines = cv2.HoughLines(edges, 1, np.pi/720, 200)
   if lines is None:
       print("0.0"); sys.exit(0)
   # Collect angles near horizontal (±30°) and near vertical (±30° of 90°)
   angles = []
   for rho, theta in lines[:200, 0]:
       deg = np.degrees(theta) - 90  # 0 = horizontal line
       if abs(deg) < 30:
           angles.append(deg)
       elif abs(deg - 90) < 30:
           angles.append(deg - 90)
       elif abs(deg + 90) < 30:
           angles.append(deg + 90)
   if not angles:
       print("0.0"); sys.exit(0)
   print(f"{np.median(angles):.3f}")
   ```

   That snippet is not shipped as a file — write it to a temp script at run time, then invoke it with the venv interpreter resolved in step 1:

   ```bash
   DESKEW_PY="$(mktemp -t deskew_photo.XXXXXX.py)"
   cat > "$DESKEW_PY" <<'PYEOF'
   # ... the Python above, verbatim ...
   PYEOF

   if ! ANGLE=$("$VENV_PY" "$DESKEW_PY" "$IN"); then
     echo "SKIPPED (unreadable): $IN" >> "$failed_log"
     rm -f "$DESKEW_PY"
     continue
   fi

   magick "$IN" -background "$BG" -rotate "$(awk -v a="$ANGLE" 'BEGIN{print -1*a}')" \
     $( [ "$CROP" = on ] && echo "+repage -fuzz 1% -trim +repage" ) \
     "$OUT"

   rm -f "$DESKEW_PY"
   ```

   For a batch, write the temp script once before the loop and delete it after, rather than per file.

5. **Max-angle guard**: applies to both modes, using `$ANGLE` from step 3 (document, measuring pass) or step 4 (photo). If `|angle| > MAX_ANGLE`, skip the file before writing anything and flag it:

   ```bash
   if awk -v a="$ANGLE" -v m="$MAX_ANGLE" 'BEGIN{ exit !(((a < 0) ? -a : a) > m) }'; then
     echo "$IN: detected ${ANGLE}° — exceeds max-angle ${MAX_ANGLE}°, skipping (likely wrong orientation, not skew)"
     continue
   fi
   ```

6. **Crop to inscribed rectangle** (when `--no-crop` is off and the simple `-trim` leaves uneven borders): use the analytic formula for the largest inscribed axis-aligned rectangle inside a rotated rectangle. For input `W×H` rotated by `θ`:

   ```
   new_w = (W·|cos θ| - H·|sin θ|) / (cos²θ - sin²θ)   if W ≥ H
   new_h = (H·|cos θ| - W·|sin θ|) / (cos²θ - sin²θ)
   ```

   Crop centred. For small angles (<5°) the difference vs. `-trim` is negligible — `-trim` is fine.

7. For batch, parallelise with `xargs -P "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"` — `nproc` is GNU coreutils and is absent on macOS/BSD. Skip files ending `_deskew`.

8. Per-file failures append to `$failed_log` and the batch continues. Report that list in the summary; a processed count on its own hides the skips.

#### Output

- Deskewed images at the resolved paths.
- Summary:
  - Files processed / skipped (RAW or non-image) / failed / unchanged (|angle| < 0.1°) / refused (|angle| > max).
  - Per-mode count when mixed.
  - Distribution of detected angles (min / median / max) — sanity check across the batch.

#### Notes

- ImageMagick's `-deskew` is tuned for bilevel/grayscale text. On colour photos it often returns 0° or noise — that's why `photo` mode exists.
- For OCR pipelines: deskew before binarisation. After deskew, `magick "$IN" -threshold 50%` or hand off to `tesseract` directly.
- If you want both content types handled in one run: `--mode auto`. The heuristic isn't perfect — review the angle distribution in the summary and re-run misclassified files explicitly.
- This skill rotates only. For perspective correction (four-corner unwarping of a photographed document), use a dedicated tool like `dewarp` or OpenCV's `getPerspectiveTransform` — auto-deskew won't fix keystoning.

---

### Auto Tone

**Name.** `auto-tone`

**When to use.** Use when the user wants automatic tonal correction — fix flat/washed-out / underexposed / low-contrast images by stretching levels, normalising contrast, and gamma-correcting to a neutral midtone. Implements auto-level (per-channel histogram stretch), auto-gamma (midtone correction), and a combined "punch" mode via ImageMagick. Operates on JPEG/PNG/TIFF/WebP.

**Triggers.** this photo looks flat, fix the exposure on these, brighten up my scans

Fix flat or under/over-exposed images without manual curves work. Three modes:

- **level** (default) — `-auto-level` on the luminance channel. Stretches the histogram to `[0,1]` without touching colour balance. Safe, reversible-feeling.
- **gamma** — `-auto-gamma`. Drives the image's mean brightness toward 50% grey. Lifts dark scans, tames blown-out daylight.
- **punch** — `-normalize` (1% black + 1% white clip) followed by `-auto-gamma`. Stronger; the "press the button" preset for batch gallery prep.

#### When to use

- Underexposed indoor / night phone shots.
- Faded scans of old prints.
- Bulk normalisation of a gallery shot under varying light.
- Pre-step before sharpening or upscaling — auto-tone first so the next stage isn't operating on a flat histogram.

Do **not** use this skill when:
- Source is a RAW file — fix tone in `darktable-cli` where you have full bit depth.
- Image is intentionally low-key (silhouettes, night scenes with crushed shadows) or high-key (snow, fashion editorials). Auto-gamma flattens the look.
- The histogram is already well-distributed (a quick `magick identify -format "%[fx:standard_deviation]" "$IN"` ≥ 0.22 → likely already toned; auto-level becomes a no-op or worse).

#### Inputs

1. **Input** — file or directory. Required.
2. **Mode** — `level` (default) | `gamma` | `punch`.
3. **Recursive** — `--recursive` for directory descent.
4. **Output** — default in-place suffix `_tone`. `--output-dir <path>` to write into a sibling folder. `--overwrite` to replace.
5. **Strength** — `0.0` to `1.0` (default `1.0`). Blends corrected image with original via `-compose blend`.
6. **Preserve hue** — default `on`. Operate on the luminance channel only (HSL `L`), so colour relationships aren't shifted. `--per-channel` to apply auto-level independently to R/G/B (acts as combined tone + white-balance — usually you want `auto-white-balance` for that instead).
7. **Clip** (mode=punch) — black/white clip percent. Default `1`. `--clip 0.5` for gentler, `--clip 2` for aggressive contrast.

#### Procedure

1. Verify ImageMagick 7+. `magick -version | head -1`. Else `convert` (IM6) with the same syntax.

2. Enumerate inputs (JPEG/JPG/PNG/TIFF/TIF/WebP). Skip RAW with note.

3. **level** (luminance-only auto-level, hue-preserving):

   ```bash
   magick "$IN" -colorspace HSL -channel L -auto-level +channel -colorspace sRGB "$OUT"
   ```

   With `--per-channel`:

   ```bash
   magick "$IN" -channel RGB -auto-level +channel "$OUT"
   ```

4. **gamma**:

   ```bash
   magick "$IN" -auto-gamma "$OUT"
   ```

   `-auto-gamma` computes the gamma needed to drive `mean → 0.5` and applies it. No clipping, no hue shift.

5. **punch**:

   ```bash
   magick "$IN" -normalize -auto-gamma "$OUT"
   ```

   Or with explicit clip:

   ```bash
   magick "$IN" -colorspace HSL -channel L -contrast-stretch "${CLIP}%x${CLIP}%" \
     +channel -colorspace sRGB -auto-gamma "$OUT"
   ```

   The `-colorspace HSL` wrap is required, exactly as in the `level` mode above. In sRGB there is no channel named `L` for `-channel` to select, so without the wrap the clip does not do the hue-preserving stretch the mode advertises.

   `-contrast-stretch 1%x1%` clips the darkest 1% to black and brightest 1% to white before stretching — the "Photoshop auto-contrast" behaviour.

6. **Strength blend** (when `<1.0`):

   Steps 3–5 write the tone-corrected result to a temp file `$TONED`, not straight to `$OUT`; the blend then composites it back over the original:

   ```bash
   PCT=$(awk -v s="$STRENGTH" 'BEGIN{ printf "%.0f", s*100 }')
   magick "$IN" "$TONED" -compose blend -define compose:args="$PCT" -composite "$OUT"
   rm -f "$TONED"
   ```

   At `--strength 1.0` skip the blend entirely and let steps 3–5 write `$OUT` directly.

7. For batch, parallelise with `xargs -P "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"` — `nproc` is GNU coreutils and is absent on macOS/BSD. Skip files ending `_tone` to avoid recursive re-processing.

8. Check `magick`'s exit status per file. On non-zero, append the path to `$failed_log`, remove any partial output, and continue to the next file.

#### Output

- Tone-corrected images at the resolved paths.
- Summary:
  - Files processed / skipped (RAW or non-image) / failed / no-op (where the histogram was already well-distributed). The failed count and the paths come from `$failed_log` — report both, never the processed count alone.
  - Per-mode count when mixed.
  - Average histogram-spread before/after (`fx:standard_deviation`) — sanity check that the run actually changed something.

#### Notes

- For "make my photos look better" without thinking: `--mode punch --strength 0.7` is the sane default.
- Auto-tone amplifies noise. If the source is already noisy (high ISO phone shots), denoise first, then tone.
- Combined with `auto-white-balance`: run WB first (so tone correction operates on a neutral image), then tone. Reverse order is not order-equivalent.
- This skill is the tone-only primitive. The `/apply-filters` command may chain it with sharpen/saturate; use this skill standalone when you only want tonal work.

---

### Auto White Balance

**Name.** `auto-white-balance`

**When to use.** Use when the user wants to automatically correct the white balance of an image (or batch) — neutralise colour casts from indoor lighting, mixed light, underwater shots, scans, or uncalibrated cameras. Implements gray-world (default), white-patch (per-channel auto-level), and a combined mode via ImageMagick. Operates on JPEG/PNG/TIFF/WebP; for RAW use `darktable-cli` instead.

**Triggers.** this photo looks too orange, fix the colour cast on these scans, white balance this batch

Neutralise colour casts without per-image manual correction. Three algorithms, one CLI.

- **gray-world** (default) — assume the average of the scene is neutral grey. Scale each RGB channel so its mean equals the global mean. Robust on most natural scenes.
- **white-patch** — assume the brightest pixels are white. Per-channel `-auto-level` stretches each channel to full range. Strong correction; fails on scenes lacking a true white reference.
- **combined** — gray-world first, then a gentle white-patch pass at 50% strength. Good default for mixed-light indoor shots.

#### When to use

- Indoor photos under tungsten/fluorescent/LED with the wrong WB preset.
- Scanned prints / slides with age-related cast.
- Underwater or aquarium shots (heavy blue/green cast).
- Batch normalisation before publishing a gallery shot across multiple lighting conditions.

Do **not** use this skill when:
- Source is a RAW file (CR2/NEF/ARW/DNG/RAF) — use `darktable-cli` with `--apply-custom-presets` and the `temperature` module set to `as shot to reference`. White-balancing a baked JPEG throws away headroom that's still in the RAW.
- The cast is intentional (golden hour, sodium streetlamps for mood, blue-hour landscapes). Auto-WB will flatten it.
- The image is a deliberately monochromatic / toned edit.

#### Inputs

1. **Input** — file or directory. Required.
2. **Mode** — `gray-world` (default) | `white-patch` | `combined`.
3. **Recursive** — `--recursive` for directory descent.
4. **Output** — default in-place suffix `_wb` next to the source. `--output-dir <path>` to write into a sibling folder. `--overwrite` to replace.
5. **Strength** — `0.0` to `1.0` (default `1.0`). Blends the corrected image with the original via `-compose blend -define compose:args=<pct>`. Use `0.5` for a softer touch.
6. **Preserve luminance** — default `on`. After channel scaling, rescale so the mean luminance matches the original (prevents brightness drift). `--no-preserve-luma` to disable.

#### Procedure

1. Verify ImageMagick 7+. `magick -version | head -1`. Fall back to `convert` (IM6) if `magick` is missing — the syntax below works on both with the leading binary swapped. If neither, point at `install-deps`.

2. Enumerate inputs. Accept JPEG/JPG/PNG/TIFF/TIF/WebP. Skip and note RAW formats.

3. **gray-world**:

   ```bash
   magick "$IN" \
     -colorspace sRGB \
     -channel R -evaluate multiply "$GR" \
     -channel G -evaluate multiply "$GG" \
     -channel B -evaluate multiply "$GB" \
     +channel "$OUT"
   ```

   with `$GR` / `$GG` / `$GB` from the guarded `gain()` helper below.

   Each `fx:mean/mean.<c>` is the gain that drives that channel's mean to the global mean. Three `info:` calls decode the image three extra times — for a batch, read all four means in one pass and compute the gains in shell instead:

   ```bash
   read -r M MR MG MB < <(magick identify \
     -format "%[fx:mean] %[fx:mean.r] %[fx:mean.g] %[fx:mean.b]" "$IN")

   # A channel whose mean is 0 (a pure-black R, G or B plane) has no gain that
   # makes it neutral; dividing yields inf and -evaluate multiply corrupts the
   # file. Leave that channel alone.
   gain() { awk -v m="$M" -v c="$1" 'BEGIN{ print (c > 0) ? m/c : 1 }'; }
   GR=$(gain "$MR"); GG=$(gain "$MG"); GB=$(gain "$MB")
   ```

4. **white-patch**:

   ```bash
   magick "$IN" -channel RGB -auto-level +channel "$OUT"
   ```

   Independent per-channel histogram stretch to `[0,1]`. Aggressive; clips highlights if any channel already saturates.

5. **combined**:

   Run gray-world to a temp file, then:

   ```bash
   magick "$TMP" \( +clone -channel RGB -auto-level +channel \) \
     -compose blend -define compose:args=50 -composite "$OUT"
   ```

6. **Preserve luminance** (when enabled): after step 3/4/5, measure luminance before and after and rescale:

   ```bash
   L_IN=$(magick "$IN"  -colorspace Gray -format "%[fx:mean]" info:)
   L_OUT=$(magick "$WB" -colorspace Gray -format "%[fx:mean]" info:)

   # A fully black WB result gives L_OUT = 0; dividing yields inf/nan and
   # -evaluate multiply then writes a corrupt file. Fall back to no rescale.
   GAIN=$(awk -v i="$L_IN" -v o="$L_OUT" 'BEGIN{ print (o > 0) ? i/o : 1 }')
   magick "$WB" -evaluate multiply "$GAIN" "$OUT"
   ```

7. **Strength blend** (when `<1.0`):

   ```bash
   PCT=$(awk -v s="$STRENGTH" 'BEGIN{ printf "%.0f", s*100 }')
   magick "$IN" "$WB" -compose blend -define compose:args="$PCT" -composite "$OUT"
   ```

8. For batch, parallelise with `xargs -P "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"` over the file list — `nproc` is GNU coreutils and is absent on macOS/BSD. Skip files that already end in `_wb` to avoid recursive re-processing.

9. Check `magick`'s exit status per file. On non-zero, append the path to `$failed_log`, remove any partial output and temp files, and continue with the next file.

#### Output

- Corrected images at the resolved paths.
- Summary:
  - Files processed / skipped (RAW or non-image) / failed — the failure count and paths read from `$failed_log`.
  - Per-mode count when mixed.
  - Average per-channel gain across the batch (sanity check — if R-gain ≈ G-gain ≈ B-gain ≈ 1.0, the batch had no cast and the run was a no-op).

#### Notes

- Gray-world fails on scenes dominated by one colour (snow, foliage, red brick wall). For those, `white-patch` is more honest, or skip auto-WB entirely and use a colour picker on a known-neutral patch.
- For batch mixed-lighting normalisation, run `combined` at `--strength 0.7` — strong enough to neutralise obvious casts, weak enough to preserve scene character.
- Output colour profile: ImageMagick respects the input ICC profile. If the source has no profile, it's treated as sRGB. Use `-profile sRGB.icc` explicitly if the pipeline downstream is profile-strict.
- This skill is the single-image / batch primitive. The `/apply-filters` command may call it as one step; this skill exists to do WB-only work without the rest of the pipeline.

---

### Batch Set Copyright on Images

**Name.** `batch-set-copyright`

**When to use.** Use when the user wants to batch-stamp copyright, artist, and rights information across every image in a directory — a photo library heading for distribution or archival. Convenience wrapper around exiftool. For arbitrary tags (description, keywords, GPS) on individual files, use `set-metadata` instead.

**Triggers.** add my copyright to all these photos, stamp the artist name across this shoot

Walk a directory and stamp copyright, artist, and rights metadata on every image using `exiftool`. Common real-world use: archiving a photo library with a consistent copyright statement.

#### When to use

- Preparing a personal photo library for distribution or archival with consistent copyright metadata.
- Quickly tagging all images from an event or shoot with the same artist and copyright info.
- Ensuring your photo library has baseline legal metadata before sharing or licensing.

#### Inputs to gather

- **Target directory** — folder containing images to tag. Default: current directory.
- **Recursive?** Ask whether to process subdirectories. Default: **no** (flat, current folder only).
- **Artist name** — required. Ask for the photographer or creator name.
- **Copyright string** — optional. If not provided, auto-generate from current year and artist: `© 2026 <Artist>`. Allow the user to override.
- **Rights/Usage statement** (optional) — additional rights text (e.g., "All rights reserved", "Creative Commons BY-SA 4.0"). If omitted, skip this field.
- **Backup before write?** Default: **yes**. Automatic via exiftool `_original` sidecars.

#### Procedure

##### 1. Check tooling

```bash
command -v exiftool >/dev/null || {
  echo "exiftool not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Build metadata strings

```bash
ARTIST="<user-provided>"                       # required
COPYRIGHT="${user_copyright:-© $(date +%Y) $ARTIST}"
RIGHTS="<user-provided-or-empty>"              # optional
```

- **Artist:** the user-provided value.
- **Copyright:** provided, or auto-generated as `© <YYYY> <Artist>` using the current year from `date +%Y`.
- **Rights/Usage:** used if provided; otherwise omitted entirely.

Print a summary for user confirmation before proceeding.

##### 3. Count and preview

```bash
# Count images that will be tagged.
# Non-recursive: -maxdepth 1. Recursive: omit -maxdepth entirely.
find "$TARGET" -maxdepth 1 -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
     -o -iname '*.heic' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \) | wc -l
```

Quote `"$TARGET"` everywhere — an unquoted path word-splits on the first space and `find` then reports a nonexistent directory.

Print:
- Number of images found.
- Metadata to be applied.
- Request confirmation before applying.

##### 4. Apply metadata

Build the tag list as an array first. The optional `-Rights` flag cannot be written inline as `<-Rights="...">` — bash reads a bare `<` and `>` as input/output redirection, so that line breaks the command rather than making the flag conditional:

```bash
ARGS=( -Artist="$ARTIST" -Copyright="$COPYRIGHT" )
[ -n "$RIGHTS" ] && ARGS+=( -Rights="$RIGHTS" )
```

Then apply, tallying per-file status. `find -exec` discards each `exiftool` exit code, so without the inner shell the "count of failures" promised in step 6 cannot be produced:

```bash
: > "$failed_log"

# Non-recursive: -maxdepth 1. Recursive: omit -maxdepth entirely
# (there is no need for a sentinel like -maxdepth 999, which silently
# truncates a tree deeper than that).
find "$TARGET" -maxdepth 1 -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
     -o -iname '*.heic' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \) \
  -print0 |
while IFS= read -r -d '' f; do
  exiftool "${ARGS[@]}" "$f" >/dev/null || echo "$f" >> "$failed_log"
done
```

`-print0` with `read -d ''` is what makes filenames containing spaces or newlines safe here.

Show progress as files are processed (especially for large batches).

##### 5. Verify

Sample 3–5 images across the directory and confirm metadata was applied:

```bash
exiftool -Artist -Copyright -Rights "$sample1"
exiftool -Artist -Copyright -Rights "$sample2"
```

##### 6. Report

After completion:

- Count of images successfully tagged.
- Count of failures and their paths, read from `$failed_log`. Say "none" only when that file is empty.
- Reminder: `_original` sidecars have been created (location noted).
- Option: offer to remove `_original` sidecars if the user is confident the write succeeded.

#### Output / side effects

- Copyright, Artist, and optional Rights metadata written to all images in scope.
- `_original` sidecars created in the same directories (can be removed post-verification).
- Original images modified; create a backup directory first if preservation is critical.

#### Notes

- **Auto-generated copyright:** step 2 uses the system date (`date +%Y`) to build the year. If the images are from a prior year, the user should provide a custom copyright string (e.g. `© 2024 <Artist>`).
- **Metadata format:** `exiftool` writes to EXIF IFD0 / IPTC / XMP as appropriate. Different image readers may check different formats; this skill writes comprehensively so compatibility is high.
- **Batch verification:** For large directories, consider sampling rather than checking every file. Spot-check 5–10% of the batch.
- **Rights field variations:** Some tools recognize `Rights`, others use `UsageRights` or custom XMP fields. The `Rights` tag is most portable; if compatibility issues arise, document alternatives in the report.
- **Preserve prior metadata:** By default, this skill adds/updates copyright metadata without touching other tags. If the user wants a fresh start (nuke all, then add new), use the `scrub-metadata` skill first.
- Depends on `exiftool` (`apt install libimage-exiftool-perl` on Debian/Ubuntu, `brew install exiftool` on macOS). Use `install-deps` rather than installing by hand.

---

### Convert to AVIF

**Name.** `convert-to-avif`

**When to use.** Use when the user wants AVIF output — modern web format with ~30% better compression than WebP at the same visual quality, and ~50% better than JPEG. Wraps `avifenc`. Companion to the `/convert-to-webp` command. Best target for new web work; check browser support if delivering to ancient clients.

**Triggers.** convert these to AVIF, encode this folder as AVIF for the web

Encode JPEG/PNG/TIFF to AVIF. AVIF beats WebP on compression ratio and supports 10/12-bit, HDR, and lossless modes. Browser support is universal as of 2024 (Chrome 85+, Firefox 113+, Safari 16.4+).

#### When to use

- Web-prep where modern browser support is fine.
- Archival of high-bit-depth photos (10/12-bit AVIF preserves more than JPEG).
- Pre-step inside `web-ready` orchestrator.

Do **not** use this skill when:
- Output must work in Safari <16.4 / IE / very old Android browsers — fall back to WebP or JPEG.
- Source is already AVIF — no point re-encoding.
- You need lossless re-encoding of a JPEG that should remain bit-exact-decodable — that's JPEG XL's unique trick, not AVIF's. Use `transcode-jpeg-to-jxl-lossless`.

#### Inputs

1. **Input** — file or directory. Required.
2. **Quality** — `avifenc -q N` (0–100). Default `60` (visually equivalent to JPEG q82, much smaller). `80` for archival; `45` for aggressive.
3. **Speed/effort** — `avifenc -s <0..10>`. Default `6` (balanced). `0` is best compression but very slow; `10` is fast but bigger files.
4. **Lossless** — `--lossless`. Enables lossless mode (ignores quality). For exact archival of PNG.
5. **Bit depth** — `--depth 8|10|12`. Default `8`. Use `10` for HDR or 16-bit source.
6. **Output dir** — default: `<input-dir>/avif/`. Skill never overwrites originals.
7. **Recursive** — `--recursive` for directory descent.
8. **Preserve EXIF** — default off (web-prep assumption). `--keep-exif` to copy EXIF over via `exiftool`.

#### Procedure

1. Verify `avifenc` is on PATH. If missing, point at `install-deps`.

2. Enumerate inputs (jpg, jpeg, png, tiff — skip others with note).

3. For each file:

   ```bash
   avifenc -q "$quality" -s "$speed" ${lossless:+--lossless} ${depth:+--depth "$depth"} \
     "$input" "$output" \
     || { echo "FAILED: $input" >> "$failed_log"; rm -f "$output"; continue; }
   ```

   Per-file. avifenc is single-threaded per encode but accepts `--jobs N` for tile-parallel — useful on large images. Removing a partial `$output` on failure matters: a truncated AVIF left behind looks like a successful conversion to the summary and to anything that later globs the output directory.

   For batch parallelism:

   ```bash
   find "$indir" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \
        -o -iname '*.png' -o -iname '*.tif' -o -iname '*.tiff' \) -print0 |
   xargs -0 -P "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" -I{} \
     sh -c 'avifenc -q "$0" -s "$1" "$2" "$3/$(basename "${2%.*}").avif" \
            || echo "FAILED: $2" >> "$4"' \
     "$quality" "$speed" {} "$outdir" "$failed_log"
   ```

4. If `--keep-exif` was set, post-process:

   ```bash
   exiftool -tagsfromfile "$input" -all:all "$output" -overwrite_original
   ```

5. Track size deltas, and report the contents of `$failed_log` alongside them.

#### Output

- AVIF files at `<output-dir>/`.
- Summary:
  - Files processed / failed, with the failed paths from `$failed_log`.
  - Total: `<orig-MB>` → `<new-MB>` (`<pct>%` saved).
  - Quality estimate per file (using `--qcolor` if requested).

#### Notes

- AVIF encoding is *slow* compared to JPEG/WebP. Speed `6` is ~2–4× slower than `cwebp`. Speed `0` can be 30× slower. Pick `6` unless archiving.
- `--speed 6 --quality 60` is the de facto web-prep default — quality matches q82 JPEG at roughly half the bytes.
- Animation: avifenc supports animated AVIF from PNG sequences (`avifenc -i input1.png -i input2.png ...`) but this skill focuses on still images.
- Decode support outside browsers is uneven (older image viewers may not decode). Check before mass-converting an archive.
- For *guaranteed* lossless re-encode of a JPEG (bit-exact reversible), use `transcode-jpeg-to-jxl-lossless` instead — JXL has a unique lossless-JPEG mode that AVIF cannot match.

---

### Fast Resize (libvips)

**Name.** `fast-resize`

**When to use.** Use when the user wants to resize a large batch of images (>500 files) where ImageMagick throughput is the bottleneck. Wraps libvips for 5–10× faster batch resize at lower memory. Falls back to ImageMagick if `vips` isn't installed. Same outputs as the `/batch-resize` command — different engine.

**Triggers.** resize this whole folder fast, these thousands of images are too slow in ImageMagick

Batch image resize using libvips. Material throughput improvement over ImageMagick on large libraries — typical 5–10× speed-up and lower peak memory.

#### When to use

- Batch is >500 images.
- The user is feeling ImageMagick's slowness (or is about to).
- The job is "resize this directory" — pure resize without compositing or filters.

Do **not** use this skill for:
- Small batches (<100 images) — the `/batch-resize` command is fine, no point swapping engines.
- Resize-with-filter / resize-with-text / multi-op pipelines — ImageMagick is the better tool for compound work.

#### Inputs

1. **Input directory** — required.
2. **Target size** — one of:
   - `--width N` — resize so width = N, height auto.
   - `--height N` — resize so height = N, width auto.
   - `--max NxM` — fit within NxM box (preserves aspect).
   - `--exact NxM` — force exact dimensions (may distort or crop).
3. **Output mode** — `--output-dir <path>` (default: `<input>/resized/`), or `in-place`. **In-place is destructive and downscaling is not reversible** — never select it on the user's behalf. Require an explicit request plus a confirmation after the dry-run count in step 2, and write via a temp file so a failed resize cannot leave a truncated original (step 3).
4. **Filter** — interpolation kernel: `lanczos3` (default — best quality), `cubic`, `linear`, `nearest`.
5. **Recursive** — `--recursive` to descend into subdirectories. Default: top-level only.
6. **Format preserve** — by default keeps source format. `--to <ext>` to change format on the way out.

#### Procedure

1. Verify `vips` is on PATH. If missing, fall back to ImageMagick `convert` with the same parameters and warn that this will be slower (point at `install-deps`).

2. Enumerate input files (filter to image extensions: jpg, jpeg, png, webp, tiff, gif, heic, avif, jxl). Report the count and the resolved output mode. **If in-place was requested, stop here and get explicit confirmation** — state the file count and that originals will be replaced.

3. For each file, build the vips command. Two main forms:

   **Fit within box (preserves aspect):**
   ```bash
   vipsthumbnail "$input" --size "${W}x${H}" --output "$output[Q=85]"
   ```

   `vipsthumbnail` is the right tool for "resize down" — it's optimised for thumbnail-style ops and handles JPEG shrink-on-load (free 8× speedup for 1/8-size targets).

   **Exact resize via `vips`:**
   ```bash
   # scale = target / source; vips resize takes a scale factor, not pixel dims
   src_w=$(vipsheader -f width "$input")
   scale=$(awk -v t="$target_w" -v s="$src_w" 'BEGIN{ printf "%.6f", t/s }')
   vips resize "$input" "$output" "$scale" --kernel "$kernel"
   ```

   For `--width`/`--height`, compute scale = target / source as above. `vipsthumbnail` is preferred when shrinking; use `vips resize` when upscaling or when source dimensions vary widely.

   **In-place writes go through a temp file.** A vips process killed mid-write (OOM, corrupt source) otherwise leaves a truncated file where the original was:

   ```bash
   tmp="$(mktemp "${input}.XXXXXX.${ext}")"
   if vipsthumbnail "$input" --size "${W}x${H}" --output "$tmp[Q=85]"; then
     mv "$tmp" "$input"
   else
     rm -f "$tmp"
     echo "FAILED: $input" >> "$failed_log"
   fi
   ```

4. Run in parallel where safe. vips is internally threaded; running multiple processes via xargs/parallel adds little. One process per CPU core is the sweet spot for large batches — `$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)`, which works on both macOS and Linux (`nproc` is GNU-only).

5. Report progress every N files (every 10% or every 100, whichever is more frequent).

6. Capture per-file failures as shown above. Every non-zero exit appends to `$failed_log`; the summary in the Output section reads from it. Do not report a processed count without the failure list.

#### Output

- Resized images at the resolved output paths.
- Summary: `<n> files processed, <total-input-MB>MB → <total-output-MB>MB, <elapsed-s>s, avg <ms>ms/image`.
- List of any files that failed (corrupt, unsupported format, permission errors).
- If output-dir was used and any source files had identical names from different subdirectories without `--recursive` flattening logic, flag the collision.

#### Notes

- `vipsthumbnail` accepts `[Q=N]` syntax for JPEG quality on output (default 75; 85 is a good balance).
- Wide colour gamut: vips preserves ICC profiles by default. If the user is processing display-P3 / Adobe RGB images, that's a feature.
- HEIC / AVIF / JXL: vips supports these if compiled with the right libs (apt's `libvips-tools` includes libheif and libjxl on recent Ubuntu).
- ImageMagick fallback path: if `vips` is missing, run `magick "$input" -resize "${W}x${H}" "$output"` per file. Same output, slower. (`magick` is the ImageMagick 7 entry point; `convert` is the v6 name and is deprecated in v7.) The same temp-file-then-`mv` rule applies for in-place runs.

---

### Fast Thumbnail (vipsthumbnail)

**Name.** `fast-thumbnail`

**When to use.** Use when the user wants to generate thumbnails at scale — index views, contact sheets, web previews, or just shrinking a library to manageable sizes. Wraps `vipsthumbnail` for sub-second-per-image generation, much faster than ImageMagick on large batches.

**Triggers.** make thumbnails of this folder, build me a contact sheet's worth of previews, shrink these for a gallery index

Generate thumbnails at high throughput using `vipsthumbnail`. Distinct from `fast-resize`: this is purpose-built for "make small previews of every image in this folder" workflows where output is always a downscale and quality is "good enough for a thumbnail".

#### When to use

- Building a contact-sheet / web-gallery / index of an image library.
- Pre-rendering thumbnails for a UI / filesystem browser.
- Bulk-shrinking large originals to share / archive.

Do **not** use this skill when:
- The user wants the *same* size as the originals — that's a no-op.
- The user is upscaling — use `fast-resize` (or `upscale-image` for AI upscale).
- The user wants to keep original quality — this skill assumes lossy thumbnail-grade output.

#### Inputs

1. **Input directory** — required.
2. **Size** — pixel size. Single number is shorthand for `NxN` (fit within square). Default: `512`.
3. **Output dir** — default: `<input>/thumbnails/`. The skill never overwrites originals.
4. **Format** — output format. Default: `jpg` (best size/quality balance for thumbs). Options: `jpg`, `png`, `webp`, `avif`.
5. **Quality** — JPEG/WebP/AVIF quality. Default: `80`.
6. **Recursive** — `--recursive` to descend. Mirrors subdirectory structure under the output dir.
7. **Naming** — default: same base name. `--prefix <s>` or `--suffix <s>` if collision is a risk.

#### Procedure

1. Verify `vipsthumbnail` is on PATH. If missing, point at `install-deps`. No graceful fallback — if vips isn't installed, the skill's whole reason to exist is gone; tell the user to install it or use the `/batch-resize` command.

2. Enumerate input files (image extensions only).

3. For each file:

   ```bash
   vipsthumbnail "$input" \
     --size "$size" \
     --output "$outdir/$(basename "${input%.*}").$ext[Q=$quality]" \
     || echo "FAILED: $input" >> "$failed_log"
   ```

   For non-JPEG outputs, the `[Q=N]` syntax still works for WebP/AVIF.

4. For very large batches, parallelise. vips is internally threaded but per-image work is small enough that process-level parallelism wins on >5k batches:

   ```bash
   find "$indir" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
        -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.webp' \) -print0 |
   xargs -0 -P "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" -I{} \
     sh -c 'vipsthumbnail "$0" --size "$1" \
              --output "$2/$(basename "${0%.*}").$3[Q=$4]" \
            || echo "FAILED: $0" >> "$5"' \
     {} "$size" "$outdir" "$ext" "$quality" "$failed_log"
   ```

   `-print0` / `-0` keeps filenames with spaces intact, and every path stays quoted — an unquoted `{}` breaks on the first space.

5. Track progress and skipped files. Every non-zero `vipsthumbnail` exit lands in `$failed_log`; report its contents in the summary rather than a bare success count.

#### Output

- Thumbnails at `<output-dir>/`.
- Summary: `<n> thumbnails, <total-output-MB>MB, <elapsed-s>s, avg <ms>ms/image`.
- Failed files listed, read from `$failed_log`.

#### Notes

- `vipsthumbnail` shrink-on-load: for JPEG sources, it decodes at the smallest DCT scale ≥ target — so generating a 256-px thumbnail from a 4000-px JPEG is *much* faster than full decode + resize. This is the headline reason to use it.
- Sharpen-on-shrink is on by default (vipsthumbnail applies a mild sharpen after downscale). Add `--no-rotate` and explicit `--linear` flags only if the user asks for them; the defaults are sensible for thumbnails.
- For contact-sheet *layout* (multiple thumbs into a grid image), this skill produces the inputs; combine with ImageMagick `montage` separately.
- ICC handling: vipsthumbnail strips ICC by default to keep file sizes small (right call for thumbs). If colour-accurate thumbs are needed, pass `--export-profile <path-to-srgb.icc>`.

---

### Decode JPEG XL Images

**Name.** `from-jxl`

**When to use.** Use when the user wants to decode JPEG XL images (.jxl) back to PNG or JPEG — for compatibility with tools that cannot read JXL, for display, or for further editing. Also recovers the byte-exact original JPEG from a lossless transcode. Reverse of `to-jxl`.

**Triggers.** convert these JXL files to PNG, my viewer can't open .jxl, get the original JPEG back out

Extract images from JPEG XL (.jxl) files using `djxl`. Outputs PNG or JPEG, with optional recovery of original JPEG bitstream if the source JXL was a lossless JPEG transcode.

#### When to use

- Converting JXL files back to PNG for general use or compatibility.
- Recovering the original JPEG bitstream from a lossless-transcoded JXL file.
- Batch-decoding a JXL archive to portable formats.

#### Inputs to gather

- **Input .jxl file or directory** — single file or folder.
- **Output format** — `png` (default) or `jpeg`. If the user has a JXL that came from a lossless JPEG transcode and wants to recover the original JPEG byte-exact, offer the `jpeg` format and explain that reconstruction is automatic (see step 3).
- **Output directory** — optional. Default: same directory as input.

#### Procedure

##### 1. Check tooling

```bash
command -v djxl >/dev/null || {
  echo "djxl not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Determine scope and format

- **Single file:** direct conversion.
- **Directory (non-recursive):** loop over all `.jxl` files.
- **Recursive:** use `find` to locate `.jxl` files in the tree.

Confirm the output format with the user. Set the depth limit once, and reuse it:

```bash
maxdepth="-maxdepth 1"   # non-recursive
maxdepth=""              # recursive — omit the flag entirely
```

##### 3. Decode

`djxl` picks its output codec from the output file's extension. There is no format flag to pass.

**Single file to PNG (default):**

```bash
djxl input.jxl output.png
```

**Single file to JPEG:**

```bash
djxl input.jxl output.jpg
```

A `.jpg` output only succeeds when the `.jxl` carries JPEG reconstruction data (JBRD) — that is, it came from `cjxl original.jpg out.jxl`. In that case the result is the original JPEG **byte-exact**, which is the recovery path for an archive built by `transcode-jpeg-to-jxl-lossless`.

For a `.jxl` encoded from PNG or any other source there is no JBRD and this command **fails**; it does not silently re-encode. Decode to PNG and re-encode explicitly instead:

```bash
djxl input.jxl /tmp/decoded.png && magick /tmp/decoded.png -quality 92 output.jpg
```

Check for reconstruction data before promising byte-exact recovery on a batch — a failed `djxl` to `.jpg` is the signal, so let step 4's failure log surface it rather than pre-flighting every file.

**Batch (folder or recursive):**

`find` substitutes only the literal token `{}`. It has no `{.}` extension-stripping placeholder — that is GNU parallel syntax, and `find` passes `{.}.png` through verbatim, so every file decodes onto one output that each iteration overwrites. Derive the name in a shell:

```bash
: > "$failed_log"

find "$target" $maxdepth -type f -iname '*.jxl' \
  -exec sh -c '
    for f do
      djxl "$f" "${f%.jxl}.$0" || echo "$f" >> "$1"
    done
  ' "$format" "$failed_log" {} +
```

Set `$format` to `png` or `jpg`.

##### 4. Report

After decoding:

- Count of files decoded, skipped, failed.
- Output file sizes and locations.
- Print the contents of `$failed_log`; say "none" only when it is empty. For a `jpg` batch, a failure most often means that `.jxl` had no JPEG reconstruction data — call that out rather than reporting a generic error.

#### Output / side effects

- New PNG or JPEG files created in the output directory.
- Original `.jxl` files remain unchanged.

#### Notes

- **Lossless JPEG recovery:** decoding to a `.jpg` output reconstructs the original bitstream only when the `.jxl` was created via lossless JPEG transcode (`cjxl original.jpg encoded.jxl`). Otherwise `djxl` errors out — it will not hand back a silently re-encoded approximation, so a successful `.jpg` decode is itself the guarantee.
- **Alpha channels:** JXL alpha is preserved when decoding to PNG. JPEG does not support transparency, so any alpha will be lost if decoding to JPEG.
- **Color profile:** JXL can carry ICC color profiles; `djxl` preserves them in the output.
- Depends on `libjxl-tools` (`apt install libjxl-tools` on Debian/Ubuntu, `brew install jpeg-xl` on macOS). Use `install-deps` rather than installing by hand. The `magick` re-encode path above additionally needs ImageMagick.

---

### Images → PDF

**Name.** `images-to-pdf`

**When to use.** Use when the user wants to combine a folder or list of images into a single PDF — typically on a standard paper size (A4 default) for digital printers, document-style sharing, or proof sheets. Modes - one-per-page (default; auto-orient portrait/landscape per image), multi-up (2/4/6/9 per page), as-is (native pixel size). Prefers `img2pdf` for lossless JPEG embedding; falls back to ImageMagick for non-JPEG sources or when img2pdf is missing.

**Triggers.** put these photos into a PDF, make a proof sheet, bundle this folder for the print shop

Bundle images into a PDF with predictable paper-size and layout behaviour. Built for the recurring "I need to send this batch to a printer" workflow.

#### When to use

- Preparing a photo set for a digital print shop (one-per-page on A4 / Letter).
- Building a proof sheet (multi-up).
- Sharing a document-style PDF (e.g. scanned receipts) without re-encoding.
- Bundling AI-generated images for client review.

Do **not** use this skill when:
- The user wants the PDF to also include text/markdown — that's a different workflow (typst / pandoc).
- The PDF needs OCR text layer — out of scope (run tesseract separately, then merge).
- A single image → PDF without paper-size constraints — `img2pdf <input> -o <output>.pdf` is enough; no skill needed.

#### Inputs

1. **Inputs** — directory, glob, or explicit file list. Required.
2. **Output PDF path** — required.
3. **Paper size** — `A4` (default), `A3`, `A5`, `Letter`, `Legal`, `Tabloid`, or explicit `<W>x<H><unit>` (e.g. `210x297mm`, `8.5x11in`).
4. **Mode** — one of:
   - `one-per-page` (default) — one image per page, fitted to the paper with margins. Auto-rotates the page (portrait vs landscape) to match the image's aspect ratio.
   - `multi-up` — `2`, `4`, `6`, or `9` images per page (`--per-page N`). Grid layout, each cell sized equally, image fitted within cell.
   - `as-is` — native pixel dimensions become the page size (use for digital archives or when DPI metadata is authoritative).
5. **Margin** — millimetres. Default `10mm` (`one-per-page`), `5mm` per cell (`multi-up`), `0` (`as-is`).
6. **Sort order** — `filename` (default, natural sort), `exif-date` (capture time from EXIF), `mtime` (filesystem mtime).
7. **DPI** — assumed DPI for fit calculations when source has no DPI metadata. Default `300` (print-quality).
8. **Auto-orient** — default `on` for `one-per-page`. Rotates page (not image) to match aspect — landscape image gets a landscape page. Disable with `--no-auto-orient`.

#### Procedure

1. Detect tool availability:
   - `which img2pdf` — preferred path.
   - `which magick || which convert` — fallback for cases img2pdf can't handle.
   - If neither exists, point at `install-deps`.

2. Enumerate inputs in the requested sort order (image extensions only: jpg, jpeg, png, webp, tiff, gif). Skip non-image files with a one-line note.

3. **Mode: `one-per-page` with img2pdf** — preferred path because img2pdf embeds JPEG bytes losslessly (no re-encode):

   ```bash
   img2pdf \
     --pagesize "$paper_spec" \
     --imgsize "$paper_minus_margins" \
     --fit into \
     --auto-orient \
     -o "$output" \
     "${files[@]}" \
     || { echo "img2pdf failed — see stderr above; not falling through silently" >&2; exit 1; }
   ```

   Collect the inputs into a bash array (`files=()`, `files+=( "$f" )` per match) and expand as `"${files[@]}"`. A bare unquoted file list word-splits on the first path containing a space.

   `--fit into` keeps aspect ratio, fits within page minus margins. `--auto-orient` rotates pages to match image aspect.

   img2pdf accepts JPEG, PNG, TIFF natively. For other formats (WebP, HEIC, AVIF), pre-convert to PNG via vipsthumbnail and stage in a temp directory; img2pdf will re-embed losslessly.

4. **Mode: `multi-up`** — img2pdf doesn't natively grid; build an intermediate composite per page using ImageMagick `montage`:

   ```bash
   # for each chunk of N files:
   montage "${chunk[@]}" -tile "${cols}x${rows}" \
     -geometry "${cell_w}x${cell_h}+${margin}+${margin}" \
     -background white \
     "$staged/page-$idx.png"
   ```

   Then feed the staged page PNGs to img2pdf as `one-per-page` against the chosen paper size. Cell dimensions = `(paper-w - 2*outer-margin) / cols - cell-margin` and similar for height.

   Layout mapping: `--per-page 2` = 1×2 portrait or 2×1 landscape (orient by paper); `4` = 2×2; `6` = 2×3 (portrait) / 3×2 (landscape); `9` = 3×3.

5. **Mode: `as-is`** — straight pass-through:

   ```bash
   img2pdf -o "$output" "${files[@]}"
   ```

   No `--pagesize` or `--imgsize`; img2pdf uses each image's native dimensions and DPI.

6. **ImageMagick fallback** (only if img2pdf is missing or chokes on a format):

   ```bash
   magick -density "$dpi" "${files[@]}" \
     -page "$paper_spec" \
     -gravity center \
     -background white \
     -extent "$paper_spec" \
     -compress jpeg -quality 90 \
     "$output"
   ```

   Two things about the ordering. `-density` is a *setting*, not an operator: it applies only to images read after it appears, so placing it at the end of the command leaves the sources decoded at their default density and the requested DPI silently does nothing. Likewise `-background white` must precede `-extent`, or the padding colour on non-matching aspect ratios is whatever the current background happens to be rather than the white a print shop expects.

   `magick` is the ImageMagick 7 entry point (`convert` is the v6 name, deprecated in v7).

   This re-encodes JPEGs (quality loss), so prefer img2pdf when possible. Surface a warning when falling back.

7. Verify output. Check the exit status of whichever tool ran — do not report success on a non-zero exit — then confirm the artefact:

   ```bash
   pdfinfo "$output" || { echo "output is not a readable PDF" >&2; exit 1; }
   ```

   If `pdfinfo` is unavailable, check the file is non-empty and starts with the `%PDF` magic. Report the page count.

#### Output

- The PDF at the resolved path.
- Summary: `<n> images → <output> (<pages> pages, <size-MB>MB)`.
- Mode used + tool used (img2pdf primary / ImageMagick fallback).
- List of any skipped or staged-via-conversion files.

#### Notes

- `one-per-page` with auto-orient is the default because real-world prints want each photo at maximum size on the page regardless of original orientation. Disable for documents/contracts where every page must be uniform portrait.
- img2pdf is the right default: lossless JPEG embedding means the output PDF is essentially the JPEGs in a PDF wrapper — no quality loss, smallest possible file. ImageMagick re-encodes; only fall back when forced.
- For very large input sets (>200 images) ImageMagick `montage` becomes slow on multi-up mode — chunk and parallelise. For one-per-page mode, img2pdf handles thousands of pages without issue.
- Paper-size internals: A4 = 210×297mm, A3 = 297×420mm, A5 = 148×210mm, Letter = 8.5×11in (215.9×279.4mm), Legal = 8.5×14in, Tabloid = 11×17in.
- Print-shop-friendly defaults: A4, 10mm margin, 300 DPI assumption, auto-orient on. Override only with explicit reason.
- For mixed orientations in `as-is` mode without auto-orient, the resulting PDF will have heterogeneous page sizes — many printers handle this but some don't. Default to `one-per-page` with auto-orient for printer reliability.

---

### Install Dependencies

**Name.** `install-deps`

**When to use.** Provision the plugin's tools — system binaries via the host package manager, Python tools into a plugin-owned uv venv at <data-dir>/venv/. Idempotent doctor — run before any command reports a missing dep. Never touches system Python or fights PEP 668.

Two surfaces:

1. **System binaries** — required: `ImageMagick`, `exiftool`. Optional: `libvips-tools`, `libheif-examples`, `oxipng`, `pngquant`, `jpegoptim`, `mozjpeg`, `libavif-bin`, `libjxl-tools`, `realesrgan-ncnn-vulkan`, `darktable-cli`.
2. **Python tools** — `imagehash`, `Pillow` (perceptual dedupe). Installed into a plugin-owned uv venv at `<data-dir>/venv/`.

The plugin invokes Python via `<data-dir>/venv/bin/python`, so the user's system Python stays untouched and PEP 668 / externally-managed-environment errors never occur.

#### Resolve paths

```bash
PLUGIN_DATA_DIR="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops"
VENV_DIR="$PLUGIN_DATA_DIR/venv"
```

#### Rules for this skill

**Confirm with the user before executing any command that installs software, and always before a `sudo` command.** Show the exact command, say what it installs, and wait. This applies to every row of the matrix below and to the `uv` bootstrap — not just to the ones that carry an inline caveat. `Bash(sudo *)` is an unrestricted root grant; the confirmation step is what bounds it.

Never install anything the user did not ask for. A missing *optional* tool is a reported status, not a task.

#### Procedure

##### 1. Detect host

```bash
uname -s
which apt-get apt brew dnf pacman 2>/dev/null
which uv 2>/dev/null
```

Record what's available; this drives which install commands you propose.

##### 2. Ensure `uv` is available

`uv` is the only hard prerequisite for the Python side. If missing, propose:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ask before running. This pipes a remote script straight into a shell with no checksum or signature check — say so when you propose it, and offer the alternatives (`brew install uv`, `pipx install uv`, or the distro package) for users who would rather not. Fall back to system pip with `--break-system-packages` only if the user declines all of them — prefer `uv`.

##### 3. Walk the system-binary matrix

| Tool | Detect | Required? | Install (apt) | Install (brew) |
|---|---|---|---|---|
| `magick` / `convert` / `identify` | `which magick \|\| which convert` | required | `sudo apt install imagemagick` | `brew install imagemagick` |
| `exiftool` | `which exiftool` | required | `sudo apt install libimage-exiftool-perl` | `brew install exiftool` |
| `fdupes` | `which fdupes` | optional | `sudo apt install fdupes` | `brew install fdupes` |
| `vips` / `vipsthumbnail` | `which vips` | optional (recommended >500 images) | `sudo apt install libvips-tools` | `brew install vips` |
| `heif-convert` | `which heif-convert` | optional | `sudo apt install libheif-examples` | `brew install libheif` |
| `oxipng` | `which oxipng` | optional | `sudo apt install oxipng` | `brew install oxipng` |
| `pngquant` | `which pngquant` | optional | `sudo apt install pngquant` | `brew install pngquant` |
| `jpegoptim` | `which jpegoptim` | optional | `sudo apt install jpegoptim` | `brew install jpegoptim` |
| `mozjpeg` | `ls "$(brew --prefix mozjpeg 2>/dev/null)/bin/cjpeg" /opt/mozjpeg/bin/cjpeg 2>/dev/null` | optional | build from source, or a distro package if one exists | `brew install mozjpeg` |
| `avifenc` | `which avifenc` | optional | `sudo apt install libavif-bin` | `brew install libavif` |
| `cjxl` / `djxl` | `which cjxl` | optional | `sudo apt install libjxl-tools` | `brew install jpeg-xl` |
| `upscayl-bin` | `which upscayl-bin \|\| ls /opt/Upscayl/resources/bin/upscayl-bin 2>/dev/null` | optional | install Upscayl from <https://upscayl.org> (deb / flatpak / appimage) | install Upscayl from <https://upscayl.org> |
| `realesrgan-ncnn-vulkan` (fallback) | `which realesrgan-ncnn-vulkan` | optional | binary release from upstream | binary release from upstream |
| `darktable-cli` | `which darktable-cli` | optional | `sudo apt install darktable` (GUI + CLI) | `brew install darktable` |
| `img2pdf` | `which img2pdf` | optional | `uv tool install img2pdf` (or `sudo apt install python3-img2pdf`) | `pipx install img2pdf` |

For each: if missing, stage the install command tagged required/optional. Required tools that are missing block the install — surface that clearly.

`realesrgan-ncnn-vulkan` and `mozjpeg` are not in apt — for those, point the user at the upstream releases page rather than auto-downloading. Ask before placing binaries under `~/bin/`.

**mozjpeg's binaries are named `cjpeg` / `djpeg` / `jpegtran`, exactly like libjpeg-turbo's.** Homebrew keeps the formula keg-only so it does not shadow the system copies, which means `which cjpeg` finding something proves nothing about mozjpeg. Detect it by prefix path (as in the matrix row above) and report the resolved directory in the status table — `optimize-jpeg` and `web-ready` both need that path, not a bare binary name.

##### 4. Provision the venv

If `<VENV_DIR>` doesn't exist:

```bash
uv venv "$VENV_DIR" --python 3.11
```

If it exists, leave it.

##### 5. Install Python packages into the venv

| Package | Required? | Used by |
|---|---|---|
| `Pillow` | required | dedupe (perceptual), inspection |
| `imagehash` | required | dedupe (perceptual) |
| `numpy` | required (Pillow/imagehash dep) | dedupe |
| `cairosvg` | optional | `svg-to-raster` (SVG → PNG/PDF). Needs system `libcairo2` (preinstalled on most Linux/macOS). |
| `vtracer` | optional | `vectorize` (raster → SVG). Self-contained wheel (bundled Rust binary). |
| `opencv-python-headless` | optional | `auto-deskew` photo mode (Hough-line skew detection). |

Stage:

```bash
uv pip install --python "$VENV_DIR/bin/python" Pillow imagehash numpy
# Optional — only if the user wants SVG conversion / vectorization / photo deskew:
uv pip install --python "$VENV_DIR/bin/python" cairosvg vtracer opencv-python-headless
```

Targeting `--python "$VENV_DIR/bin/python"` avoids `source`-ing an activate script, whose effect would not survive to the next command anyway — each Bash call gets a fresh shell.

If `cairosvg` import fails at runtime with a libcairo error, prompt the user to install the system lib: `sudo apt install libcairo2` (Linux) / `brew install cairo` (macOS).

##### 6. Verify

After installs, re-run the detect commands and report a green/red status table per tool. Surface install commands the user still needs to run themselves (sudo, cargo).

#### Output

Single status report:
- Required system bins: present / missing.
- Optional system bins: present / missing (with one-line reason to install each).
- mozjpeg: the resolved prefix directory, or missing.
- Venv: provisioned at `<VENV_DIR>`, Python `<version>`.
- Python packages: installed.

Refuse to mark "OK" if any required tool is missing.

---

### Nano Tech Diagrams

**Name.** `nano-tech-diagrams`

**When to use.** Create and edit tech diagrams via a nano-tech-diagrams MCP server (Nano Banana 2 through Fal AI). Text-to-image, image-to-image, whiteboard cleanup, and 28+ style presets. Requires an externally configured MCP server — this plugin does not ship one.

This skill drives a **nano-tech-diagrams** MCP server to create and transform tech diagrams using Fal AI's Nano Banana 2 model.

#### Prerequisite: the MCP server is not bundled

This plugin does **not** ship or configure any MCP server. Before this skill can do anything, the user must have configured, in their own `.mcp.json` or Claude Code MCP settings:

1. A **nano-tech-diagrams** server exposing `list_styles`, `list_diagram_types`, `whiteboard_cleanup`, `image_to_image`, and `text_to_image`.
2. If that server runs anywhere other than the local machine, an **S3-compatible object store** server (e.g. MinIO) exposing a presign tool, used for file staging below.

Tool names are namespaced by whatever the user called their server, so they take the shape `mcp__<server-name>__nano-tech-diagrams__*` and `mcp__<store-name>__presign_url`. Resolve the actual names from the tools available in session rather than assuming any particular deployment.

**If neither server is configured, say so and stop.** There is no local fallback — Nano Banana 2 is a hosted model.

#### File Staging

Skip this section entirely when the MCP server runs on the same machine as the files and accepts local paths.

When the server runs remotely it cannot read local file paths, and a local-path call fails with `ENOENT`. For any tool that takes an `image_path`, upload the file to the object store and pass a presigned GET URL instead — the MCP accepts `http(s)` URLs directly.

Ask the user for the staging bucket name the first time; do not assume one.

##### Staging workflow:
1. **Presign a PUT URL**: `presign_url(bucket="<staging-bucket>", key="staging/<filename>", method="put")`
2. **Upload**:
   ```bash
   curl -sSf -X PUT -T "/local/path/to/image.jpg" "$put_url" \
     || { echo "Upload failed — check the presigned URL has not expired" >&2; exit 1; }
   ```
   `-f` matters: without it curl exits 0 on an HTTP error and the pipeline proceeds with a URL that serves nothing.
3. **Presign a GET URL** for the same key (`method="get"`) and pass it as `image_path` to the MCP tool.
4. Presigned URLs are short-lived (commonly 1 hour; check the `expires` param). If a call fails with a 403 or `SignatureDoesNotMatch`, re-presign rather than retrying the stale URL. Objects in a `*-transient` style bucket typically expire on a lifecycle policy — do not treat staged files as durable storage.

##### Batch staging:
For multiple files, repeat the presign-PUT/curl/presign-GET cycle per file (presign calls can be batched), collect the URLs, then call the MCP tools. If any upload fails, record which file and continue with the rest; report the failures at the end.

##### When staging is NOT needed:
- `text_to_image` — no input image required
- When `image_path` is already an `http://` or `https://` URL (Fal media, any public host)

#### Saving output locally

The MCP returns a `fal.media` URL. If the server has a `download_to` parameter, note that it writes to the *server's* filesystem — which is not the local one when the server is remote. Download the returned URL directly:

```bash
curl -fsSL -o "/absolute/local/path/output.png" "$fal_url" \
  || { echo "Download failed — the fal.media URL may have expired" >&2; exit 1; }
file "/absolute/local/path/output.png"
```

Keep `-f` and verify with `file` before reporting success: without them a expired-link HTML error page lands on disk named `.png` and is reported as a generated diagram.

#### Available Tools

| Tool | Purpose |
|------|---------|
| `list_styles` | Show all 28+ visual style presets (key, name, category, default aspect ratio) |
| `list_diagram_types` | Show all diagram type presets (network, flowchart, mind map, etc.) |
| `whiteboard_cleanup` | Clean up a whiteboard photo into a polished diagram |
| `image_to_image` | Transform an existing image into a styled tech diagram |
| `text_to_image` | Generate a diagram from a text description (no input image) |

#### Defaults

- **Model**: Nano Banana 2 (baked in, not configurable)
- **Resolution**: 1K (default)
- **Reasoning**: Minimal (default)
- **Output format**: PNG
- **Aspect ratio**: auto (pass as parameter to override)

#### Workflow

##### For whiteboard cleanup:
1. Stage the image if the server is remote (presign PUT, `curl -T`, presign GET; see "File Staging" above)
2. Optionally ask about style preference — default is `clean_polished`
3. Call `whiteboard_cleanup` with the presigned URL as `image_path`
4. If domain-specific terms are present, pass them as `dictionary_words` for accurate spelling
5. Download the returned `fal.media` URL locally (see "Saving output" above) (see "Saving output" above)

##### For image-to-image transformation:
1. Stage the image if the server is remote (presign PUT, `curl -T`, presign GET; see "File Staging" above)
2. Determine what transformation is needed: style change, diagram type conversion, or custom prompt
3. Call `image_to_image` with at least one of: `prompt`, `style`, or `diagram_type`, and the presigned URL as `image_path`
4. Common combos: `style=blueprint` + `diagram_type=network_diagram`
5. Download the returned `fal.media` URL locally (see "Saving output" above)

##### For text-to-image generation:
1. Get the user's description of what diagram they want
2. Pick an appropriate `diagram_type` if it matches a preset
3. Pick a `style` if the user has a visual preference
4. Call `text_to_image` — no staging needed (no input image)
5. Download the returned `fal.media` URL locally (see "Saving output" above)

#### Style Categories

- **Professional**: clean_polished, corporate_clean, hand_drawn_polished, minimalist_mono, ultra_sleek, blog_hero
- **Creative**: colorful_infographic, comic_book, isometric_3d, neon_sign, pastel_kawaii, pixel_art, stained_glass, sticky_notes, watercolor
- **Technical**: blueprint, dark_mode, flat_material, github_readme, photographic, terminal_hacker, visionary
- **Retro & Fun**: chalkboard, psychedelic, mad_genius, retro_80s, woodcut
- **Language**: bilingual_hebrew, translated_hebrew

#### Diagram Types

- **Infrastructure**: network_diagram, cloud_architecture, kubernetes_cluster, server_rack
- **Software**: system_architecture, microservices, api_architecture, database_schema
- **Process**: flowchart, decision_tree, sequence_diagram, state_machine, pipeline
- **Conceptual**: mind_map, wireframe, gantt_chart, comparison_table, org_chart

#### Notes

- For batch processing, call tools sequentially to avoid API rate limits
- The `dictionary_words` parameter helps with domain-specific terminology (e.g., ["Kubernetes", "Proxmox", "PostgreSQL"])
- Aspect ratio options: auto, 1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, 21:9, 9:21
- Resolution options: 0.5K, 1K (default), 2K, 4K
- Staging buckets are usually configured with a short object lifecycle and presigned URLs with a ~1-hour TTL. Both are properties of the user's own deployment, not of this skill — check them if calls start failing mid-batch.
- Every MCP call can fail (rate limit, model error, expired credential). Surface the server's error text to the user rather than retrying blindly; only presigned-URL expiry is worth an automatic re-presign and one retry.

---

### New Image Project

**Name.** `new-project`

**When to use.** Create a new image project inside the user's registered image workspace. Use when the user says "new image project", "create an image project called X", "scaffold a new image set", or similar. Creates a project subfolder with source, working, exports, references layout and an optional git init.

Scaffold a project folder inside the registered image workspace.

#### Procedure

##### 1. Resolve the workspace

```bash
CONFIG="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/workspace.json"
test -f "$CONFIG" || { echo "No workspace registered — run workspace-setup first."; exit 1; }
# jq is the happy path. The fallback must be portable: `grep -oP` is GNU-only and
# errors out on macOS's BSD grep — the very case the fallback covers.
WS=$(jq -r .path "$CONFIG" 2>/dev/null) \
  || WS=$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG")
test -d "$WS" || { echo "Workspace path missing: $WS — run workspace-setup."; exit 1; }
```

##### 2. Ask for project metadata

- **Name** — required. Slugify (lowercase, hyphens for spaces).
- **Version control** — ask; default **no**.

##### 3. Create the layout

```bash
PROJ="$WS/$slug"
test -e "$PROJ" && { echo "Already exists: $PROJ"; exit 1; }
mkdir -p "$PROJ"/{source,working,exports,references,thumbnails} \
  || { echo "Could not create $PROJ — check permissions on $WS"; exit 1; }
```

| Folder         | Purpose                                                    |
|----------------|------------------------------------------------------------|
| `source/`      | Original images — never edited in place                    |
| `working/`     | In-progress edits, layered files (PSD, XCF, AFPHOTO)       |
| `exports/`     | Final deliverables (web JPEG/WebP, print TIFF, etc.)       |
| `references/`  | Mood boards, reference images, prompts                     |
| `thumbnails/`  | Small previews for indexing                                |

Write a `README.md` in the project root with the slug, the ISO date from `date +%Y-%m-%d`, and a notes section.

##### 4. (Optional) git init

If the user wants version control, run `git init "$PROJ"` and add a `.gitignore` excluding `source/` and `exports/` if they're large. Nothing else in this skill touches git — do not commit, add a remote, or push.

##### 5. Confirm

Print the project path. Offer to `cd` or open in a terminal.

---

### New Image Workflow

**Name.** `new-workflow`

**When to use.** Scaffold a multi-touchpoint image workflow inside the registered image workspace — a structured pipeline with explicit human review gates and optional cloud-AI generation/edit steps (Fal nano-banana via MCP). Use when the user says "new image workflow", "scaffold a workflow", "set up an image pipeline", "iterative image project", or describes a job that needs multiple rounds of generation → review → revision → export.

Scaffold a structured, multi-stage image workflow inside the user's registered image workspace. Unlike `new-project` (a flat source/working/exports layout), a workflow expects **iteration**: generation, human review, revision, and export are explicit stages, each with their own folder and manifest entry.

Cloud AI (Fal nano-banana via a `nano-tech-diagrams` MCP server) is wired in as an optional driver for the generation and revision stages. That server is **not** shipped with this plugin — see the `nano-tech-diagrams` skill for what the user has to configure. If it is not available, scaffold the workflow with driver `none` and say so; the folder structure and review gates are useful on their own.

#### When to use this vs. new-project

- **`new-project`** — single batch of images, photo-editing style, no iteration loop.
- **`new-workflow`** — generative or hybrid work with multiple touchpoints: brief → references → generate → review → revise → export. Use when the user expects to come back to the project across several sessions and wants a stable structure to resume into.

#### Procedure

##### 1. Resolve the workspace

```bash
CONFIG="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/workspace.json"
test -f "$CONFIG" || { echo "No workspace registered — run workspace-setup first."; exit 1; }
WS=$(jq -r .path "$CONFIG" 2>/dev/null) \
  || WS=$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG")
test -d "$WS" || { echo "Workspace path missing: $WS — run workspace-setup."; exit 1; }
```

The `sed` fallback covers a host without `jq`; `grep -oP` would not, since macOS ships BSD grep with no PCRE support.

##### 2. Gather workflow metadata

Ask (or infer if obvious):

- **Name** — required. Slugify (lowercase, hyphens).
- **Brief** — one or two sentences describing the deliverable.
- **Cloud-AI driver** — `fal-nano-banana` if a nano-tech-diagrams MCP server is configured in this session, otherwise `none`. Also use `none` when the user is bringing their own images. Resolve the actual tool namespace from the tools available in session rather than assuming a server name.
- **Expected rounds** — how many revision cycles to scaffold (default 3).
- **Final aspect ratio / resolution** — for export-stage placeholders.

##### 3. Create the layout

```bash
PROJ="$WS/$slug"
test -e "$PROJ" && { echo "Already exists: $PROJ"; exit 1; }
mkdir -p "$PROJ"/{01-brief,02-references,03-generation,04-review,05-revision,06-export,_manifest} \
  || { echo "Could not create $PROJ — check permissions on $WS"; exit 1; }

# Brace expansion happens before variable expansion, so `round-{1..$ROUNDS}`
# would create one literal directory named `round-{1..$ROUNDS}`. Loop instead.
for i in $(seq 1 "$ROUNDS"); do
  mkdir -p "$PROJ/05-revision/round-$i"
done
```

| Stage              | Purpose                                                                 | Touchpoint? |
|--------------------|-------------------------------------------------------------------------|:-----------:|
| `01-brief/`        | `brief.md` — goal, audience, constraints, do/don't list                 | ✓ user      |
| `02-references/`   | Mood board, reference images, prompt fragments                          | ✓ user      |
| `03-generation/`   | First-pass generations (Fal output lives here)                          | ai          |
| `04-review/`       | Selected candidates from `03-generation/` + review notes                | ✓ user      |
| `05-revision/`     | Per-round sub-folders with revised generations + notes                   | ai + user   |
| `06-export/`       | Final deliverables — sized, formatted, metadata-scrubbed                | ai          |
| `_manifest/`       | `workflow.json` — pipeline state; `prompts.md` — running prompt log     | ai          |

##### 4. Write the manifest

`$PROJ/_manifest/workflow.json`:

```json
{
  "slug": "<slug>",
  "created": "<ISO date>",
  "brief": "<one-line summary>",
  "driver": "fal-nano-banana | none",
  "stages": [
    {"id": "01-brief",       "status": "pending", "type": "human"},
    {"id": "02-references",  "status": "pending", "type": "human"},
    {"id": "03-generation",  "status": "pending", "type": "ai"},
    {"id": "04-review",      "status": "pending", "type": "human"},
    {"id": "05-revision",    "status": "pending", "type": "ai+human", "rounds": <ROUNDS>, "current_round": 0},
    {"id": "06-export",      "status": "pending", "type": "ai"}
  ],
  "final": {"aspect_ratio": "<...>", "resolution": "1K", "format": "png"}
}
```

##### 5. Seed templates

- `01-brief/brief.md` — markdown template with sections: Goal, Audience, Deliverables, Constraints, Do, Don't, Reference Links.
- `_manifest/prompts.md` — append-only log; one heading per generation call with the prompt, model params, and resulting filenames.
- `README.md` at project root — slug, brief, driver, ISO date, stage checklist (mirrors `workflow.json`), and a "Resume here" pointer to the first non-`done` stage.

##### 6. (Optional) git init

If the workspace itself is a git repo (check `git -C "$WS" rev-parse --git-dir`), the new workflow is automatically tracked — no separate init. Otherwise, ask whether to `git init` the project folder.

##### 7. Confirm and hand off

Report:
- Project path
- Current stage (`01-brief`)
- Next action (open `01-brief/brief.md` and fill in)

#### Driving the workflow

Subsequent sessions resume by reading `_manifest/workflow.json` and continuing from the first stage with `status != "done"`.

##### Cloud AI generation (stage 03 + 05)

When the active stage is `ai`-typed and the driver is `fal-nano-banana`:

1. Read the brief + references; compose a dense one-paragraph prompt — concrete subject, composition, style, and palette in a single paragraph, no bullet lists.
2. Call the server's `text_to_image` tool with `resolution: "1K"` and the configured aspect ratio. For revision rounds that build on a prior image, use `image_to_image` and pass the selected candidate. Use whatever namespace the configured server exposes (the `nano-tech-diagrams` skill covers staging local files for a remote server).
3. Download the returned `fal.media` URL into the stage folder:
   ```bash
   out="$PROJ/03-generation/$(date +%s)-$slug.png"
   curl -fsSL -o "$out" "$fal_url" \
     || { echo "download failed — the fal.media URL may have expired" >&2; exit 1; }
   file "$out"
   ```
   `-f` is what makes this safe: without it curl exits 0 on an HTTP error and writes the error page to disk as a `.png`, which then gets logged as a generated candidate. Verify with `file` before recording it.
4. Append a log entry to `_manifest/prompts.md`: stage, round, prompt, params, output filename.
5. Mark the stage `awaiting-review` in `workflow.json` and surface the candidates to the user.

##### Human touchpoints (stage 01, 02, 04, 05-review)

At each human stage, **stop and prompt the user**. Do not auto-advance. Show:
- What was just produced (file list, thumbnails if available)
- The decision needed (which candidates to keep, what to change, etc.)
- Where to record the decision (a `notes.md` in the stage folder)

After the user records the decision, mark the stage `done` and advance.

##### Export (stage 06)

When all revision rounds are `done`:

1. Take the selected final images from the last `05-revision/round-N/` folder.
2. Apply: resize to target resolution, convert to target format, scrub metadata — via the `fast-resize`, `convert-to-avif`, `optimize-jpeg`, and `scrub-metadata` skills, or `web-ready` to do all of it in one pass.
3. Write to `06-export/` with stable filenames (`<slug>-<variant>.<ext>`).
4. Mark stage `done`.

#### Notes

- Don't overwrite existing files in `03-generation/` or `05-revision/round-*/` — always timestamp-prefix.
- The manifest is the source of truth; the README is a human-readable mirror, regenerate it from the manifest when state changes.
- If the user changes the driver mid-flow (e.g., switches from cloud-AI to bringing their own), update `workflow.json` and note it in `prompts.md`.

---

### Open Image Workspace

**Name.** `open-workspace`

**When to use.** Open the user's registered image workspace folder. Use when the user says "open my image workspace", "take me to my image workspace", or similar. Reads the path from workspace.json and opens a terminal (or Finder/file manager) there.

```bash
CONFIG="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/workspace.json"
test -f "$CONFIG" || { echo "No image workspace registered. Run workspace-setup first."; exit 1; }

# jq is the happy path. The fallback must be portable: `grep -oP` is GNU-only and
# errors out on the BSD grep that ships with macOS, which is exactly the case the
# fallback exists to cover.
WS=$(jq -r .path "$CONFIG" 2>/dev/null) \
  || WS=$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG")
test -d "$WS" || { echo "Workspace path missing: $WS"; exit 1; }

case "$(uname -s)" in
  Darwin)
    open -a Terminal "$WS" || open "$WS"
    ;;
  *)
    if command -v konsole >/dev/null; then
      konsole --workdir "$WS" &
    elif command -v gnome-terminal >/dev/null; then
      gnome-terminal --working-directory="$WS" &
    elif command -v xdg-open >/dev/null; then
      xdg-open "$WS" &
    else
      echo "No terminal opener found — printing the path only." >&2
    fi
    ;;
esac

echo "Workspace: $WS"
ls -la "$WS"
```

`konsole` / `gnome-terminal` / `xdg-open` are Linux-only and none exist on macOS, so without the `Darwin` branch the script silently falls through and opens nothing. Always print the path regardless of whether an opener was found — that is the part the user can still act on.

If config is missing or stale, redirect to `workspace-setup`.

---

### Optimize JPEG

**Name.** `optimize-jpeg`

**When to use.** Use when the user wants to shrink JPEG files — losslessly with `jpegoptim` (~5–15% reduction, no re-encode) or with re-compression via `mozjpeg` (~10–15% better than libjpeg-turbo at the same visual quality). Web-prep workhorse for photo libraries.

**Triggers.** compress these JPEGs, make these photos smaller, optimise my JPEG folder for web

Squeeze JPEG file size. Two modes:

- **lossless** (default) — `jpegoptim --strip-all`. Repacks Huffman tables and strips metadata. No re-encode, no quality change.
- **recompress** — `mozjpeg`. Re-encodes with better quantisation tables; 10–15% smaller than libjpeg-turbo for the same SSIM. Quality flag controls trade-off. Always strips metadata (see step 4).

#### When to use

- Web-prep: photo galleries, blog images, anything destined for upload.
- Archive squeeze: lossless mode is the no-regret option for any JPEG-heavy folder.
- Pre-step inside `web-ready` orchestrator.

Do **not** use this skill when:
- Source is PNG → use `optimize-png`.
- Source is HEIC/RAW/TIFF — pipe through `web-ready` (or convert first).
- The JPEG is already heavily compressed (<70% quality estimate) — recompress will visibly degrade.

#### Inputs

1. **Input** — file or directory. Required.
2. **Mode** — `lossless` (default) or `recompress`.
3. **Recursive** — `--recursive` for directory descent.
4. **In-place** — default. `--output-dir <path>` to write copies.
5. **Quality** (mode=recompress) — `cjpeg -quality N`. Default `82` (web-quality). `90` for archival; `75` for aggressive web compression.
6. **Strip metadata** — default `on` for both modes. EXIF/IPTC/XMP gone. `--keep-metadata` is honoured in **lossless mode only** (drop `--strip-all`). Recompress always loses metadata at the decode step; the skill re-injects it afterwards with `exiftool` when `--keep-metadata` is set — see step 4.
7. **Progressive** — default `on`. Smaller files + better perceived load. `--baseline` to disable for compatibility with very old decoders.

#### Procedure

1. Verify the relevant binary.

   **Lossless:** `which jpegoptim`. If missing, point at `install-deps` and stop.

   **Recompress:** mozjpeg ships its `cjpeg`/`djpeg`/`jpegtran` under the *standard* names, but the package is deliberately kept off the default PATH so it does not shadow libjpeg-turbo. Resolve the real prefix before use — do **not** assume a `-mozjpeg` suffixed binary exists:

   ```bash
   # Resolve MOZ_BIN: directory containing mozjpeg's cjpeg/djpeg/jpegtran
   MOZ_BIN=""
   for d in \
     "$(brew --prefix mozjpeg 2>/dev/null)/bin" \
     /opt/mozjpeg/bin \
     /usr/local/opt/mozjpeg/bin
   do
     [ -x "$d/cjpeg" ] && { MOZ_BIN="$d"; break; }
   done
   if [ -z "$MOZ_BIN" ]; then
     echo "mozjpeg not found — install it (see install-deps), or use mode=lossless" >&2
     exit 1
   fi
   ```

   If `MOZ_BIN` cannot be resolved, do not silently fall through to the system `cjpeg` — that is plain libjpeg-turbo and gives none of the promised gain. Report it and offer lossless mode instead.

2. Enumerate inputs (JPEG/JPG only — skip with note).

3. **Lossless** (jpegoptim):

   ```bash
   jpegoptim --strip-all --all-progressive ${outdir:+--dest "$outdir"} "$input" \
     || echo "FAILED: $input" >> "$failed_log"
   ```

   `--all-progressive` forces progressive output (smaller). `--strip-all` removes EXIF/IPTC/XMP/comments. Drop these if `--keep-metadata` was set.

4. **Recompress** (mozjpeg):

   mozjpeg's CLI is decode-then-encode. **Never redirect into the input path** — the shell truncates the redirect target before `djpeg` reads it, destroying the source. Always encode to a temp file and move it into place only on success:

   ```bash
   tmp="$(mktemp "${input}.XXXXXX.jpg")"
   if "$MOZ_BIN/djpeg" "$input" \
        | "$MOZ_BIN/cjpeg" -quality "$q" -progressive -optimize > "$tmp"
   then
     # --keep-metadata: recompress decodes to raw PPM, so EXIF/IPTC/XMP/ICC are
     # gone by this point. Re-inject from the original before the swap.
     if [ "$keep_metadata" = "yes" ]; then
       exiftool -overwrite_original -tagsFromFile "$input" -all:all "$tmp" || {
         echo "FAILED (metadata re-inject): $input" >&2; rm -f "$tmp"; continue; }
     fi
     mv "$tmp" "$output"
   else
     echo "FAILED (recompress): $input" >&2
     rm -f "$tmp"
     continue
   fi
   ```

   When `$output` equals `$input` this is the in-place path and it is safe: the original is only replaced after a successful encode.

   Or use `"$MOZ_BIN/jpegtran"` for lossless transforms when only metadata stripping + Huffman repack is desired (essentially a faster jpegoptim). `jpegtran` reads and writes JPEG directly, so it preserves metadata and needs no re-injection — but it too must go via a temp file for in-place use.

   For batch, parallelise with `xargs -P <ncpu>` where `<ncpu>` is `$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)`.

5. Sanity-check: any output file >95% of input size in recompress mode — keep the original instead. mozjpeg occasionally inflates already-optimised inputs. Compare with `stat` before the `mv`:

   ```bash
   in_sz=$(wc -c < "$input"); out_sz=$(wc -c < "$tmp")
   if [ "$out_sz" -ge $(( in_sz * 95 / 100 )) ]; then
     rm -f "$tmp"; echo "KEPT ORIGINAL (no gain): $input"; continue
   fi
   ```

6. Collect failures. Every `FAILED:` line emitted above feeds the summary in the Output section — do not report success counts without also reporting the failure list.

#### Output

- Optimised JPEGs at the resolved paths.
- Summary:
  - Files processed / skipped / failed / kept-original (where recompress would have inflated).
  - Total: `<orig-MB>` → `<new-MB>` (`<pct>%` saved).
  - Visible-quality flag: if recompress was used and the source had a quality estimate <75 (via `identify -format "%Q"`), surface a warning per file.

#### Notes

- mozjpeg is a drop-in libjpeg-turbo replacement with smarter trellis quantisation. It's slower than libjpeg-turbo by ~3× — fine for web-prep, not for thumbnail generation.
- mozjpeg's binaries are named `cjpeg` / `djpeg` / `jpegtran`, identical to libjpeg-turbo's. That is why step 1 resolves an explicit prefix rather than calling them bare: a bare `cjpeg` on PATH is almost always libjpeg-turbo's.
- For "I just want it smaller, don't touch quality": always use `lossless` mode. Free win.
- The orchestrator (`web-ready`) defaults to: resize first, then encode WebP/AVIF, fall back to mozjpeg for JPEG output. This skill exists to do JPEG-only optimisation without that pipeline.

---

### Optimize PNG

**Name.** `optimize-png`

**When to use.** Use when the user wants to shrink PNG files in a batch — losslessly with `oxipng` (typical 20–40% reduction, byte-identical decode) or aggressively with `pngquant` (lossy palette quantisation, 60–80% reduction with near-imperceptible quality loss for web use). Web-prep workhorse.

**Triggers.** these PNGs are huge, compress my screenshots, optimise this folder of UI assets

Squeeze PNG file size. Two modes:

- **lossless** (default) — `oxipng`. Byte-identical decode. Always safe.
- **lossy** — `pngquant`. Palette-quantised; visible artefacts only on smooth gradients. Right call for web/UI assets.

#### When to use

- Web-prep: PNG screenshots, UI assets, illustrations destined for upload.
- Archival: shave a few hundred MB off a folder of PNG masters losslessly.
- Pre-step inside `web-ready` orchestrator.

Do **not** use this skill when:
- Source is JPEG → use `optimize-jpeg`.
- Source is RAW/HEIC/TIFF → run `web-ready` end-to-end first.
- Quality must be bit-perfect for cryptographic hashing → only use `lossless` mode.

#### Inputs

1. **Input** — file or directory. Required.
2. **Mode** — `lossless` (default) or `lossy`.
3. **Recursive** — `--recursive` for directory descent.
4. **In-place** — default. `--output-dir <path>` to write copies.
5. **Lossless level** (mode=lossless) — `oxipng -o <0..6>`. Default `4`. `6` is ~20% slower for ~1–2% extra compression.
6. **Lossy quality** (mode=lossy) — `pngquant --quality min-max`. Default `65-80` (web-good). Increase floor for sensitive material.
7. **Strip metadata** — default off. `--strip` removes EXIF/iTXt/zTXt/tIME chunks (oxipng `--strip safe`). Use when web-prep doesn't need camera info.

#### Procedure

1. Verify the relevant binary exists. `which oxipng` for lossless; `which pngquant` for lossy. If missing, point at `install-deps`.

2. Enumerate inputs (PNG only — skip non-PNG with a one-line note).

3. **Lossless** (oxipng):

   ```bash
   oxipng -o "$level" ${strip:+--strip safe} ${outdir:+--dir "$outdir"} "$input" \
     || echo "FAILED: $input" >> "$failed_log"
   ```

   In-place is the default. The output-directory flag is `-d` / `--dir <DIRECTORY>`; `--out` is oxipng's *single-file* output path and takes a file, not a directory — passing a directory to it fails. Pass `--dir` only if `--output-dir` was set. `oxipng` is multithreaded by default — no need to xargs-parallelise.

4. **Lossy** (pngquant):

   ```bash
   pngquant --quality "$min-$max" --skip-if-larger --strip --force \
     --output "$output" "$input" \
     || echo "FAILED: $input" >> "$failed_log"
   ```

   `--skip-if-larger` is critical — pngquant occasionally produces a larger file on already-quantised inputs; this prevents inflation.
   `--strip` removes optional chunks (default off in pngquant — explicitly enable for web-prep).
   `--force` is required whenever `$output` already exists, which is always true for the documented in-place default: without it pngquant refuses to overwrite and exits non-zero on every file.

5. Track total before/after sizes and report the savings:

   ```bash
   total() {
     find "$1" -type f -iname '*.png' -exec wc -c {} + \
       | awk '$NF == "total" { next } { s += $1 } END { print s+0 }'
   }
   ```

   Capture `total` before the run and again after, then report the difference. Read `$failed_log` for the failure list; report it next to the savings, never the savings alone.

#### Output

- Optimised PNG files at the resolved paths.
- Summary table:
  - Files processed / skipped / failed, with the failed paths from `$failed_log`.
  - Total: `<orig-MB>` → `<new-MB>` (`<pct>%` saved).
  - Worst compressors (files with <5% savings) — flag for inspection.

#### Notes

- `oxipng` lossless on a typical screenshot: 20–40% reduction. On already-optimised PNGs (e.g. via Photoshop "Save for Web"): often 1–5%.
- `pngquant` is irreversible. Keep originals if there's any chance the file will need further editing.
- For *animated* PNGs (APNG): both tools handle them but check output visually first.
- Combining lossy then lossless (`pngquant` → `oxipng`) gets a few extra % off — the orchestrator (`web-ready`) does this automatically; this skill keeps it as separate modes for explicit control.

---

### Extract Embedded Images from PDF

**Name.** `pdf-extract-embedded-images`

**When to use.** Use when the user wants to recover the images embedded in a PDF at their native resolution, without rasterizing the pages — a PDF that is essentially a wrapper around photos. For rendering whole pages to images instead, use `pdf-to-images`.

**Triggers.** get the photos out of this PDF, extract the original images from this brochure, recover the embedded pictures at full quality

Pull out JPEG and PNG objects embedded in a PDF using `pdfimages`. Extracts at native resolution without rasterizing the page. Different from `pdf-to-images` — this recovers the original embedded image files, not a rasterized page render.

#### When to use

- A PDF is a container for photos (e.g., a photo book or brochure) — you want the original images, not a rasterized version.
- Bulk-extracting image assets from a multi-page document without re-encoding.
- Recovering embedded images at their full embedded resolution and quality.

#### Inputs to gather

- **Input PDF file** — path to the PDF. Required.
- **Output directory** — optional. Default: current directory.

#### Procedure

##### 1. Check tooling

```bash
command -v pdfimages >/dev/null || {
  echo "pdfimages not installed — see the install-deps skill (poppler-utils)" >&2
  exit 1
}
```

##### 2. Validate PDF and inspect contents

```bash
file "$input"
pdfimages -list "$input" || { echo "not a readable PDF: $input" >&2; exit 1; }
```

The `-list` flag shows a summary of embedded images: page number, index, width, height, bits per component, color space, encoding. This helps set expectations (e.g., "3 JPEG images at 2400×3000px").

##### 3. Extract

```bash
mkdir -p "$outdir"
pdfimages -all "$input" "$outdir/$prefix" \
  || { echo "extraction failed for $input" >&2; exit 1; }
```

`-all` is shorthand for `-j -jp2 -jbig2 -ccitt`: it writes each image in its *native* encoding rather than dumping raw pixels. A JPEG stream comes out as `.jpg`, a JBIG2 stream as `.jb2`, and so on. It does not extract extra "alternate-format versions" — there is one output per embedded image.

**Alternatives:**

- `-j` — preserve native JPEG encoding for JPEG streams. It is an *encoding* switch, not a filter: non-JPEG images are still extracted, as raw `.ppm`/`.pbm` dumps.
- `-png` — write everything as PNG. Re-encodes non-PNG content; lossless output, but larger files and no longer byte-identical to what was embedded.

Recommend `-all` unless the user specifies otherwise — it is the only mode that never re-encodes.

##### 4. Report

After extraction:

- Count of images extracted, by type (JPEG, PNG, etc.).
- Output filenames and their dimensions.
- File sizes and whether any extraction failed.
- Remind the user that embedded images may have compression applied by the PDF creator — they are not necessarily at absolute maximum quality, but they are at their native resolution.

#### Output / side effects

- Image files created with names like `prefix-000.jpg`, `prefix-001.png`, etc. (depends on PDF content).
- Original PDF unchanged.

#### Notes

- **Native resolution, not PDF rendering resolution:** `pdfimages` extracts the raw embedded objects at the resolution they were embedded, not the page rendering resolution. For a photo book PDF with 2400×3000px JPEGs embedded, you get those 2400×3000px files directly — much faster and lossless compared to rasterizing the 8.5"×11" page at 300 DPI.
- **Lossy source warning:** Even though `pdfimages` does not re-encode, the original embedded images may already be JPEG-compressed by the PDF creator. You cannot recover quality that was lost before embedding. Check output sizes and quality to verify.
- **Format preservation:** `-all` keeps each stream in its embedded encoding, so nothing is re-encoded on the way out. `-png` is useful when you want a uniform output format, at the cost of re-encoding and a file-size change.
- **Naming collision:** If multiple images have the same name, `pdfimages` appends sequential suffixes (e.g., `prefix-000.jpg`, `prefix-001.jpg`). No files are overwritten.
- Depends on poppler (`apt install poppler-utils` on Debian/Ubuntu, `brew install poppler` on macOS). Use `install-deps` rather than installing by hand.

---

### Rasterize PDF to Images

**Name.** `pdf-to-images`

**When to use.** Use when the user wants to rasterize PDF pages into numbered image files (JPEG, PNG, or TIFF) at a chosen resolution (DPI) — one image per page, with optional page-range selection. For recovering the photos embedded in a PDF at native resolution instead, use `pdf-extract-embedded-images`.

**Triggers.** turn this PDF into images, export each page as a PNG, give me page 3 of this PDF as a JPEG

Convert PDF pages to raster images (JPEG, PNG, or TIFF) using `pdftoppm`. Each page becomes a numbered image file. Different from `pdf-extract-embedded-images` — this rasterizes the entire page content.

#### When to use

- Converting a scanned PDF or document PDF to standalone images for archival, editing, or distribution.
- Extracting pages as thumbnails or preview images at lower DPI.
- Creating image sequences from a multi-page PDF without needing OCR or text extraction.

#### Inputs to gather

- **Input PDF file** — path to the PDF. Required.
- **DPI (resolution)** — dots per inch. Default: 300 (suitable for archival and print). Ask if the user needs lower DPI for faster processing or smaller file size (e.g., 150 for thumbnails, 600 for high-quality scans).
- **Output format** — `jpeg`, `png`, or `tiff`. Default: `jpeg` (good balance of size and quality). PNG for lossless, TIFF for archival.
- **Page range** (optional) — ask if they want all pages or a subset. If a subset, capture start page and end page (e.g., pages 5–10).
- **Output directory** — optional. Default: current directory.

#### Procedure

##### 1. Check tooling

```bash
command -v pdftoppm >/dev/null || {
  echo "pdftoppm not installed — see the install-deps skill (poppler-utils)" >&2
  exit 1
}
```

##### 2. Validate PDF

```bash
file "$input" 
pdfinfo "$input" || { echo "not a readable PDF: $input" >&2; exit 1; }
```

If invalid, abort. Print the page count for user awareness — it also determines the filename padding width (see step 5).

##### 3. Build command

Base command:

```bash
pdftoppm -r "$dpi" "-$format" "$input" "$output_prefix"
```

**Examples:**

- All pages, JPEG at 300 DPI: `pdftoppm -r 300 -jpeg "input.pdf" "output"`
- Pages 5–10, PNG at 150 DPI: `pdftoppm -r 150 -png -f 5 -l 10 "input.pdf" "output"`
- All pages, TIFF at 600 DPI: `pdftoppm -r 600 -tiff "input.pdf" "output"`

Flags:
- `-r <DPI>` — resolution in DPI.
- `-<format>` — output format: `jpeg`, `png`, `tiff`.
- `-f <N>` — first page (optional).
- `-l <N>` — last page (optional).

##### 4. Execute

```bash
pdftoppm -r "$dpi" "-$format" $page_flags "$input" "$output_prefix" \
  || { echo "pdftoppm failed on $input" >&2; exit 1; }
```

Show progress and warn if the PDF is large (many pages or high DPI — processing may take a minute or more).

##### 5. Report

After conversion:

- Count of images created.
- Output directory and filename pattern. `pdftoppm` pads the page number to the width of the total page count — a 9-page PDF gives `output-1.jpg`, a 40-page PDF gives `output-01.jpg`, a 500-page PDF gives `output-001.jpg`. Read the actual names off disk rather than predicting them.
- File sizes and total space used.
- If a page range was used, note which pages were extracted.

#### Output / side effects

- Numbered image files created. The zero-padding width is derived from the document's total page count (not a fixed width), and the separator is a hyphen by default.
- Original PDF unchanged.

#### Notes

- **Rasterization vs. embedding:** `pdftoppm` rasterizes the entire page at the specified DPI. This is lossy compared to the original PDF vector content, but suitable for archival, sharing, or thumbnail workflows. See `pdf-extract-embedded-images` for extracting embedded photos without rasterization.
- **DPI guidance:** 300 DPI is standard for documents and photos. 150 DPI is adequate for thumbnails or web preview. 600 DPI or higher for fine scanning or print-quality archival.
- **Format choice:** JPEG for smaller files (good for photos within PDFs). PNG for lossless (documents with text). TIFF for professional archival (larger files, lossless, can embed metadata).
- **Large PDFs:** Page rasterization is I/O and CPU intensive. A 100-page PDF at 300 DPI can take 1–2 minutes. Warn the user before starting large jobs.
- Depends on poppler (`apt install poppler-utils` on Debian/Ubuntu, `brew install poppler` on macOS). Use `install-deps` rather than installing by hand.

---

### Read Image Metadata

**Name.** `read-metadata`

**When to use.** Use when the user wants to inspect EXIF, IPTC, XMP, or GPS metadata on images without modifying anything — read out as structured JSON or a human-readable summary. Read-only counterpart to `scrub-metadata` (removes) and `set-metadata` (writes).

**Triggers.** what camera took this photo, does this image have GPS in it, show me the EXIF for this folder

Extract metadata from image files using `exiftool` and output as structured JSON. Supports single files, batch operations, and filtering by metadata group (EXIF, IPTC, XMP, GPS, etc.).

#### When to use

- Inspecting the metadata on a photo before sharing or publishing.
- Auditing a batch of images to verify copyright, GPS, or camera information.
- Programmatically querying metadata for file organization or validation.

#### Inputs to gather

- **Input file or directory** — single image or folder. Default: current directory.
- **Recursive?** If directory, ask whether to descend. Default: **no** (flat).
- **Filter/group** (optional) — ask if they want a specific metadata subset (e.g., EXIF only, GPS only, copyright-related tags). Default: all metadata.
- **Output format** — JSON (default) or a human-readable summary. Recommend JSON for programmatic use, summary for quick inspection.

#### Procedure

##### 1. Check tooling

```bash
command -v exiftool >/dev/null || {
  echo "exiftool not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Determine scope

- **Single file:** direct read.
- **Directory (non-recursive):** read all image files in the folder.
- **Recursive:** use `find` to walk the tree.

##### 3. Read metadata

**Single file, full metadata as JSON:**

```bash
exiftool -j "$file"
```

**Single file, summary (human-readable):**

```bash
exiftool -G1 -a -s "$file" | head -50
```

**Filtered by group (EXIF only):**

```bash
exiftool -j -G1 -EXIF "$file"
```

**Common filters:**

- `-EXIF` — EXIF metadata only.
- `-IPTC` — IPTC tags (description, keywords, copyright).
- `-XMP` — XMP metadata (structured, often used by Adobe).
- `-GPS` — GPS coordinates (latitude, longitude, altitude).

`MakerNote` is a single raw EXIF tag holding an undecoded binary blob, not a group you can filter on like the four above. exiftool decodes maker notes into manufacturer-named groups (`Canon`, `Nikon`, `Sony`, …) — filter on those, or just run unfiltered and read what appears.

**Batch (directory or recursive):**

`exiftool` already walks directories and emits one valid JSON array for the whole set. Use that rather than `find -exec`, which invokes exiftool once per file and concatenates N separate `[...]` arrays into a file that is not valid JSON:

```bash
exiftool -j -r \
  -ext jpg -ext jpeg -ext png -ext heic -ext webp -ext tif -ext tiff \
  "$target" > metadata.json
```

Drop `-r` for the non-recursive case. If a `find`-driven list is genuinely needed (e.g. a filtered subset), pipe it through `jq -s 'add'` to flatten the per-file arrays into one before writing.

##### 4. Summarize or display

**For JSON output:**

If the user wants a summary, parse the JSON:

```bash
exiftool -j "$file" | jq '.[] | {File, Make, Model, DateTime, GPSLatitude, GPSLongitude, Copyright}'
```

**For a batch report:**

```bash
exiftool -j -a -s "$target" | jq '.[] | {FileName, Make, Model, LensModel, FocalLength, ISO, ExposureTime, FNumber}'
```

Pass the directory itself, not a quoted glob. `"$target/*"` is quoted, so the shell never expands it and exiftool receives the literal string `dir/*` as a filename that does not exist.

##### 5. Report

Print the metadata (JSON or summary, per user preference). If batch:

- Count of files read.
- Any files with missing metadata.
- Common metadata patterns (e.g., "15 images from Canon EOS 5D Mark III", "8 images missing GPS").

#### Output / side effects

- Metadata displayed on stdout (or saved to a JSON file if requested).
- No files modified.

#### Notes

- **Metadata standards overlap:** EXIF, IPTC, and XMP sometimes describe the same field (e.g., copyright, description, keywords). `exiftool -j` merges these intelligently; check the JSON keys to see what's present.
- **Camera-specific tags:** Each manufacturer embeds maker-specific metadata. exiftool decodes it into a manufacturer-named group — filter with `-Canon`, `-Nikon`, `-Sony`, or run unfiltered with `-G1` to see which groups a given file actually carries.
- **GPS privacy:** Check for `-GPS` tags before sharing a photo. Many smartphone cameras and some cameras embed GPS by default.
- **Phone metadata:** iPhones embed extensive metadata in EXIF and XMP, including model, iOS version, and processing applied.
- **PNG text chunks:** PNG metadata lives in text chunks (`tEXt`, `iTXt`) rather than EXIF. `exiftool` reads them as XMP or PNG metadata.
- **Batch JSON:** prefer letting exiftool walk the directory (`-j -r <dir>`) — it emits one valid array. Only reach for `jq -s 'add'` when you had to drive it from an external file list and ended up with several concatenated arrays.
- Depends on `exiftool` (`apt install libimage-exiftool-perl` on Debian/Ubuntu, `brew install exiftool` on macOS). Use `install-deps` rather than installing by hand.

---

### Scrub Image Metadata

**Name.** `scrub-metadata`

**When to use.** Strip EXIF / IPTC / XMP metadata from images using exiftool. Use when the user wants to remove identifying metadata (GPS, camera, timestamps, thumbnails) from a single image, a folder, or a recursive tree before sharing or publishing. Supports preview, backup-first, whitelist of fields to keep (e.g. Orientation), and recursive operation. Logs each run to notes/.

Remove EXIF / IPTC / XMP metadata from images in place (or to a copy), with preview and logging. Wraps `exiftool` — do not hand-roll metadata parsing.

#### When to use

- Before publishing photos to a public blog, social media, or client deliverable.
- Bulk-cleaning an archive that may contain GPS or serial-number metadata.
- Preparing reference images for distribution where only orientation should be preserved.

#### Procedure

##### 1. Establish scope

Ask the user (and confirm before touching files):

- **Target path** — single file, folder, or recursive tree. Default: current working directory.
- **Recursive?** If the target is a folder, ask whether to descend into sub-folders. Default **no** (flat, current folder only) unless the user says "recursive" or supplies a root.
- **Backup first?** Default **yes** — `exiftool` keeps `_original` sidecars automatically, but offer an explicit `backup/` copy for the nervous case.
- **Whitelist** — fields to preserve. Common sensible default: keep `Orientation` so the image renders right-way-up. Ask if the user wants to preserve anything else (ColorSpace, ICC profile, copyright).
- **Dry run vs apply** — always preview first.

##### 2. Check tooling

```bash
command -v exiftool >/dev/null || {
  echo "exiftool not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 3. Preview what will be stripped

Set the depth limit once, from the answer to "recursive?" in step 1:

```bash
maxdepth="-maxdepth 1"   # non-recursive
maxdepth=""              # recursive — omit the flag entirely
```

Then run a read-only pass and show the user a summary:

```bash
# Show metadata currently present on a sample file
exiftool -G1 -a -s "$sample"

# Count files that would be touched
find "$TARGET" $maxdepth -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
     -o -iname '*.heic' -o -iname '*.webp' -o -iname '*.tif' \
     -o -iname '*.tiff' \) | wc -l
```

Print:
- File count by extension.
- Which tag groups will be removed (EXIF, GPS, IPTC, XMP, MakerNotes, Thumbnail).
- Which tags will be kept (the whitelist).
- Whether a `backup/` copy will be made.

Wait for user confirmation.

##### 4. Backup (if requested)

The backup must live **outside** the target tree. A `backup/` created inside the target gets copied into itself by `cp`, and — worse — is then walked by the recursive `exiftool -r` pass in step 5, which strips the very copies meant to be pristine.

```bash
STAMP=$(date +%Y-%m-%d-%H%M%S)
BACKUP="$(dirname "$TARGET")/.scrub-backup-$STAMP"
mkdir -p "$BACKUP" || { echo "cannot create backup dir $BACKUP" >&2; exit 1; }

if [ -d "$TARGET" ]; then
  cp -R "$TARGET/." "$BACKUP/" || { echo "backup failed — aborting" >&2; exit 1; }
else
  cp "$TARGET" "$BACKUP/" || { echo "backup failed — aborting" >&2; exit 1; }
fi
echo "Backup: $BACKUP"
```

The `-d` branch matters: the scope in step 1 allows a single file, and `cp -R "$TARGET/."` is invalid against a regular file.

If `$(dirname "$TARGET")` is not writable, fall back to `BACKUP="$(mktemp -d)/scrub-backup"` and tell the user the path — never silently place the backup inside the target.

Report the backup path to the user before step 5 runs, and never proceed to step 5 if the backup command failed.

Note that `exiftool` also keeps its own `<file>_original` sidecars in-place unless `-overwrite_original` is passed — decide with the user whether to keep those or clean them up at the end.

##### 5. Strip metadata

Two patterns — pick based on scope:

**Folder (non-recursive):**

```bash
exiftool -all= -tagsFromFile @ -Orientation \
  -ext jpg -ext jpeg -ext png -ext heic -ext webp -ext tif -ext tiff \
  "$TARGET"
```

**Recursive tree:**

```bash
exiftool -r -all= -tagsFromFile @ -Orientation \
  -ext jpg -ext jpeg -ext png -ext heic -ext webp -ext tif -ext tiff \
  "$TARGET"
```

The recursive form is why the step 4 backup has to sit outside `$TARGET`: `-r` descends into every subdirectory, including one named `backup/`.

If the user asked to keep additional fields, extend the `-tagsFromFile @ -Field1 -Field2 ...` list. If the user asked to preserve **nothing** (full nuke), drop the `-tagsFromFile` clause — just `-all=`.

To discard the `_original` sidecars in the same run, append `-overwrite_original`. Only do this if a backup was made in step 4, or if the user explicitly waived backup.

##### 6. Verify

Sample a few output files and show their remaining metadata:

```bash
exiftool -G1 -a -s "$sample_output"
```

Confirm only whitelisted tags remain. If unexpected metadata survived (common with PNG text chunks or XMP sidecars), flag it and offer a second pass with `-xmp:all=` or a manual `exiftool -ext xmp -overwrite_original -all= "$TARGET"`.

##### 7. Log

Write `notes/scrub-metadata-$STAMP.md` in the target folder (or the cwd if the target was a single file), reusing the `$STAMP` computed in step 4 — or, if no backup was taken, `STAMP=$(date +%Y-%m-%d-%H%M%S)`. Include:

- Target path and whether recursive.
- Backup taken? Where?
- Whitelist used.
- File count processed, count skipped, count failed.
- Sample before/after metadata dump for one file.
- Any warnings (XMP sidecars found, MakerNotes that resisted strip, etc.).

If `notes/` doesn't exist, create it.

#### Notes

- `exiftool` is the only sane tool for this — don't use `convert -strip` (ImageMagick) as the primary path; it silently drops colour profiles and doesn't touch XMP sidecars reliably.
- **GPS is the most common sensitive leak** — always explicitly confirm it's gone in step 6 (`exiftool -GPS:all "<file>"` should return nothing).
- For HEIC from iPhones, there are often **two** copies of EXIF (container + embedded). `exiftool -all=` handles both, but verify.
- For PNGs, metadata lives in `tEXt` / `iTXt` / `eXIf` chunks — `exiftool -all=` covers them. Do not rely on `optipng -strip all` as a primary scrubber.
- Never operate on the only copy of irreplaceable originals without a backup. If the user is working on an archive, insist on step 4.
- Do not push scrubbed files anywhere automatically — that's a human decision.

---

### Write Metadata to Images

**Name.** `set-metadata`

**When to use.** Use when the user wants to write arbitrary EXIF, IPTC, or XMP tags to images — artist, copyright, description, keywords, GPS coordinates, capture date, lens or camera model. For stamping only copyright/artist/rights uniformly across a whole directory, `batch-set-copyright` is the narrower wrapper.

**Triggers.** set the description on this photo, add GPS coordinates to these images, fix the lens metadata

Set metadata tags on image files using `exiftool`. Supports EXIF, IPTC, and XMP metadata, with automatic backup of original files.

#### When to use

- Adding copyright and artist information to a photo before distribution.
- Manually setting GPS coordinates if they were not captured.
- Batch-updating descriptions or keywords across multiple images.
- Fixing incorrect camera model or lens metadata.

For the narrow case of stamping the *same* copyright, artist, and rights across an entire folder, `batch-set-copyright` wraps that workflow with a preview and a per-file failure tally. Use this skill for arbitrary tags, per-file values, or anything outside those three fields.

#### Inputs to gather

- **Input file or directory** — single image or folder.
- **Metadata key-value pairs** — ask the user for the tags and values they want to set. Common fields:
  - `Artist` — photographer or creator name.
  - `Copyright` — copyright statement (e.g. `© 2026 <Artist>`).
  - `Description` / `ImageDescription` — image description text.
  - `Keywords` — comma-separated keywords.
  - `LensModel` — lens description (if not auto-detected).
  - `GPSLatitude` / `GPSLongitude` / `GPSAltitude` — GPS coordinates.
  - `DateTimeOriginal` — capture date/time (format: `YYYY:MM:DD HH:MM:SS`).
- **Backup before write?** Default: **yes**. exiftool creates `_original` sidecars; offer an explicit backup copy for safety.

#### Procedure

##### 1. Check tooling

```bash
command -v exiftool >/dev/null || {
  echo "exiftool not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Validate tag names

Ask the user to confirm the exiftool tag names. Common mappings:

| User-facing | exiftool tag |
|---|---|
| Artist | Artist |
| Creator | Creator |
| Copyright | Copyright |
| Description | ImageDescription |
| Keywords | Keywords |
| Lens | LensModel |
| Camera model | Model |

**Gotcha:** EXIF, IPTC, and XMP may use different tag names for the same logical field. exiftool auto-detects the appropriate target; document which format will be used:

```bash
exiftool -a -G1 "$sample" | grep -i copyright
```

This shows which groups (EXIF, IPTC, XMP) currently carry copyright info on the sample file.

##### 3. Confirm metadata and scope

Print a summary:

- Tags to be set: list all key-value pairs.
- Target files: count and confirm.
- Backup location: where `_original` sidecars will be stored.
- Confirm before proceeding.

##### 4. Backup (if requested)

exiftool creates `_original` sidecars by default; offer an explicit backup on top of that. Put it **outside** the target tree, or a later recursive pass walks into the backup and rewrites the copies too:

```bash
BACKUP="$(dirname "$TARGET")/.setmeta-backup-$$"
mkdir -p "$BACKUP" || { echo "cannot create backup dir $BACKUP" >&2; exit 1; }

if [ -d "$TARGET" ]; then
  cp -R "$TARGET/." "$BACKUP/" || { echo "backup failed — aborting" >&2; exit 1; }
else
  cp "$TARGET" "$BACKUP/"      || { echo "backup failed — aborting" >&2; exit 1; }
fi
echo "Backup: $BACKUP"
```

The `-d` branch matters — the scope allows a single file, and `cp -R "$TARGET/."` is invalid against one. Never proceed to step 5 if the backup command failed.

##### 5. Write metadata

**Single file:**

Build the tag list once as an array, so the same set can be reused for the single-file and batch paths and optional tags can be appended conditionally:

```bash
ARGS=( -Artist="$ARTIST" -Copyright="$COPYRIGHT" )
[ -n "$DESC" ]     && ARGS+=( -ImageDescription="$DESC" )
[ -n "$KEYWORDS" ] && ARGS+=( -Keywords="$KEYWORDS" )
```

**Single file:**

```bash
exiftool "${ARGS[@]}" "$file"
```

**Batch (directory or recursive):**

```bash
: > "$failed_log"

# Non-recursive: -maxdepth 1. Recursive: omit -maxdepth entirely.
find "$TARGET" -maxdepth 1 -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
     -o -iname '*.heic' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \) \
  -print0 |
while IFS= read -r -d '' f; do
  exiftool "${ARGS[@]}" "$f" >/dev/null || echo "$f" >> "$failed_log"
done
```

`find -exec` discards each exit code, so the loop is what makes a failure count possible. `-print0` with `read -d ''` keeps filenames with spaces intact.

Append `-overwrite_original` to `ARGS` to discard `_original` sidecars, but only if a backup was made in step 4.

##### 6. Verify

Sample a few output files and confirm the metadata was written:

```bash
exiftool -Artist -Copyright -ImageDescription "$sample"
```

Also report the contents of `$failed_log` — say "none" only when it is empty.

If metadata did not stick (e.g. PNG text chunks), try the XMP-specific path:

```bash
exiftool -XMP:Artist="$ARTIST" -XMP:Copyright="$COPYRIGHT" "$file"
```

##### 7. Cleanup (optional)

If the user accepted `-overwrite_original`, remove `_original` sidecars. Confirm first — this discards exiftool's own safety net:

```bash
find "$TARGET" -maxdepth 1 -type f -iname '*_original' -delete
```

Drop `-maxdepth` for the recursive case.

#### Output / side effects

- Metadata tags written to original files (or to a copy if the user requested a separate output directory).
- `_original` sidecars created in the same directory as each file (unless `-overwrite_original` was used).
- Original files are modified (unless a backup was made in step 4).

#### Notes

- **EXIF vs. IPTC vs. XMP:** The same field (e.g., copyright) can live in EXIF, IPTC, and/or XMP. Some readers check only one format. `exiftool` intelligently maps to the appropriate group, but document which format was used:
  - EXIF: structured, camera/lens/exposure info. Limited size.
  - IPTC: editorial metadata (keywords, description, copyright). Limited size.
  - XMP: extensible, can hold arbitrary key-value pairs.
- **PNG and HEIC:** exiftool writes metadata to PNG as XMP in iTXt chunks. HEIC is complex; check the `_original` sidecar to ensure metadata persisted.
- **Tag size limits:** EXIF and IPTC have field-length limits. Very long descriptions (>500 chars) should go in XMP. exiftool warns if a value is too large.
- **Permanent writes:** Always create a backup before bulk metadata writes. Metadata corruption is rare but possible.
- **Preserve other metadata:** By default, `exiftool -Tag=value file` preserves all other metadata. Use `-all=` if you want to nuke everything before writing (not recommended).
- Depends on `exiftool` (`apt install libimage-exiftool-perl` on Debian/Ubuntu, `brew install exiftool` on macOS). Use `install-deps` rather than installing by hand.

---

### SVG to Raster

**Name.** `svg-to-raster`

**When to use.** Use when the user wants to rasterize SVG files — convert SVG to PNG, PDF, or PostScript at a chosen resolution. Wraps CairoSVG (Python, in the plugin venv). Single file or batch. Companion to `vectorize` (other direction).

**Triggers.** convert this SVG to PNG, render my icons at 2x, I need a raster version of this logo

Rasterize SVG files to PNG / PDF / PS via [CairoSVG](https://github.com/Kozea/CairoSVG). Runs from the plugin's uv venv — no system Python pollution.

#### When to use

- Convert logo / icon / diagram SVGs to PNG for use in slides, social, or pipelines that don't accept SVG.
- Render an SVG at multiple resolutions (e.g. 1×, 2×, 3× for app assets).
- Bake an SVG into a PDF for print or archival.

Do **not** use this skill when:
- Source is already raster — wrong direction; use `vectorize` instead.
- You need to *edit* the SVG — CairoSVG is render-only.
- The SVG uses advanced filters / unsupported CSS — CairoSVG covers SVG 1.1 well but newer features may not render. Inspect output and warn the user.

#### Inputs

1. **Input** — SVG file or directory. Required.
2. **Format** — `png` (default), `pdf`, `ps`.
3. **Output dir** — default: `<input-dir>/<format>/`. Never overwrites originals.
4. **Scale** — multiplier on the SVG's intrinsic size. Default `1.0`. Use `2.0`, `3.0` for hi-DPI.
5. **Width / Height** — explicit pixel dimensions (overrides scale). Pass one to preserve aspect; both to force.
6. **DPI** — for PDF/PS output. Default `96`.
7. **Background** — default transparent. Pass a CSS colour (`#ffffff`, `white`) for solid fill.
8. **Recursive** — `--recursive` for directory descent.

#### Procedure

1. Resolve venv: `VENV_DIR="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/venv"`.

2. Verify `cairosvg` is importable in the venv:

   ```bash
   "$VENV_DIR/bin/python" -c "import cairosvg" 2>&1
   ```

   If missing → point at `install-deps`. If it imports but raises a libcairo error, surface the system-lib install command (`sudo apt install libcairo2` / `brew install cairo`).

3. Enumerate `*.svg` inputs (case-insensitive). Skip non-SVG with note.

4. Call CairoSVG via the venv Python (keeps the skill self-contained — no helper script needed). Pass the gathered options as arguments rather than string-substituting them into the source; the script below dispatches on format and builds the kwargs itself:

   ```bash
   "$VENV_DIR/bin/python" - "$input" "$output" "$fmt" \
       "$scale" "$width" "$height" "$dpi" "$background" <<'PYEOF'
   import sys, cairosvg

   src, dst, fmt, scale, width, height, dpi, bg = sys.argv[1:9]

   fn = {'png': cairosvg.svg2png,
         'pdf': cairosvg.svg2pdf,
         'ps':  cairosvg.svg2ps}[fmt]

   kwargs = {'url': src, 'write_to': dst}
   # Empty string means "not supplied" — omit rather than passing a default
   # that would override CairoSVG's own.
   if scale:  kwargs['scale'] = float(scale)
   if width:  kwargs['output_width'] = int(width)
   if height: kwargs['output_height'] = int(height)
   if dpi:    kwargs['dpi'] = int(dpi)
   if bg:     kwargs['background_color'] = bg

   fn(**kwargs)
   PYEOF
   ```

   Function map: `png → svg2png`, `pdf → svg2pdf`, `ps → svg2ps`.

   Note that `output_width` / `output_height` override `scale` in CairoSVG — do not pass both unless that is what the user asked for.

5. Track file sizes and any render warnings (CairoSVG prints to stderr for unsupported features). Wrap each conversion so one bad file does not kill the batch:

   ```bash
   if ! "$VENV_DIR/bin/python" - ... <<'PYEOF'
   ...
   PYEOF
   then
     echo "FAILED: $input" >> "$failed_log"
     rm -f "$output"
     continue
   fi
   ```

   Removing the partial `$output` matters — a truncated PNG left on disk reads as a successful conversion to the summary.

#### Output

- Rasterized files at `<output-dir>/`.
- Summary:
  - Files processed / failed, with the failed paths from `$failed_log`.
  - Per-file: source dimensions → output dimensions, output size.
  - Any render warnings (unsupported SVG features).

#### Notes

- CairoSVG is LGPL-3.0; using it as a CLI dependency is fine, no licence contagion.
- For multi-resolution batch (e.g. app icon set), call this skill multiple times with different `--scale` values, or wrap in a small loop.
- If you need true SVG editing or advanced filter support, look at Inkscape CLI (`inkscape --export-type=png`). CairoSVG is the lighter-weight pure-Python option.
- Animated SVG (SMIL) is not supported — CairoSVG renders the initial frame only.

---

### Convert Images to JPEG XL

**Name.** `to-jxl`

**When to use.** Use when the user wants to encode images of any raster format (PNG, GIF, WebP, TIFF, JPEG) to JPEG XL (.jxl) with a chosen quality preset — lossless, visually lossless, or web. General-purpose JXL encoder. For a JPEG-only archive where the goal is a byte-exact-recoverable lossless transcode with a savings report, use `transcode-jpeg-to-jxl-lossless` instead.

**Triggers.** convert these PNGs to JXL, encode this folder as JPEG XL, make JXL versions at web quality

Encode images to JPEG XL (.jxl) format using `cjxl`. Supports lossless, visually lossless, and web quality presets, with optional effort (compression) tuning.

#### When to use

- Converting photos to JXL for archival, where file size matters and quality must be preserved.
- Encoding non-JPEG sources (PNG, TIFF, WebP, GIF) to JXL at a chosen distance.
- Creating web-optimized JXL variants with controlled visual loss.

Do **not** use this skill when the source set is exclusively JPEG and the goal is archival: `transcode-jpeg-to-jxl-lossless` covers that case with a dry-run preview, a byte-savings report, and the recovery instructions. This skill is the general encoder; that one is the JPEG-archive workflow.

#### Inputs to gather

- **Input file or directory** — single image, folder, or recursive tree. If omitted, ask for the path.
- **Quality preset** — ask which tier: `lossless` (full fidelity, `-d 0`), `visually-lossless` (imperceptible loss, `-d 1.0`, default), or `web` (visible compression acceptable, `-d 3.0`). Default: visually-lossless.
- **Effort level** — optional, range 1–9 (1 = fastest, 9 = slowest/best compression). Default: 7. Only ask if the user is concerned about speed vs file size.

#### Procedure

##### 1. Check tooling

```bash
command -v cjxl >/dev/null || {
  echo "cjxl not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Map quality presets to distance

- `lossless` → `-d 0`
- `visually-lossless` → `-d 1.0`
- `web` → `-d 3.0`

Set `effort=7` unless the user overrides.

##### 3. Determine scope

- **Single file:** run one conversion.
- **Directory (non-recursive):** ask before processing, then loop over image files in the folder.
- **Recursive:** use `find` to locate all images in the tree.

Ask for confirmation before batch operations. Set the depth limit once, and reuse it:

```bash
maxdepth="-maxdepth 1"   # non-recursive
maxdepth=""              # recursive — omit the flag entirely
```

##### 4. Convert

**Single file:**

```bash
cjxl -d "$distance" -e "$effort" "$input" "${input%.*}.jxl"
```

**Batch (folder or recursive):**

`find` substitutes only the literal token `{}`. It has **no** `{.}` "strip the extension" placeholder — that is GNU parallel syntax. Passing `{.}.jxl` writes every single file to one literal output named `{.}.jxl`, so each conversion overwrites the last. Derive the output name inside a shell instead:

```bash
find "$target" $maxdepth -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
     -o -iname '*.gif' -o -iname '*.webp' -o -iname '*.tif' \) \
  -exec sh -c '
    for f do
      cjxl -d "$0" -e "$1" "$f" "${f%.*}.jxl" \
        || echo "FAILED: $f" >> "$2"
    done
  ' "$distance" "$effort" "$failed_log" {} +
```

Show progress (file count, time remaining estimate if batch is large).

##### 5. Report

After conversion:

- Count of files converted, skipped, failed.
- Original vs. converted file sizes; report total bytes saved.
- Read the failure list from `$failed_log` written by step 4 and print it. Never report a converted count without also reporting failures — `find -exec` does not propagate per-file exit status, so an uncaptured failure is invisible.

#### Output / side effects

- New `.jxl` files created in the same directory as originals (or in a user-specified output folder).
- Original files remain unchanged.

#### Notes

- **Lossless JPEG→JXL transcoding:** at `-d 0` from a JPEG source, `cjxl` stores JPEG reconstruction data (JBRD) alongside the pixels. To recover the original JPEG bit-exact later, run `djxl input.jxl recovered.jpg` — reconstruction is driven by the `.jpg` output extension, not by a flag. If the `.jxl` carries no JBRD (it was encoded from PNG, or lossily), `djxl` fails rather than silently emitting a re-encode. This is the killer feature for photo archives; the `transcode-jpeg-to-jxl-lossless` skill wraps it with a savings report.
- **Effort vs. speed:** Effort 7 is a good default (reasonable compression in 1–2 seconds per MP). Effort 9 can take minutes on large files. Only use 9 for final archival encodes, not batch preview work.
- **Alpha channels:** JXL supports them natively. PNGs with transparency will retain it.
- Depends on `libjxl-tools` (`apt install libjxl-tools` on Debian/Ubuntu, `brew install jpeg-xl` on macOS). Use `install-deps` rather than installing by hand.

---

### Losslessly Transcode JPEG to JPEG XL

**Name.** `transcode-jpeg-to-jxl-lossless`

**When to use.** Use when the user wants to archive a JPEG-only library as JPEG XL — losslessly transcodes JPEG to .jxl, preserving the original bitstream for byte-exact recovery, with a dry-run preview and a byte-savings report (~15–25% reduction). Prefer this over the general-purpose `to-jxl` skill whenever the sources are exclusively JPEG and archival is the goal.

**Triggers.** archive my JPEGs as JXL, shrink this photo library losslessly, JPEG to JXL without quality loss

Walk a directory of JPEG files and convert them to JPEG XL (.jxl) format using lossless encoding. `cjxl` automatically detects JPEG bitstream and preserves it without re-compression. Reports byte savings; explains how to recover the original JPEG if needed.

#### When to use

- Archiving JPEG photo libraries to save space (typically 15–25% reduction) without image degradation.
- Preparing a photo collection for long-term storage where compatibility with JPEG is not required.
- Building a smaller-footprint JXL archive that can still yield the original JPEG byte-exact via `djxl`.

For non-JPEG sources, or for lossy/web-quality JXL encodes, use `to-jxl` — this skill deliberately handles only the JPEG-archival case.

#### Inputs to gather

- **Source directory** — folder containing JPEG files (`.jpg` or `.jpeg`). Default: current directory.
- **Recursive?** Ask whether to process subdirectories. Default: **no** (flat, current folder only).
- **Output location** — optional. Default: same directory as originals (`.jxl` files sit alongside `.jpg`).
- **Dry run first?** Recommend a preview pass showing the count and byte savings estimate, before committing to the conversion.

#### Procedure

##### 1. Check tooling

```bash
command -v cjxl >/dev/null || {
  echo "cjxl not installed — see the install-deps skill" >&2
  exit 1
}
```

##### 2. Preview

Show the user what will happen. Capture the original total into a variable — step 4 needs it to compute savings, and re-measuring the directory afterwards would count the new `.jxl` files too.

Set the depth limit once, from the answer to "recursive?" in the inputs:

```bash
maxdepth="-maxdepth 1"   # non-recursive
maxdepth=""              # recursive — omit the flag entirely
```

```bash
# Count JPEGs in scope
find "$target" $maxdepth -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' \) | tee /tmp/jpegs.txt | wc -l

# Original total, in bytes (not human-readable — it has to be arithmetic later)
ORIG_BYTES=$(find "$target" $maxdepth -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' \) -exec wc -c {} + \
  | awk '$NF == "total" { next } { s += $1 } END { print s+0 }')
```

Skipping the `total` lines matters: `-exec ... +` batches its arguments, so a large tree produces one `total` line per batch and naively summing every line would double-count.

`wc -c` totals exact bytes; `du` rounds to block size and would skew the savings figure on a library of small files.

Print:
- Number of JPEG files found.
- Total original size.
- Estimated output size (advise 20% reduction as a rough baseline).
- Confirm before proceeding.

##### 3. Transcode

Use `-d 0` (lossless) and a reasonable effort (suggest 6–7 for balance):

`find` substitutes only the literal token `{}`. There is no `{.}` extension-stripping placeholder — that is GNU parallel syntax, and `find` would pass the literal string `{.}.jxl`, funnelling every file in the tree into one output that each conversion overwrites. Build the output name inside a shell instead, reusing the `$maxdepth` set in step 2:

```bash
: > "$failed_log"

find "$target" $maxdepth -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' \) \
  -exec sh -c '
    for f do
      cjxl -d 0 -e 7 "$f" "${f%.*}.jxl" || echo "$f" >> "$0"
    done
  ' "$failed_log" {} +
```

(The `-d 0` flag ensures lossless encoding. Effort 7 balances speed and compression. Effort 9 is slower but slightly smaller; only recommend if the user has time.)

`$failed_log` collects every non-zero `cjxl` exit. `find -exec` does not propagate per-file status, so without this file a failed transcode is silently invisible in the step 4 report.

##### 4. Verify and report

After transcoding:

```bash
# Count JXL files created
find "$target" $maxdepth -type f -iname '*.jxl' | wc -l

# Total size of the new JXL files, in bytes
JXL_BYTES=$(find "$target" $maxdepth -type f -iname '*.jxl' -exec wc -c {} + \
  | awk '$NF == "total" { next } { s += $1 } END { print s+0 }')

# Bytes saved — an explicit subtraction against the step 2 figure
awk -v o="$ORIG_BYTES" -v n="$JXL_BYTES" 'BEGIN {
  printf "original: %.1f MB\njxl:      %.1f MB\nsaved:    %.1f MB (%.1f%%)\n",
         o/1048576, n/1048576, (o-n)/1048576, (o ? (o-n)*100/o : 0)
}'
```

Do **not** substitute `du -ch "$target"` for this. At this point the directory holds both the originals and the new `.jxl` files, so it measures the sum of the two, not the saving. The saving only exists as the difference between the step 2 figure and the step 4 figure.

Print:
- Files successfully transcoded.
- Original total size vs. new total size.
- Bytes saved and percentage reduction (from the `awk` above).
- Any failures — print the contents of `$failed_log`, and say "none" only when that file is empty.

##### 5. Explain recovery path

Inform the user:

> If you ever need to recover the original JPEG bitstream byte-exact (for legal/archival purposes), run:
> ```bash
> djxl archive.jxl recovered.jpg
> ```
> This works because `cjxl` detected and preserved the original JPEG structure. Reconstruction is triggered by the `.jpg` output extension — there is no `--jpeg` flag in current libjxl. If the `.jxl` carries no reconstruction data, `djxl` reports an error rather than quietly writing a re-encoded approximation, so a successful run is itself the proof of byte-exactness.

#### Output / side effects

- `.jxl` files created in the source directory (or user-specified output folder).
- Original `.jpg` files remain untouched.
- No backup is created; if the originals must be preserved, the user should copy them first.

#### Notes

- **Lossless JPEG preservation:** `cjxl` auto-detects JPEG bitstreams and preserves them exactly. This is why `djxl` can recover the original — it's not a re-encoded approximation.
- **Effort 7 vs. 9:** Effort 7 compresses in seconds per image; effort 9 can take minutes. For batch workflows, 7 is recommended. Use 9 only if compression size is the overriding concern.
- **Size savings:** Typical JPEG → JXL lossless reduction is 15–25%, depending on the original JPEG quality. Do not oversell — some JPEGs may compress only 5–10%.
- **Selective transcoding:** If you want to skip already-small files or transcode only above a size threshold, filter the find output (e.g., `-size +100k` for files larger than 100 KB).
- Do not delete the original JPEG files automatically. Let the user confirm removal after verifying the JXL output.
- Depends on `libjxl-tools` (`apt install libjxl-tools` on Debian/Ubuntu, `brew install jpeg-xl` on macOS). Use `install-deps` rather than installing by hand.

---

### Upscale Image (Upscayl)

**Name.** `upscale-image`

**When to use.** Use when the user wants to AI-upscale images 2× / 3× / 4× — recovering detail in low-res sources, prepping small photos for print, enlarging AI-generated images. Wraps `upscayl-bin` (the CLI bundled with Upscayl) with its model library; falls back to standalone `realesrgan-ncnn-vulkan` if Upscayl isn't installed. GPU-accelerated via Vulkan.

**Triggers.** upscale this image 4x, enlarge these photos for print, this image is too low-res, can you fix it

AI upscaling via `upscayl-bin` — the CLI shipped with the Upscayl GUI. Same Vulkan-accelerated `realesrgan-ncnn-vulkan` engine as standalone, but with Upscayl's curated model selection bundled.

#### When to use

- Low-res source needs to be enlarged for print or display.
- AI-generated image at 1024px wants 4096px output without re-prompting.
- Old photos / screenshots need detail recovery.

Do **not** use this skill when:
- The source is already large enough — upscaling rarely improves a 4K-native image.
- The user wants traditional bicubic / lanczos upscaling — `fast-resize` is the right tool (much faster, no AI).
- The image is text/document-heavy — upscalers can hallucinate glyph detail; consider `tesseract` re-OCR + re-typeset instead.

#### Inputs

1. **Input** — file or directory. Required.
2. **Scale** — `2`, `3`, or `4` (Upscayl's bundled models are 4× natively; 2× and 3× are produced by post-resize). Default `4`.
3. **Model** — one of:
   - `upscayl-standard-4x` (default — best general-purpose photo upscaler).
   - `upscayl-lite-4x` (faster, lower quality, good for batches).
   - `realesrgan-x4plus` (classic, slightly different texture handling).
   - `realesrgan-x4plus-anime` (illustrations, line art, anime).
   - `remacri-4x` / `ultramix-balanced-4x` (alternative photo models if installed).
   - Or `--model-path <dir> --model-name <name>` to point at a custom model.
4. **Output dir** — default: `<input-dir>/upscaled/`. Skill never overwrites originals.
5. **Output format** — default `png` (lossless preserves the upscale fidelity). `jpg` option for size-sensitive batches (uses quality 92).
6. **Recursive** — `--recursive` for directory descent.
7. **GPU** — default auto-detect. `-g <n>` to pick a specific GPU device id. `-g -1` forces CPU (slow — only for headless boxes). The binary takes single-dash short flags throughout; there are no `--gpu` / `--cpu` long forms.

#### Procedure

1. Locate the binary. Check in order:
   - `which upscayl-bin`
   - `/opt/Upscayl/resources/bin/upscayl-bin`
   - `~/.var/app/org.upscayl.Upscayl/data/bin/upscayl-bin` (Flatpak)
   - `which realesrgan-ncnn-vulkan` (fallback — same syntax, smaller model selection)

   If none found, point the user at `install-deps` (Upscayl install instructions: <https://upscayl.org>).

2. Locate the models directory. For upscayl-bin, typically:
   - `/opt/Upscayl/resources/models/`
   - `~/.var/app/org.upscayl.Upscayl/data/models/`
   - User-custom dir at `~/.config/Upscayl/models/`

   For standalone realesrgan-ncnn-vulkan, models are alongside the binary or in `./models/`.

   Verify the requested model exists in the resolved dir (each model is a `.param` + `.bin` pair).

3. Enumerate inputs (image extensions only).

4. For each file:

   ```bash
   "$binary" \
     -i "$input" \
     -o "$output.png" \
     -s 4 \
     -m "$models_dir" \
     -n "$model" \
     ${gpu:+-g "$gpu"} \
     || { echo "FAILED: $input" >> "$failed_log"; continue; }
   ```

   `$gpu` is the device id when the user picked one, or `-1` for forced CPU; leave it unset for auto-detect.

   The `-s` flag is fixed at the model's native scale (almost always 4). For non-4× output:

   - **Scale 2 or 3:** run 4× upscale, then post-resize down via `vipsthumbnail` to `(orig × scale)` dimensions:
     ```bash
     vipsthumbnail "$intermediate_4x" --size "${target_w}x${target_h}" \
       --output "$final.$ext[Q=92]"
     ```
   - **Scale 4 native:** the upscaler output is final.

5. **Output format conversion** if `--output-format jpg`:

   `cjpeg` decodes PPM/PGM/BMP/Targa only — it cannot read PNG, so piping the upscaler's PNG into it fails. Either convert with ImageMagick directly:

   ```bash
   magick "$output.png" -quality 92 -interlace Plane "$output.jpg" \
     && rm "$output.png"
   ```

   Or, to get mozjpeg's better quantisation, decode to PPM first and pipe that in (`$MOZ_BIN` resolved as in `optimize-jpeg` step 1):

   ```bash
   magick "$output.png" ppm:- \
     | "$MOZ_BIN/cjpeg" -quality 92 -progressive -optimize > "$output.jpg" \
     && rm "$output.png"
   ```

   Keep the `&&` — deleting the PNG after a failed encode loses the upscale entirely.

6. **Sequential, not parallel.** Vulkan GPU is single-resource — running multiple upscales concurrently doesn't help and may OOM the GPU on large images. Run one at a time.

7. **Memory awareness.** For very large inputs (>4000px on the long side), the Vulkan tile size matters. Default is fine; if the binary reports OOM, retry with `-t 100` (smaller tile = less VRAM, slightly slower). Surface this to the user rather than silently failing.

8. **Per-file failures do not abort the batch.** Any file that fails — corrupt input, model/scale mismatch, OOM that survives the `-t 100` retry — is appended to `$failed_log` and the run continues to the next file. Report that list alongside the success count; never print a processed total on its own.

#### Output

- Upscaled images at `<output-dir>/`.
- Summary:
  - Files processed / failed, the failure list read from `$failed_log`, and the reason per entry where the binary gave one.
  - Per-file: input dimensions → output dimensions, model used, elapsed seconds.
  - Total elapsed.
  - GPU device that was used (from upscayl-bin's stderr).

#### Notes

- Upscayl's `upscayl-standard-4x` produces visibly better results than vanilla `realesrgan-x4plus` on most photos — keep the default unless the user has a reason.
- Anime/illustration content: switch to `realesrgan-x4plus-anime` or one of the anime-specific Upscayl variants. Photo models smear line art.
- Compute time: ~5–20s per 1080p input on a mid-range GPU; 1–3 minutes per image on CPU. Batch a folder overnight for CPU runs.
- Output format default is PNG because JPEG re-encoding immediately after upscale undoes some of the perceptual gain. JPEG only when the user explicitly wants smaller files.
- Combining with other skills:
  - `web-ready` after upscale → use the `gallery` profile to ship the upscaled output to the web at sensible quality.
  - `images-to-pdf` after upscale → enlarge then print at higher DPI.
- This skill does not auto-install Upscayl or download models. The user owns that step. Models are typically several hundred MB total.

---

### Vectorize

**Name.** `vectorize`

**When to use.** Use when the user wants to trace a raster image (PNG/JPEG) into an SVG vector — useful for logos, line art, diagrams, and stylized illustrations. Wraps `vtracer` (Rust-backed, via Python wheel in the plugin venv). Companion to `svg-to-raster` (other direction).

**Triggers.** vectorize this logo, convert this PNG to SVG, trace this line art

Convert raster images to SVG via [vtracer](https://github.com/visioncortex/vtracer). vtracer is a color-clustering tracer — much better than `potrace` for full-color images, comparable for B/W line art. Installed as a Python wheel in the plugin venv (bundled Rust binary, no `cargo` needed at install time).

#### When to use

- Recover an editable vector logo from a raster (PNG/JPEG).
- Convert a flat illustration / icon / diagram into SVG for crisp scaling.
- Stylize a photo into a flat-color vector (large `--filter-speckle` + low `--color-precision`).
- Pre-step before `svg-to-raster` if you want to upscale a small raster losslessly.

Do **not** use this skill when:
- Source is a complex photograph and you want photo-realism — vector tracing always loses gradients/texture; use `upscale-image` for raster upscaling instead.
- You need OCR'd text inside the SVG — vtracer traces strokes, not text. Use a separate OCR step.
- Input is already SVG — no-op.

#### Inputs

1. **Input** — image file or directory. Required.
2. **Output dir** — default: `<input-dir>/svg/`. Never overwrites originals.
3. **Mode** — `color` (default, multi-color with clustering) or `binary` (B/W line art, faster, smaller output).
4. **Color precision** — `1..8`, default `6`. Lower = fewer colors = smaller / more abstract SVG.
5. **Layer difference** — `0..255`, default `16`. Larger = fewer layers, simpler output.
6. **Filter speckle** — pixels, default `4`. Discards regions smaller than N pixels — raise to de-noise.
7. **Path simplification** — `corner threshold` (default `60` deg), `length threshold` (default `4.0`), `splice threshold` (default `45` deg). Most users won't tune these; expose only if asked.
8. **Recursive** — `--recursive` for directory descent.

#### Procedure

1. Resolve venv: `VENV_DIR="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/venv"`.

2. Verify `vtracer` is importable:

   ```bash
   "$VENV_DIR/bin/python" -c "import vtracer" 2>&1
   ```

   If missing → point at `install-deps`.

3. Enumerate inputs (`*.png`, `*.jpg`, `*.jpeg`, `*.bmp`, `*.tiff`). Skip already-SVG with note.

4. For each file, call vtracer via the venv Python. Pass the tuning values as arguments — the placeholders below are *shell* variables, and substituting `<int>`-style placeholders into the Python source literally would be a `SyntaxError`:

   ```bash
   "$VENV_DIR/bin/python" - "$input" "$output" "$colormode" \
       "$color_precision" "$layer_difference" "$filter_speckle" \
       "$corner_threshold" "$length_threshold" "$splice_threshold" <<'PYEOF'
   import sys, vtracer

   (src, dst, colormode, color_precision, layer_difference,
    filter_speckle, corner_threshold, length_threshold,
    splice_threshold) = sys.argv[1:10]

   vtracer.convert_image_to_svg_py(
       src,
       dst,
       colormode=colormode,                        # 'color' or 'binary'
       color_precision=int(color_precision),
       layer_difference=int(layer_difference),
       filter_speckle=int(filter_speckle),
       corner_threshold=int(corner_threshold),
       length_threshold=float(length_threshold),
       splice_threshold=int(splice_threshold),
       path_precision=8,
   )
   PYEOF
   ```

   A fully-resolved invocation for the default logo/icon preset:
   `colormode=color`, `color_precision=6`, `layer_difference=16`, `filter_speckle=4`, `corner_threshold=60`, `length_threshold=4.0`, `splice_threshold=45`.

5. Track size deltas and a quick "vector quality" sniff: file size ratio (SVG / PNG), and visually-noticeable degradation flags (very large filter_speckle on a detailed source = likely loss).

6. Handle per-file failure. vtracer raises on corrupt or unsupported inputs; catch it at the shell level so one bad file does not end the batch:

   ```bash
   if ! "$VENV_DIR/bin/python" - ... <<'PYEOF'
   ...
   PYEOF
   then
     echo "FAILED: $input" >> "$failed_log"
     rm -f "$output"
     continue
   fi
   ```

#### Output

- SVG files at `<output-dir>/`.
- Summary:
  - Files processed / failed, with the failed paths from `$failed_log`.
  - Per-file: input pixels × → SVG path count (heuristic: `grep -c '<path' <file>`), file size delta.
  - Tuning suggestions if path count is suspiciously high (likely too noisy — raise `filter_speckle`) or low (likely over-simplified — drop `layer_difference`).

#### Notes

- vtracer is MIT — free to bundle and use.
- For B/W technical drawings / scanned line art, `binary` mode is dramatically faster and produces cleaner output than `color`.
- Common preset suggestions:
  - **Logo / icon (clean source):** `color, color_precision=6, filter_speckle=4, layer_difference=16`. Defaults are tuned for this.
  - **Photo → flat illustration:** `color, color_precision=3, filter_speckle=20, layer_difference=32`. Aggressive simplification, painterly look.
  - **Line drawing / scan:** `binary, filter_speckle=10`. Smallest output.
- If vtracer's quality isn't enough for a specific case, fall back to Inkscape's bitmap trace or `potrace` (B/W only). vtracer is the right default for everything else.
- vtracer ships a CLI binary too (`vtracer-cli`) — the Python wheel is preferred here so the venv is self-contained.

---

### Web-Ready (orchestrator)

**Name.** `web-ready`

**When to use.** Use when the user wants to take a folder of images (any mix of HEIC, RAW, PNG, JPEG, TIFF, WebP) and produce a web-ready set — EXIF stripped, resized to a sensible max dimension, encoded in modern formats (AVIF + WebP, with JPEG fallback), and optimized for size. End-to-end orchestrator over the single-purpose skills in this plugin.

**Triggers.** make this folder web-ready, prep these photos for upload, get these images ready for my blog

One-shot pipeline: ingest anything → strip EXIF → resize → encode to web formats → optimize. The "make this folder uploadable" skill.

#### When to use

- Photos coming off a phone (HEIC) destined for a blog.
- Camera RAW exports being prepped for an online gallery.
- A mixed folder of screenshots/photos that needs to ship to the web.
- Pre-step before image upload to any CMS, S3 bucket, or Cloudflare R2.

Do **not** use this skill when:
- The user wants archival output → keep originals; use the targeted skills (`to-jxl`, `transcode-jpeg-to-jxl-lossless`, `optimize-png`).
- The user wants pixel-perfect originals on the web (rare, e.g. art prints) → use `optimize-png`/`optimize-jpeg` only, no resize.
- Single-file conversion → call the underlying skill directly.

#### Inputs

1. **Input directory** — required.
2. **Profile** — preset bundle. One of:
   - `blog` (default): max-side 2000px, AVIF q60 + WebP q80 + JPEG q82 fallback, EXIF stripped.
   - `gallery`: max-side 3000px, AVIF q70 + WebP q85, EXIF stripped.
   - `thumbnail`: max-side 800px, AVIF q55 + WebP q75, EXIF stripped.
   - `archival-web`: max-side 4000px, AVIF q80 + WebP q90, **EXIF preserved**.
3. **Custom overrides** — any of `--max-side N`, `--avif-q N`, `--webp-q N`, `--jpeg-q N`, `--keep-exif`, `--no-jpeg-fallback`.
4. **Output dir** — default: `<input>/web/`. Inside: `web/avif/`, `web/webp/`, `web/jpg/` parallel trees so the user can pick which set to upload.
5. **Recursive** — `--recursive`. Mirrors subdirectory layout.

#### Procedure

1. **Pre-flight:** check each tool the pipeline needs and record which are present:

   ```bash
   for t in magick exiftool vipsthumbnail avifenc cwebp cjpeg oxipng jpegoptim \
            heif-convert darktable-cli
   do
     command -v "$t" >/dev/null && echo "ok    $t" || echo "MISS  $t"
   done
   ```

   `magick` and `exiftool` are required — stop and point at `install-deps` if either is missing. The rest are optional: a missing encoder drops its output format from the pipeline with a one-line note, and a missing `heif-convert` / `darktable-cli` narrows which sources can be ingested (stage 1).

   For the mozjpeg-quality JPEG fallback, resolve `$MOZ_BIN` as described in `optimize-jpeg` step 1 — a bare `cjpeg` on PATH is libjpeg-turbo, not mozjpeg.

2. **Stage 1: Decode/normalise inputs.** Walk the input tree; classify each file:
   - JPEG/PNG/WebP/TIFF → pass through.
   - HEIC → decode to PNG via `heif-convert` (or via `vipsthumbnail` if libvips has libheif). Fail loud if neither is available.
   - RAW (CR2, ARW, NEF, DNG, ORF, RAF) → decode via `darktable-cli "$input" "$staged.tiff"`. There is no libvips fallback here: libvips ships no camera-RAW decoder for these formats (a DNG that happens to be TIFF-wrapped may partially load via tiffload, but CR2/ARW/NEF/ORF/RAF will not). If `darktable-cli` is missing, skip the file with a flagged warning naming the format, and tell the user in the summary that RAW ingestion needs `darktable-cli` installed.
   - Anything else (BMP, GIF, etc.) → pass through.

3. **Stage 2: Strip EXIF.** Unless `--keep-exif` set:

   ```bash
   exiftool -all= -tagsfromfile @ -Orientation -ColorSpace -overwrite_original "$staged"
   ```

   Preserve `Orientation` and `ColorSpace` (rotation handling and colour fidelity) even in strip mode.

4. **Stage 3: Resize.** Per file, fit within `<max-side>` box preserving aspect:

   ```bash
   vipsthumbnail "$staged" --size "${max_side}x${max_side}" --output "$resized.png[Q=100]"
   ```

   Use lossless intermediate to avoid double-compression. Skip if the source's longest side is already ≤ max-side.

5. **Stage 4: Encode.** For each survivor, produce up to three outputs:

   - **AVIF:** `avifenc -q "$avif_q" -s 6 "$resized.png" "$out/avif/$basename.avif"`
   - **WebP:** `cwebp -q "$webp_q" "$resized.png" -o "$out/webp/$basename.webp"`
   - **JPEG fallback** (unless `--no-jpeg-fallback`): `cjpeg` cannot read PNG — it decodes PPM/PGM/BMP/Targa only — so the stage-3 PNG must be decoded first:

     ```bash
     magick "$resized.png" ppm:- \
       | "$MOZ_BIN/cjpeg" -quality "$jpeg_q" -progressive -optimize \
       > "$out/jpg/$basename.jpg"
     ```

     If `$MOZ_BIN` did not resolve in pre-flight, use ImageMagick end to end instead — slightly larger output, but it reads PNG natively:

     ```bash
     magick "$resized.png" -quality "$jpeg_q" -interlace Plane "$out/jpg/$basename.jpg"
     ```

   Run encodes in parallel — they're independent. Check each encoder's exit status and record failures per file and per format; a format that fails for one file must not abort the other two or the rest of the batch.

6. **Stage 5: Optimize (final squeeze).**
   - JPEGs: `jpegoptim --strip-all --all-progressive` in-place on `web/jpg/`.
   - PNGs (only if any survived as PNG, e.g. with `--no-jpeg-fallback`): `oxipng -o 4 --strip safe`.
   - AVIF / WebP: avifenc and cwebp already produce near-optimal output; no second pass.

7. **Cleanup:** delete `<staged>` intermediates. Write a manifest at `<output>/manifest.json` mapping `<original-path> → {avif, webp, jpg}` plus per-file size deltas.

#### Output

- Three parallel trees under `<output-dir>`: `avif/`, `webp/`, `jpg/`.
- `manifest.json` with the mapping and size table.
- Summary report:
  - Files processed / skipped / failed (with reasons).
  - Total bytes per format. Typical: `<orig> → AVIF <X>%, WebP <Y>%, JPEG <Z>%`.
  - Recommendation line: which format to upload (AVIF if all targets support it; WebP otherwise; JPEG as universal fallback).

#### Notes

- Defaults are tuned for the `blog` profile. `gallery` and `archival-web` raise quality for slower-but-better output.
- The orchestrator never modifies originals. The output tree is fully separate.
- For very large input trees (>10k files), the stage-by-stage design is intentional — early failure of one stage doesn't waste the others' work; intermediates persist until cleanup.
- Companion skills: `convert-to-avif` (single-format), `optimize-png`, `optimize-jpeg`, `fast-resize`; plus the `/convert-to-webp` command for single-format WebP. This orchestrator composes the same tools; the user is welcome to use the components directly when they want finer control.

---

### Image Workspace Setup

**Name.** `workspace-setup`

**When to use.** Register or create the user's image operations workspace — a folder on disk where they keep image projects. Use on first run, or when the user says "set up my image workspace", "register my image workspace", "change my image workspace path", or similar. Persists the path so other skills (open-workspace, new-project) can reference it.

Register the folder the user treats as their image operations workspace. Individual projects live as sub-folders inside it.

#### Data store

```
${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/workspace.json
```

Do **not** write under `~/.claude/`.

#### Procedure

##### 1. Check for existing config

```bash
DATA_DIR="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops"
CONFIG="$DATA_DIR/workspace.json"
test -f "$CONFIG" && echo "$CONFIG"
```

If the file exists, display it with the `Read` tool rather than `cat` — this skill declares `Read` for exactly that, and it keeps the Bash grants down to the ones that actually do work.

If one exists, show the path and ask whether to keep or change it.

##### 2. Ask the user

1. **Existing or new?** — do they already have an image workspace, or should one be created?
2. **Path?**
   - Existing: ask for absolute path; verify with `test -d`.
   - New: propose `~/media-workspaces/images` as the default. Don't auto-create until the user confirms.

##### 3. (New only) Version control

Ask whether to `git init` the workspace. Default **no** — image libraries can be large. Only `git init` is in scope; this skill never commits, adds a remote, or pushes.

##### 4. Create + persist

```bash
mkdir -p "$DATA_DIR" \
  || { echo "cannot create $DATA_DIR — check permissions" >&2; exit 1; }

# Only if new:
mkdir -p "$CHOSEN_PATH" \
  || { echo "cannot create $CHOSEN_PATH — check the path and permissions" >&2; exit 1; }

WS_PATH=$(realpath "$CHOSEN_PATH")
CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Stop on either failure — persisting a config that points at a directory that does not exist just moves the error to the next skill that reads it.

Write `workspace.json` with the `Write` tool, substituting the two values above:

```json
{
  "path": "<WS_PATH>",
  "created": "<CREATED>",
  "version_controlled": false,
  "type": "image"
}
```

`realpath` canonicalises the path so `open-workspace` and `new-project` resolve the same directory regardless of how the user typed it.

##### 5. Confirm

Print the registered path. Remind the user they can now say "open my image workspace" or "create a new image project".

---

## Commands

These carry their own instructions rather than delegating to a skill. A
runtime without slash commands can run one by following its body directly.

### Apply Image Filters

**Name.** `apply-filters`

**What it does.** Apply artistic or corrective filters to images with ImageMagick.

You are a photo editing assistant specialized in applying artistic and corrective filters to images using ImageMagick and other tools.

#### Your Task

Help the user apply filters and effects to their images:

1. Ask the user for:
   - Input image(s)
   - Desired filter/effect type
   - Intensity/parameters
   - Whether to batch process
   - Output path

2. Apply filters using ImageMagick:
   - Color adjustments
   - Artistic effects
   - Blur and sharpening
   - Vintage/retro effects
   - Custom filter chains

3. Execute and verify results

#### Popular Filters

##### Black and White

**Simple grayscale:**
```bash
convert input.jpg -colorspace Gray output.jpg
```

**High-contrast B&W:**
```bash
convert input.jpg -colorspace Gray -contrast -contrast output.jpg
```

**Dramatic B&W (channel mixer):**
```bash
convert input.jpg -channel R -evaluate multiply 0.3 -channel G -evaluate multiply 0.59 -channel B -evaluate multiply 0.11 -separate -average output.jpg
```

##### Vintage/Retro Effects

**Sepia tone:**
```bash
convert input.jpg -sepia-tone 80% output.jpg
```

**Vintage fade:**
```bash
convert input.jpg -modulate 100,80,100 -fill '#ffe4b5' -colorize 20% output.jpg
```

**Polaroid effect:**
```bash
convert input.jpg -bordercolor white -border 10 -bordercolor grey60 -border 1 -background black \( +clone -shadow 60x4+4+4 \) +swap -background white -flatten output.jpg
```

##### Color Adjustments

**Boost saturation:**
```bash
convert input.jpg -modulate 100,150,100 output.jpg
```

**Warm tone:**
```bash
convert input.jpg -modulate 100,100,110 output.jpg
```

**Cool tone:**
```bash
convert input.jpg -modulate 100,100,90 output.jpg
```

**Auto-level (normalize colors):**
```bash
convert input.jpg -auto-level output.jpg
```

**Increase vibrance:**
```bash
convert input.jpg -modulate 100,120 output.jpg
```

##### Blur Effects

**Gaussian blur:**
```bash
convert input.jpg -blur 0x8 output.jpg
```

**Motion blur:**
```bash
convert input.jpg -motion-blur 0x20+45 output.jpg
```

**Radial blur:**
```bash
convert input.jpg -radial-blur 10 output.jpg
```

##### Sharpen

**Unsharp mask:**
```bash
convert input.jpg -unsharp 0x1.5+1.0+0.05 output.jpg
```

**Strong sharpen:**
```bash
convert input.jpg -sharpen 0x2.0 output.jpg
```

##### Artistic Effects

**Oil painting:**
```bash
convert input.jpg -paint 4 output.jpg
```

**Sketch/pencil drawing:**
```bash
convert input.jpg -colorspace Gray -sketch 0x20+135 output.jpg
```

**Charcoal drawing:**
```bash
convert input.jpg -charcoal 2 output.jpg
```

**Edge detection:**
```bash
convert input.jpg -edge 2 output.jpg
```

**Emboss:**
```bash
convert input.jpg -emboss 2 output.jpg
```

**Posterize:**
```bash
convert input.jpg -posterize 4 output.jpg
```

##### HDR Effect

```bash
convert input.jpg \( +clone -blur 0x12 \) -compose overlay -composite -modulate 100,130 output.jpg
```

##### Instagram-Style Filters

**Nashville (warm, vintage):**
```bash
convert input.jpg -modulate 120,150,100 -fill '#f7daae' -colorize 20% -gamma 1.2 output.jpg
```

**Kelvin (warm, high contrast):**
```bash
convert input.jpg -modulate 110,100,100 -fill '#ff9900' -colorize 10% -contrast output.jpg
```

**Lomo (high contrast, vignette):**
```bash
convert input.jpg -modulate 100,150,100 -sigmoidal-contrast 3,50% \( +clone -sparse-color Barycentric '0,0 black 0,%h black %w,0 black %w,%h black' -function polynomial 1,-1,1 \) -compose multiply -composite output.jpg
```

#### Batch Processing

**Apply filter to all images:**
```bash
for file in *.jpg; do
  convert "$file" -sepia-tone 80% "vintage_${file}"
done
```

**Multiple filters in sequence:**
```bash
convert input.jpg -modulate 100,120 -unsharp 0x1.5 -auto-level output.jpg
```

#### Advanced Filter Combinations

**Professional portrait enhancement:**
```bash
convert input.jpg \
  -unsharp 0x1.0+1.0+0.05 \
  -modulate 100,105,100 \
  -sigmoidal-contrast 2,50% \
  output.jpg
```

**Landscape enhancement:**
```bash
convert input.jpg \
  -modulate 100,130,100 \
  -unsharp 0x1.5 \
  -auto-level \
  output.jpg
```

**Matte effect:**
```bash
convert input.jpg \
  -modulate 100,80,100 \
  -gamma 0.9 \
  -fill black -colorize 5% \
  output.jpg
```

#### Custom LUT (Color Grading)

Create and apply custom color lookup tables:
```bash
convert input.jpg your_lut.png -hald-clut output.jpg
```

#### Best Practices

- Always keep original images
- Test filters on a single image before batch processing
- Combine multiple subtle effects rather than one extreme effect
- Use `-quality 95` to preserve image quality
- Preview results before processing large batches
- Document your filter recipes for consistent style

#### Quick Reference

| Effect | Command Option |
|--------|----------------|
| Grayscale | `-colorspace Gray` |
| Sepia | `-sepia-tone 80%` |
| Blur | `-blur 0x8` |
| Sharpen | `-unsharp 0x1.5` |
| Contrast | `-contrast` |
| Brightness | `-modulate 120` |
| Saturation | `-modulate 100,150` |
| Edge detect | `-edge 2` |

Help users create stunning visual effects and enhance their photos professionally.

---

### Batch Resize Images

**Name.** `batch-resize`

**What it does.** Resize a whole folder of images to target dimensions or a scale factor.

You are a photo editing assistant specialized in batch resizing images efficiently.

#### Your Task

Help the user resize single or multiple images:

1. Ask the user for:
   - Input image(s) or directory
   - Target dimensions (width x height, or percentage, or max dimension)
   - Whether to maintain aspect ratio
   - Output format (keep original or convert)
   - Output directory/naming pattern

2. Choose the appropriate tool:
   - **ImageMagick** (`convert`/`mogrify`) - powerful CLI tool
   - **FFmpeg** - for image sequences
   - **Python PIL/Pillow** - for complex batch operations

3. Execute and verify:
   - Process images
   - Report dimensions before/after
   - Check output quality
   - List processed files

#### ImageMagick Resize Commands

**Resize single image to exact dimensions:**
```bash
convert input.jpg -resize 1920x1080! output.jpg
```

**Resize maintaining aspect ratio (fit within box):**
```bash
convert input.jpg -resize 1920x1080 output.jpg
```

**Resize to specific width (auto height):**
```bash
convert input.jpg -resize 1920x output.jpg
```

**Resize to specific height (auto width):**
```bash
convert input.jpg -resize x1080 output.jpg
```

**Resize by percentage:**
```bash
convert input.jpg -resize 50% output.jpg
```

**Resize to maximum dimension (longest side):**
```bash
convert input.jpg -resize 1920x1920\> output.jpg
```

#### Batch Processing with ImageMagick

**Resize all JPGs in directory:**
```bash
for file in *.jpg; do
  convert "$file" -resize 1920x1080 "resized_${file}"
done
```

**In-place resize with mogrify:**
```bash
mogrify -resize 1920x1080 *.jpg
```

**Resize and convert to different format:**
```bash
for file in *.png; do
  convert "$file" -resize 1920x1080 "${file%.png}.jpg"
done
```

**Resize with quality control:**
```bash
for file in *.jpg; do
  convert "$file" -resize 1920x1080 -quality 90 "resized_${file}"
done
```

#### Advanced Options

**Resize and add padding/background:**
```bash
convert input.jpg -resize 1920x1080 -background black -gravity center -extent 1920x1080 output.jpg
```

**Resize with sharpening:**
```bash
convert input.jpg -resize 1920x1080 -sharpen 0x1.0 output.jpg
```

**Resize multiple images to same directory:**
```bash
mkdir resized
for file in *.jpg; do
  convert "$file" -resize 1920x1080 "resized/$file"
done
```

#### Common Use Cases & Presets

**Thumbnail generation (200px):**
```bash
convert input.jpg -resize 200x200^ -gravity center -extent 200x200 thumbnail.jpg
```

**Social media - Instagram (1080x1080):**
```bash
convert input.jpg -resize 1080x1080^ -gravity center -extent 1080x1080 instagram.jpg
```

**Social media - Facebook cover (820x312):**
```bash
convert input.jpg -resize 820x312^ -gravity center -extent 820x312 fb_cover.jpg
```

**4K to HD:**
```bash
convert input.jpg -resize 1920x1080 hd_output.jpg
```

**Mobile optimization (800px max width):**
```bash
convert input.jpg -resize 800x\> mobile.jpg
```

#### Python Script for Complex Batch Operations

Offer to create a Python script for advanced needs:

```python
from PIL import Image
import os

def resize_images(input_dir, output_dir, max_size=(1920, 1080)):
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            img_path = os.path.join(input_dir, filename)
            img = Image.open(img_path)

            # Resize maintaining aspect ratio
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            output_path = os.path.join(output_dir, filename)
            img.save(output_path, quality=90, optimize=True)
            print(f"Resized: {filename} -> {img.size}")

resize_images("./input", "./output", (1920, 1080))
```

#### Best Practices

- Always keep original images as backup
- Use `-quality 90` or higher for minimal quality loss
- Use `>` suffix to only shrink images, never enlarge
- Test on a few images before batch processing
- Consider using `-strip` to remove metadata and reduce file size
- Use appropriate resampling filters: Lanczos for best quality

#### Performance Tips

- Use `mogrify` for in-place batch operations (faster)
- Process in parallel with GNU parallel:
  ```bash
  ls *.jpg | parallel convert {} -resize 1920x1080 resized/{}
  ```
- For huge batches, use `-quality 85` to balance size/quality

Help users efficiently resize their image collections with professional quality.

---

### bg-removal

**Name.** `bg-removal`

**What it does.** Remove the background from every image in a folder.

This folder contains images.

I need the background removed.

Let's use rmbg for this purpose (installed on this machine).

Script the job.

---

### Compress Images

**Name.** `compress-images`

**What it does.** Reduce image file size while holding quality at an acceptable level.

You are a photo editing assistant specialized in optimizing and compressing images to reduce file size while maintaining acceptable quality.

#### Your Task

Help the user compress images efficiently:

1. Ask the user for:
   - Input image(s) or directory
   - Target compression level or file size
   - Whether to convert format (JPEG, WebP, AVIF)
   - Whether to resize during compression
   - Output quality preference

2. Choose compression method:
   - **Lossy compression** (JPEG, WebP) - smaller files, some quality loss
   - **Lossless optimization** - remove metadata, optimize encoding
   - **Format conversion** - modern formats (WebP, AVIF) for better compression
   - **Progressive/responsive** - optimize for web delivery

3. Execute and report:
   - Original vs compressed file sizes
   - Compression ratio achieved
   - Quality metrics if needed

#### JPEG Compression

##### ImageMagick

**High quality (minimal compression):**
```bash
convert input.jpg -quality 95 output.jpg
```

**Balanced quality/size:**
```bash
convert input.jpg -quality 85 output.jpg
```

**Web optimized:**
```bash
convert input.jpg -quality 75 -strip output.jpg
```

**Aggressive compression:**
```bash
convert input.jpg -quality 60 -strip output.jpg
```

**Progressive JPEG (better for web):**
```bash
convert input.jpg -quality 85 -interlace Plane -strip output.jpg
```

##### jpegoptim (Lossless Optimization)

**Install jpegoptim if needed:**
```bash
sudo apt install jpegoptim
```

**Lossless optimization:**
```bash
jpegoptim --strip-all input.jpg
```

**Target maximum quality:**
```bash
jpegoptim --max=85 --strip-all input.jpg
```

**Target file size (e.g., 200KB):**
```bash
jpegoptim --size=200k input.jpg
```

#### PNG Compression

##### optipng

**Install optipng:**
```bash
sudo apt install optipng
```

**Optimize PNG (lossless):**
```bash
optipng -o7 input.png
```

**Faster optimization:**
```bash
optipng -o2 input.png
```

##### pngquant (Lossy but High Quality)

**Install pngquant:**
```bash
sudo apt install pngquant
```

**Compress PNG with quality control:**
```bash
pngquant --quality=65-80 input.png -o output.png
```

**Aggressive compression:**
```bash
pngquant --quality=50-70 input.png -o output.png
```

#### WebP Conversion (Superior Compression)

**Convert JPEG to WebP:**
```bash
convert input.jpg -quality 85 output.webp
```

**Convert PNG to WebP (lossy):**
```bash
convert input.png -quality 85 output.webp
```

**Convert PNG to WebP (lossless):**
```bash
cwebp -lossless input.png -o output.webp
```

**High quality WebP:**
```bash
cwebp -q 90 input.jpg -o output.webp
```

#### AVIF Conversion (Best Compression)

**Convert to AVIF (modern, excellent compression):**
```bash
convert input.jpg -quality 80 output.avif
```

**Using avifenc for better control:**
```bash
avifenc -s 6 -j 8 --min 0 --max 63 -a end-usage=q -a cq-level=20 input.jpg output.avif
```

#### Batch Compression

**Compress all JPEGs in directory:**
```bash
for file in *.jpg; do
  convert "$file" -quality 85 -strip "compressed_${file}"
done
```

**In-place JPEG optimization:**
```bash
jpegoptim --max=85 --strip-all *.jpg
```

**Batch PNG optimization:**
```bash
optipng -o5 *.png
```

**Convert all images to WebP:**
```bash
for file in *.{jpg,png}; do
  [ -f "$file" ] && convert "$file" -quality 85 "${file%.*}.webp"
done
```

#### Compression with Resizing

**Resize and compress for web:**
```bash
convert input.jpg -resize 1920x1080\> -quality 85 -strip output.jpg
```

**Create multiple sizes (responsive images):**
```bash
convert input.jpg -resize 1920x\> -quality 85 large.jpg
convert input.jpg -resize 1280x\> -quality 85 medium.jpg
convert input.jpg -resize 640x\> -quality 85 small.jpg
```

#### Metadata Removal (Reduces Size)

**Strip all metadata:**
```bash
convert input.jpg -strip output.jpg
```

**Remove EXIF data with exiftool:**
```bash
exiftool -all= input.jpg
```

#### Compression Comparison Script

```bash
#!/bin/bash
# Compare compression methods

input="$1"
basename="${input%.*}"

echo "Original: $(du -h "$input" | cut -f1)"

# JPEG quality 85
convert "$input" -quality 85 -strip "${basename}_q85.jpg"
echo "JPEG Q85: $(du -h "${basename}_q85.jpg" | cut -f1)"

# WebP
convert "$input" -quality 85 "${basename}.webp"
echo "WebP Q85: $(du -h "${basename}.webp" | cut -f1)"

# AVIF
convert "$input" -quality 80 "${basename}.avif"
echo "AVIF Q80: $(du -h "${basename}.avif" | cut -f1)"
```

#### Quality Guidelines

| Quality | Use Case | File Size |
|---------|----------|-----------|
| 95-100 | Archival, print | Largest |
| 85-90 | High-quality web, portfolio | Large |
| 75-85 | Standard web use | Medium |
| 60-75 | Thumbnails, previews | Small |
| < 60 | Heavy compression, icons | Smallest |

#### Format Comparison

| Format | Compression | Quality | Browser Support | Best For |
|--------|-------------|---------|-----------------|----------|
| JPEG | Good | Good | Universal | Photos |
| PNG | Fair (lossless) | Excellent | Universal | Graphics, transparency |
| WebP | Excellent | Excellent | Modern browsers | Web (general) |
| AVIF | Best | Excellent | Newer browsers | Modern web |

#### Advanced Optimization Pipeline

**Complete optimization pipeline:**
```bash
#!/bin/bash
# Optimize image with multiple steps

input="$1"
output="${input%.*}_optimized.jpg"

# Step 1: Resize if too large
convert "$input" -resize 1920x1080\> temp1.jpg

# Step 2: Strip metadata
convert temp1.jpg -strip temp2.jpg

# Step 3: Optimize quality
convert temp2.jpg -quality 85 -interlace Plane temp3.jpg

# Step 4: Further optimize with jpegoptim
jpegoptim --max=85 --strip-all temp3.jpg -d . --stdout > "$output"

# Cleanup
rm temp1.jpg temp2.jpg temp3.jpg

echo "Original: $(du -h "$input" | cut -f1)"
echo "Optimized: $(du -h "$output" | cut -f1)"
```

#### Best Practices

- **Always keep original images** as backup
- Use quality 85 for best balance of size/quality
- Strip metadata for web images (privacy + size reduction)
- Consider WebP or AVIF for modern websites
- Use progressive JPEG for better web loading experience
- Test different quality levels on representative images
- For batch operations, test on a few images first
- Monitor file size reductions to ensure acceptable results

#### Target File Sizes (Web Guidelines)

- **Hero images**: < 200-300 KB
- **Content images**: < 100-150 KB
- **Thumbnails**: < 30-50 KB
- **Icons**: < 10 KB

Help users achieve optimal file sizes while maintaining visual quality for their specific needs.

---

### convert-to-webp

**Name.** `convert-to-webp`

**What it does.** Convert every image in the current directory to WebP.

Convert all the images in this directory to webp.

---

### Crop Images

**Name.** `crop-images`

**What it does.** Crop images to fixed dimensions, an aspect ratio, or a custom area.

You are a photo editing assistant specialized in cropping images to specific dimensions, aspect ratios, or custom areas.

#### Your Task

Help the user crop images precisely:

1. Ask the user for:
   - Input image(s)
   - Crop method (dimensions, aspect ratio, coordinates, smart crop)
   - Target size or ratio
   - Alignment (center, top, bottom, left, right)
   - Output path

2. Use ImageMagick or FFmpeg:
   - Crop to exact dimensions
   - Crop to aspect ratio
   - Crop based on coordinates
   - Smart crop based on content
   - Batch processing

3. Execute and verify results

#### ImageMagick Crop Commands

##### Crop to Specific Dimensions

**Crop 800x600 from top-left:**
```bash
convert input.jpg -crop 800x600+0+0 output.jpg
```

**Crop 800x600 from center:**
```bash
convert input.jpg -gravity center -crop 800x600+0+0 output.jpg
```

**Crop from specific coordinates (x,y):**
```bash
convert input.jpg -crop 800x600+100+50 output.jpg
```

##### Crop to Aspect Ratio (Center)

**Crop to 16:9 ratio:**
```bash
convert input.jpg -gravity center -crop 16:9 output.jpg
```

**Crop to 1:1 (square):**
```bash
convert input.jpg -gravity center -crop 1:1 output.jpg
```

**Crop to 4:3 ratio:**
```bash
convert input.jpg -gravity center -crop 4:3 output.jpg
```

##### Gravity Options for Alignment

**Crop from top:**
```bash
convert input.jpg -gravity north -crop 1920x800+0+0 output.jpg
```

**Crop from bottom:**
```bash
convert input.jpg -gravity south -crop 1920x800+0+0 output.jpg
```

**Crop from left:**
```bash
convert input.jpg -gravity west -crop 800x1080+0+0 output.jpg
```

**Crop from right:**
```bash
convert input.jpg -gravity east -crop 800x1080+0+0 output.jpg
```

##### Smart Crop (Content-Aware)

**Auto-crop whitespace/borders:**
```bash
convert input.jpg -trim +repage output.jpg
```

**Crop to largest centered square:**
```bash
convert input.jpg -gravity center -crop 1:1 +repage output.jpg
```

##### Social Media Crops

**Instagram square (1080x1080):**
```bash
convert input.jpg -gravity center -crop 1080x1080+0+0 +repage output.jpg
```

**Instagram portrait (1080x1350):**
```bash
convert input.jpg -gravity center -crop 4:5 -resize 1080x1350 +repage output.jpg
```

**YouTube thumbnail (1280x720):**
```bash
convert input.jpg -gravity center -crop 16:9 -resize 1280x720 +repage output.jpg
```

**Twitter header (1500x500):**
```bash
convert input.jpg -gravity center -crop 1500x500+0+0 +repage output.jpg
```

**Facebook cover (820x312):**
```bash
convert input.jpg -gravity center -crop 820x312+0+0 +repage output.jpg
```

#### Batch Cropping

**Crop all images to same size:**
```bash
for file in *.jpg; do
  convert "$file" -gravity center -crop 1920x1080+0+0 +repage "cropped_${file}"
done
```

**Crop all to square:**
```bash
for file in *.jpg; do
  convert "$file" -gravity center -crop 1:1 +repage "square_${file}"
done
```

#### Advanced Cropping Techniques

**Crop and resize in one command:**
```bash
convert input.jpg -gravity center -crop 16:9 -resize 1920x1080 +repage output.jpg
```

**Crop with percentage:**
```bash
convert input.jpg -gravity center -crop 80%x80% +repage output.jpg
```

**Multiple crops from one image:**
```bash
convert input.jpg -gravity center -crop 800x600 +repage tile_%d.jpg
```

**Crop with aspect fill (no distortion):**
```bash
convert input.jpg -resize 1920x1080^ -gravity center -crop 1920x1080+0+0 +repage output.jpg
```

#### Python Script for Interactive Cropping

Offer to create a script for complex cropping needs:

```python
from PIL import Image
import os

def crop_to_aspect_ratio(input_path, output_path, aspect_width, aspect_height):
    img = Image.open(input_path)
    width, height = img.size

    target_ratio = aspect_width / aspect_height
    current_ratio = width / height

    if current_ratio > target_ratio:
        # Image is too wide, crop width
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        img_cropped = img.crop((left, 0, left + new_width, height))
    else:
        # Image is too tall, crop height
        new_height = int(width / target_ratio)
        top = (height - new_height) // 2
        img_cropped = img.crop((0, top, width, top + new_height))

    img_cropped.save(output_path, quality=95)
    print(f"Cropped to {aspect_width}:{aspect_height} -> {output_path}")

# Example: Crop to 16:9
crop_to_aspect_ratio("input.jpg", "output.jpg", 16, 9)
```

#### Common Aspect Ratios

| Ratio | Description | Use Case |
|-------|-------------|----------|
| 1:1 | Square | Instagram, profile pictures |
| 4:3 | Traditional | Standard photos, presentations |
| 16:9 | Widescreen | YouTube, TV, monitors |
| 21:9 | Ultra-wide | Cinematic, ultra-wide monitors |
| 4:5 | Portrait | Instagram portrait |
| 9:16 | Vertical | Instagram Stories, TikTok |
| 3:2 | Photo | DSLR standard |

#### Best Practices

- Always use `+repage` after cropping to reset image geometry
- Test crop on one image before batch processing
- Keep original images as backup
- Use `-gravity center` for most balanced crops
- For smart content-aware cropping, consider using `-trim` first
- Combine crop with resize for optimal results
- Use exact pixel dimensions when precision matters

#### Troubleshooting

**Image appears offset after crop:**
- Add `+repage` to reset virtual canvas

**Crop creates multiple tiles:**
- Use `+repage` and specify exact offset like `+0+0`

**Quality loss after cropping:**
- Add `-quality 95` to preserve quality

Help users crop images precisely for any purpose while maintaining quality and composition.

---

### Deduplicate Images

**Name.** `dedupe`

**What it does.** Find and remove duplicate and near-duplicate images.

Find and remove duplicate or near-duplicate images.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default recursive for dedupe (since duplicates often live in sibling folders).

2. **Ask the user what kind of dedupe** they want:
   - **Exact duplicates** — byte-identical files (md5 / sha1). Fast, reliable. Use `fdupes` or a quick md5 pass.
   - **Near-duplicates** — same image re-encoded, resized, or lightly edited. Use perceptual hashing (dHash / pHash) via Python + `imagehash`, or `findimagedupes`.
   - **Both** — exact first, then perceptual on the remainder.

3. **Run detection**:

   Exact:
   ```bash
   fdupes -r <target>/
   # or
   find <target> -type f \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.heic' \
     -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \) \
     -exec md5sum {} + | sort | uniq -D -w 32
   ```

   Perceptual (Python + imagehash — preferred; tolerant of re-encodes and mild edits):
   ```bash
   python3 -c "
   import imagehash, pathlib
   from PIL import Image
   hashes = {}
   for p in pathlib.Path('.').rglob('*'):
       if p.suffix.lower() in {'.jpg','.jpeg','.png','.heic','.webp','.tif','.tiff'}:
           try: h = imagehash.dhash(Image.open(p))
           except Exception: continue
           hashes.setdefault(str(h), []).append(str(p))
   for h, files in hashes.items():
       if len(files) > 1: print(h, files)
   "
   ```

   Check tools before invoking: `command -v fdupes`, `python3 -c 'import imagehash'`. If `imagehash` is missing, offer `pip install imagehash Pillow` or a `pipx run` one-liner.

4. **Present duplicate groups** — for each group show filename, size, dimensions, format, and mtime. Mark the proposed **keeper** (default: largest dimensions, then largest byte size, then earliest mtime). Let the user override keeper per group.

5. **Wait for confirmation.** Never auto-remove.

6. **Move non-keepers** to `archive/duplicates/` (preserving the relative path as a manifest sidecar). Do not delete. The user decides when to empty `archive/`.

7. **Log** to `notes/dedupe-{timestamp}.md`:
   - Method used (exact / perceptual / both) and threshold (Hamming distance for perceptual — default 0 for identical dHash, up to 5 for "near")
   - Group count, files moved, files kept
   - Full keeper / non-keeper list

#### Notes

- Perceptual hashing across very different resolutions is unreliable — warn the user if they're mixing thumbnails with originals.
- RAW + JPEG pairs from the same shot are **not** duplicates — exclude RAW extensions from perceptual dedupe by default, and flag pair relationships separately.
- `fdupes` handles the exact case fast; don't reimplement it in Python unless `fdupes` is unavailable.
- Never delete. `archive/duplicates/` is the disposal path.

---

### Group Images by Camera

**Name.** `group-by-camera`

**What it does.** Cluster images into folders by EXIF camera make and model.

Cluster images by EXIF camera Make + Model.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default flat.

2. **Read camera metadata** for each image:
   ```bash
   exiftool -s -s -s -Make -Model -LensModel "image.jpg"
   ```
   Build a bucket label of the form `{Make}_{Model}` with spaces and slashes replaced by hyphens (e.g. `NIKON-CORPORATION_NIKON-D850`, `Apple_iPhone-15-Pro`, `SONY_ILCE-7M3`).

3. **Bucket files**:
   - `{Make}_{Model}/` — one folder per unique (Make, Model) pair
   - `no-exif/` — images with no readable camera metadata (screenshots, scrubbed photos, generated art)
   - `unknown/` — EXIF present but Make or Model missing

4. **Preview before acting** — table of bucket label → count, plus a sample filename per bucket. Wait for user confirmation. Offer to merge near-duplicate bucket names (common: `NIKON CORPORATION` vs `NIKON`).

5. **Prefer symlinks or CSV manifest over physical moves**:
   - Option A: symlinked sub-folders
   - Option B: `metadata/camera-buckets.csv` with `filename,make,model,bucket`
   - Option C: physical move on explicit confirmation

6. **Log** to `notes/group-by-camera-{timestamp}.md` with bucket counts and the no-EXIF / unknown tallies.

#### Notes

- Lens model is interesting but produces fragmented buckets — include it in the CSV manifest but not in the folder label.
- Phone photos often have consistent Make/Model but many firmware variants; don't try to split on firmware.
- If a user's library is dominated by `no-exif/`, that usually means it was previously scrubbed — note this in the log.

---

### Group Images by Capture Time

**Name.** `group-by-time`

**What it does.** Cluster images into year and month folders by EXIF capture time.

Cluster images by EXIF `DateTimeOriginal` into year / month (and optionally day) folders.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default flat.

2. **Confirm granularity** with the user:
   - `YYYY/` only
   - `YYYY/MM/` (default)
   - `YYYY/MM/DD/`
   - Custom (e.g. session-based, gap > N hours starts a new group)

3. **Read capture timestamps** for each image. Prefer, in order:
   1. `exiftool` `DateTimeOriginal`
   2. `exiftool` `CreateDate` / `MediaCreateDate`
   3. `exiftool` `FileModifyDate` (fallback — **warn the user** when falling back, since mtime reflects copy time)
   ```bash
   exiftool -s -s -s -DateTimeOriginal -CreateDate -FileModifyDate "image.jpg"
   ```

4. **Build a timeline** — sorted (filename, timestamp) list. Show the user min/max timestamps and any suspicious gaps / duplicates.

5. **Propose grouping** — print bucket labels (`2026/04/`, `2026/04/18/`) with image counts. Flag any file that fell back to mtime. Let the user rename buckets (e.g. `2026-04-18_wedding/`).

6. **Preview before acting**, then choose method:
   - Option A: `metadata/time-groups.csv` with `filename,timestamp,group` (no moves)
   - Option B: symlinked folders (`time-groups/2026/04/photo.jpg → ../../../photo.jpg`)
   - Option C: physical move on explicit confirmation

7. **Log** to `notes/group-by-time-{timestamp}.md`:
   - Granularity used
   - Bucket labels and counts
   - Files that fell back to mtime (flagged for review)
   - Files with no usable timestamp at all (bucketed to `unknown-date/`)

#### Notes

- **Timezone matters.** If EXIF lacks a TZ offset, ask the user which TZ to assume (and record it in the log). Default to the system TZ (Israel IST/IDT here).
- For mixed-source imports (phone + camera + screenshots), timestamps from different devices may drift — flag clips that cluster oddly.
- Never mutate originals. Prefer the CSV manifest for archives with many files.
- Files with no EXIF and no reliable mtime go to `unknown-date/` — don't invent a timestamp.

---

### images-here

**Name.** `images-here`

**What it does.** Flatten images out of nested sub-folders into the current directory.

This photo contains images in nested sub-folders.

Please:

- Move all of them to this level of the filesystem, creating a flat structure  
- Delete all the emptied sub-folders 
- Run a programmatic duplicate check and remove any duplicates

---

### Install GIMP Plugin

**Name.** `install-gimp-plugin`

**What it does.** Install and register a GIMP plugin or extension.

You are a system administration assistant specialized in installing and managing GIMP plugins and extensions on Linux.

#### Your Task

Help the user install GIMP plugins (scripts, plug-ins, and extensions):

1. First, verify GIMP is installed:
   ```bash
   gimp --version
   ```

2. Ask the user:
   - Which plugin/script they want to install (provide popular suggestions)
   - Plugin type (Python-Fu, Script-Fu, binary plugin)
   - Installation preference (Flatpak vs system)

3. Determine correct plugin directories:
   - **System GIMP**: `~/.config/GIMP/2.10/plug-ins/` and `~/.config/GIMP/2.10/scripts/`
   - **Flatpak GIMP**: `~/.var/app/org.gimp.GIMP/config/GIMP/2.10/plug-ins/` and scripts
   - **GIMP 3.x**: Replace `2.10` with appropriate version

4. Install plugin with correct permissions and verify it loads

#### GIMP Plugin Directories

##### System Installation
```bash
# Python/Binary plugins
~/.config/GIMP/2.10/plug-ins/

# Script-Fu scripts (.scm files)
~/.config/GIMP/2.10/scripts/

# Brushes, patterns, gradients
~/.config/GIMP/2.10/brushes/
~/.config/GIMP/2.10/patterns/
~/.config/GIMP/2.10/gradients/
```

##### Flatpak Installation
```bash
~/.var/app/org.gimp.GIMP/config/GIMP/2.10/plug-ins/
~/.var/app/org.gimp.GIMP/config/GIMP/2.10/scripts/
```

#### Popular GIMP Plugins

##### G'MIC (Powerful filters and effects)

**System GIMP:**
```bash
sudo apt install gmic gimp-gmic
```

**Flatpak GIMP:**
```bash
flatpak install flathub org.gimp.GIMP.Plugin.GMIC
```

##### Resynthesizer (Content-aware fill, heal selection)

```bash
sudo apt install gimp-plugin-registry
# Includes resynthesizer and many other useful plugins
```

**Manual installation:**
```bash
# Download from GitHub
git clone https://github.com/bootchk/resynthesizer.git
cd resynthesizer

# Build
sudo apt install build-essential libgimp2.0-dev
./autogen.sh
make
sudo make install
```

##### Liquid Rescale (Content-aware scaling)

```bash
sudo apt install gimp-plugin-registry
```

##### BIMP (Batch Image Manipulation)

```bash
# Download from releases
wget https://github.com/alessandrofrancesconi/gimp-plugin-bimp/releases/download/v2.4/gimp-plugin-bimp-2.4.tar.gz
tar -xzf gimp-plugin-bimp-2.4.tar.gz

# Install dependencies
sudo apt install libgimp2.0-dev libpcre3-dev

# Build and install
cd gimp-plugin-bimp-*
make
make install
```

##### Beautify (Photo enhancement)

```bash
# Download beautify.scm
wget https://raw.githubusercontent.com/hejiann/beautify/master/beautify.scm

# Install
mkdir -p ~/.config/GIMP/2.10/scripts/
cp beautify.scm ~/.config/GIMP/2.10/scripts/
```

##### Fourier Plugin (Frequency domain editing)

```bash
sudo apt install gimp-plugin-registry
# Includes fourier plugin
```

##### Layer via Copy/Cut

```bash
# Download the script
wget http://registry.gimp.org/files/layer-via-copy-cut.scm

# Install
mkdir -p ~/.config/GIMP/2.10/scripts/
cp layer-via-copy-cut.scm ~/.config/GIMP/2.10/scripts/
```

#### Installing Different Plugin Types

##### Script-Fu (.scm files)

```bash
# Download the .scm file
# Copy to scripts directory
mkdir -p ~/.config/GIMP/2.10/scripts/
cp plugin-name.scm ~/.config/GIMP/2.10/scripts/

# For Flatpak:
cp plugin-name.scm ~/.var/app/org.gimp.GIMP/config/GIMP/2.10/scripts/

# Refresh scripts in GIMP: Filters → Script-Fu → Refresh Scripts
```

##### Python-Fu (.py files)

```bash
# Create plugin directory with plugin name
mkdir -p ~/.config/GIMP/2.10/plug-ins/plugin-name/

# Copy Python file
cp plugin-name.py ~/.config/GIMP/2.10/plug-ins/plugin-name/

# Make executable
chmod +x ~/.config/GIMP/2.10/plug-ins/plugin-name/plugin-name.py

# For Flatpak:
mkdir -p ~/.var/app/org.gimp.GIMP/config/GIMP/2.10/plug-ins/plugin-name/
cp plugin-name.py ~/.var/app/org.gimp.GIMP/config/GIMP/2.10/plug-ins/plugin-name/
chmod +x ~/.var/app/org.gimp.GIMP/config/GIMP/2.10/plug-ins/plugin-name/plugin-name.py
```

**Example Python plugin structure:**
```
~/.config/GIMP/2.10/plug-ins/
└── my-plugin/
    ├── my-plugin.py  (executable)
    └── README.md
```

##### Binary Plugins (.so files)

```bash
# Copy to plug-ins directory
mkdir -p ~/.config/GIMP/2.10/plug-ins/plugin-name/
cp plugin.so ~/.config/GIMP/2.10/plug-ins/plugin-name/

# Make executable
chmod +x ~/.config/GIMP/2.10/plug-ins/plugin-name/plugin.so
```

#### Installing from GIMP Plugin Registry

Many plugins can be installed via the package manager:

```bash
# Install the full plugin registry
sudo apt install gimp-plugin-registry

# This includes:
# - Resynthesizer
# - Liquid Rescale
# - Fourier
# - Wavelet Denoise
# - Separate+
# - And many more
```

#### Installing Brushes, Patterns, and Gradients

##### Brushes (.gbr, .gih, .vbr files)

```bash
mkdir -p ~/.config/GIMP/2.10/brushes/
cp *.gbr ~/.config/GIMP/2.10/brushes/

# Refresh in GIMP: Windows → Dockable Dialogs → Brushes → Refresh
```

##### Patterns (.pat files)

```bash
mkdir -p ~/.config/GIMP/2.10/patterns/
cp *.pat ~/.config/GIMP/2.10/patterns/
```

##### Gradients (.ggr files)

```bash
mkdir -p ~/.config/GIMP/2.10/gradients/
cp *.ggr ~/.config/GIMP/2.10/gradients/
```

#### Verify Plugin Installation

1. **Check plugin appears in GIMP:**
   - Restart GIMP
   - Check Filters menu for new entries
   - Check Tools menu if it's a tool plugin

2. **Refresh plugins without restarting:**
   - Filters → Script-Fu → Refresh Scripts (for Script-Fu)
   - Filters → Python-Fu → Console → Browse (for Python-Fu)

3. **Check GIMP error console:**
   - Filters → Python-Fu → Console
   - Look for any error messages

4. **Review GIMP startup messages:**
   ```bash
   gimp --verbose
   ```

#### Building Plugins from Source

General process for compiled plugins:

```bash
# Install build dependencies
sudo apt install build-essential libgimp2.0-dev

# Clone plugin repository
git clone https://github.com/author/plugin-name.git
cd plugin-name

# Build (method varies by plugin)
# Method 1: Autotools
./autogen.sh
./configure
make
sudo make install

# Method 2: Meson
meson build
ninja -C build
sudo ninja -C build install

# Method 3: Simple Makefile
make
sudo make install
```

#### Troubleshooting

##### Plugin not appearing

**Check permissions:**
```bash
chmod +x ~/.config/GIMP/2.10/plug-ins/plugin-name/*.py
chmod +x ~/.config/GIMP/2.10/plug-ins/plugin-name/*.so
```

**Check Python shebang (for Python plugins):**
```python
#!/usr/bin/env python3
```

**Ensure plugin is in its own directory:**
```bash
# Wrong:
~/.config/GIMP/2.10/plug-ins/plugin.py

# Correct:
~/.config/GIMP/2.10/plug-ins/plugin-name/plugin.py
```

##### Missing dependencies

**For Python plugins:**
```bash
# System GIMP uses system Python
pip3 install required-module

# Flatpak GIMP - more complex, may need to use flatpak Python
```

**Check what libraries binary needs:**
```bash
ldd ~/.config/GIMP/2.10/plug-ins/plugin-name/plugin.so
```

##### Flatpak permission issues

```bash
# Grant additional permissions if needed
flatpak override --user --filesystem=~/.config/GIMP org.gimp.GIMP
```

#### GIMP 3.0 Changes

For GIMP 3.0+ (when released):
- Plugin directory: `~/.config/GIMP/3.0/plug-ins/`
- Python 3 required for all Python plugins
- Some API changes may require plugin updates

#### Recommended Plugin Collection

Essential plugins for most users:
1. **G'MIC** - Hundreds of filters and effects
2. **Resynthesizer** - Content-aware fill (like Photoshop)
3. **BIMP** - Batch image manipulation
4. **gimp-plugin-registry** - Collection of useful plugins
5. **Liquid Rescale** - Content-aware scaling
6. **Layer via Copy/Cut** - Photoshop-like layer workflow

#### Uninstalling Plugins

**Remove script:**
```bash
rm ~/.config/GIMP/2.10/scripts/plugin-name.scm
```

**Remove Python/binary plugin:**
```bash
rm -rf ~/.config/GIMP/2.10/plug-ins/plugin-name/
```

**Remove system-installed plugin:**
```bash
sudo apt remove gimp-plugin-name
```

#### Resources

- **GIMP Plugin Registry**: https://www.gimphelp.org/
- **GitHub**: Search for "GIMP plugin"
- **GIMP Forums**: https://www.gimp-forum.net/
- **Package search**: `apt search gimp-plugin`

#### Best Practices

- Install plugins one at a time and test
- Keep backups of working GIMP configurations
- Read plugin documentation for requirements
- Check GIMP version compatibility
- Prefer packaged versions when available
- Use GIMP's built-in plugin manager (if available)
- Test plugins on copy of image first

Help users extend GIMP's capabilities with powerful plugins for advanced image editing.

---

### Organize Images by Aspect Ratio

**Name.** `organize-by-aspect-ratio`

**What it does.** Sort images into aspect-ratio buckets.

Sort images in the current folder (or a user-specified folder) into aspect-ratio buckets.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default flat.

2. **Probe each image** for width × height:
   ```bash
   identify -format "%w %h %i\n" *.jpg *.png *.heic *.webp 2>/dev/null
   # or
   exiftool -s -s -s -ImageWidth -ImageHeight "image.jpg"
   ```

3. **Compute aspect ratio** as `width / height` and bucket with a small tolerance (±2%):
   - `1x1/` — square (0.98–1.02)
   - `4x3/` — landscape 4:3 (≈1.333)
   - `3x2/` — landscape 3:2 (≈1.5)
   - `16x9/` — landscape 16:9 (≈1.778)
   - `3x2-portrait/` — portrait 2:3 (≈0.667)
   - `9x16-portrait/` — portrait 9:16 (≈0.5625)
   - `panorama/` — ratio > 2.5 or < 0.4
   - `other/` — doesn't match any of the above

4. **Preview before acting** — table of image → bucket, counts per bucket. Wait for user confirmation.

5. **Prefer symlinks or CSV manifest over physical moves**:
   - Option A: symlinked sub-folders
   - Option B: `metadata/aspect-ratio-buckets.csv`
   - Option C: physical move on explicit confirmation

6. **Log** to `notes/organize-by-aspect-ratio-{timestamp}.md` with bucket counts and any probe failures.

#### Notes

- The ±2% tolerance matters — phone photos often land slightly off nominal ratios after crop.
- Panorama threshold (>2.5:1) is conservative; drop to 2.0:1 if the user is sorting a stitched-panorama archive.
- Respect EXIF Orientation when computing w/h — a portrait JPEG often stores landscape pixels with orientation=6. Use `identify` with auto-orient or read the `Orientation` tag explicitly.

---

### Organize Images by File Format

**Name.** `organize-by-format`

**What it does.** Sort images into sub-folders by file format.

Sort images into format-based sub-folders.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default flat.

2. **Classify each file** by extension (case-insensitive), with `file` / `exiftool` as a fallback for misnamed files or files missing an extension:
   - `JPEG/` — `.jpg`, `.jpeg`
   - `PNG/` — `.png`
   - `HEIC/` — `.heic`, `.heif`
   - `WebP/` — `.webp`
   - `RAW/` — `.nef` (Nikon), `.cr2` / `.cr3` (Canon), `.arw` (Sony), `.dng` (Adobe), `.raf` (Fuji), `.orf` (Olympus), `.rw2` (Panasonic)
   - `TIFF/` — `.tif`, `.tiff`
   - `GIF/` — `.gif`
   - `BMP/` — `.bmp`
   - `SVG/` — `.svg`
   - `other/` — anything that doesn't match, including files missing an extension and unknown formats

   ```bash
   # Fallback when extension is missing or misleading:
   exiftool -s -s -s -FileType "image"
   # or
   file --mime-type "image"
   ```

3. **Preview before acting** — table of format → count, plus a sample filename per bucket. Wait for confirmation.

4. **Prefer symlinks or CSV manifest over physical moves**:
   - Option A: symlinked sub-folders
   - Option B: `metadata/format-buckets.csv`
   - Option C: physical move on explicit confirmation

5. **Log** to `notes/organize-by-format-{timestamp}.md` with bucket counts and any files flagged as format/extension mismatch.

#### Notes

- Flag extension/format mismatch explicitly (e.g. a `.jpg` that `exiftool` reports as PNG) — these are often the interesting files in an import.
- RAW sidecars (`.xmp`) should be kept adjacent to their RAW — when moving/symlinking, pair them.
- HEIC support requires `libheif` to be present if further commands read the image; the bucketing itself is extension-based and doesn't need it.

---

### Organize Images by Orientation

**Name.** `organize-by-orientation`

**What it does.** Sort images into portrait, landscape, and square buckets.

Sort images into `portrait/`, `landscape/`, and `square/` buckets.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default flat.

2. **Probe each image** for width × height, respecting EXIF Orientation (so a rotated-in-metadata portrait JPEG isn't categorized incorrectly):
   ```bash
   exiftool -s -s -s -ImageWidth -ImageHeight -Orientation "image.jpg"
   # or, auto-oriented:
   identify -auto-orient -format "%w %h %i\n" "image.jpg"
   ```

3. **Bucket** by the *displayed* dimensions:
   - `portrait/` — height > width
   - `landscape/` — width > height
   - `square/` — width == height (±1 px tolerance for off-by-one)

4. **Preview before acting** — table of image → bucket, counts per bucket. Wait for confirmation.

5. **Prefer symlinks or CSV manifest over physical moves**:
   - Option A: symlinked sub-folders
   - Option B: `metadata/orientation-buckets.csv`
   - Option C: physical move on explicit confirmation

6. **Log** to `notes/organize-by-orientation-{timestamp}.md` with bucket counts.

#### Notes

- **Always honour EXIF Orientation.** Raw pixel dimensions lie for rotated phone photos — without `-auto-orient` or reading the Orientation tag, portrait shots land in `landscape/`.
- Skip non-image files silently; list them in the log.

---

### Organize Images by Resolution

**Name.** `organize-by-resolution`

**What it does.** Sort images into sub-folders by resolution.

Sort images in the current folder (or a user-specified folder) into resolution-based sub-folders.

#### Task

1. **Ask which folder to operate on** — default is the current working directory. Confirm recursion: descend into sub-folders, or flat only? Default flat.

2. **Probe each image** for pixel dimensions. Prefer `identify` (ImageMagick) for speed; fall back to `exiftool` for formats it mishandles (HEIC, some RAW):
   ```bash
   identify -format "%w %h %i\n" "*.jpg" "*.png" "*.heic" "*.webp" 2>/dev/null
   # or
   exiftool -s -s -s -ImageWidth -ImageHeight "image.jpg"
   ```

3. **Bucket images** by the longest edge (so portrait and landscape shots land in the same tier):
   - `8K/` — longest edge ≥ 7680
   - `4K/` — longest edge ≥ 3840 and < 7680
   - `2K/` — longest edge ≥ 2560 and < 3840
   - `1080p-class/` — longest edge ≥ 1920 and < 2560
   - `720p-class/` — longest edge ≥ 1280 and < 1920
   - `SD/` — longest edge ≥ 640 and < 1280
   - `tiny/` — longest edge < 640
   - `other/` — probe failures, non-image files

4. **Preview before acting** — print a table of image → bucket with counts per bucket. Do not move anything until the user confirms.

5. **Prefer symlinks or a CSV manifest over physical moves** unless the user asks otherwise:
   - Option A: symlinked sub-folders (`4K/photo.jpg → ../photo.jpg`)
   - Option B: `metadata/resolution-buckets.csv` mapping file → bucket
   - Option C: physical move (only on explicit confirmation)

6. **Log** to `notes/organize-by-resolution-{timestamp}.md` with bucket counts, method chosen (symlink / manifest / move), and any probe failures.

#### Notes

- Check `identify` (from ImageMagick) is installed before using it; otherwise fall back to `exiftool`.
- Skip non-image files silently, but list them in the log.
- For RAW formats (NEF, CR2, ARW, DNG), `exiftool` is more reliable than `identify`.

---

### Scrub Small Images

**Name.** `scrub-small-images`

**What it does.** Move thumbnails, icons, and other sub-threshold images out of a library.

Identify and move images below a configurable size threshold — typically thumbnails, icons, favicons, chat-app previews, and web-sidebar gunk that clutters a library import.

#### Task

1. **Confirm threshold** — default **longest edge < 500 px**. Ask if the user wants a different cutoff (200 px for aggressive scrub, 1000 px to cull everything non-print-worthy).

2. **Ask which folder to operate on** — default is the current working directory. Confirm recursion; default recursive (small images usually hide in sub-folders).

3. **Probe every image** for dimensions (respecting EXIF Orientation so portrait phone shots aren't categorized incorrectly):
   ```bash
   identify -auto-orient -format "%w %h %i\n" *.jpg *.png *.heic *.webp 2>/dev/null
   # or
   exiftool -s -s -s -ImageWidth -ImageHeight "image.jpg"
   ```

4. **Build a candidate list** — images where `max(width, height) < threshold`. Show the user a table: filename, dimensions, format, size on disk.

5. **Wait for confirmation before moving anything.** This feels destructive — never auto-execute.

6. **Move confirmed files** to `small/` (a sibling bucket in the target folder). Preserve relative sub-paths if operating recursively. On filename collision, append a short suffix. **Do not delete.**

7. **Log** to `notes/scrub-small-images-{timestamp}.md`:
   - Threshold used
   - Files moved / files kept
   - Full list of moved files with dimensions

8. **Offer a follow-up** — if many images are borderline (e.g. 480–520 px at a 500 px cutoff), ask whether to review those manually before finalizing.

#### Notes

- Use `max(width, height)` (longest edge) rather than total pixel count — a 100×1000 column banner is more useful than a 300×300 icon even though they're the same pixel count.
- Skip non-image files silently; list them in the log.
- `small/` is the disposal bucket — the user decides when to empty it.

---

### separate-photos-and-video

**Name.** `separate-photos-and-video`

**What it does.** Split a mixed folder into photos and videos sub-folders.

This folder contains a mixture of photos and video

Create sub-folders /photos and /videos

Move photos into photos and videos into videos

---

### sort-media

**Name.** `sort-media`

**What it does.** Sort a mixed media folder into type-based sub-folders.

This folder contains a mixture of media items.

These may be (for example) photos and videos.

If the folder contains mixed photos and videos, firstly create parent folders for each media type.

If this folder contains only photos - or within the newly created photos folder:

- Move portrait and landscape photos into separate sub-folders 

If this folder contains only videos - or within the newly created videos folder:

- Move 1080P and 4K clips into separate sub-folders 

Within the resolution sub-folders, move portrait and landscape clips into separate sub-folders.

---
