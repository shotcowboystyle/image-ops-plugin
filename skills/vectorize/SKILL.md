---
name: vectorize
description: Use when the user wants to trace a raster image (PNG/JPEG) into an SVG vector — useful for logos, line art, diagrams, and stylized illustrations. Wraps `vtracer` (Rust-backed, via Python wheel in the plugin venv). Companion to `svg-to-raster` (other direction). Triggers - "vectorize this logo", "convert this PNG to SVG", "trace this line art".
disable-model-invocation: false
allowed-tools: Bash(command *), Bash(test *), Bash(find *), Bash(grep *), Bash(mkdir *), Bash(rm *), Bash(wc *), Read, Write
---

# Vectorize

Convert raster images to SVG via [vtracer](https://github.com/visioncortex/vtracer). vtracer is a color-clustering tracer — much better than `potrace` for full-color images, comparable for B/W line art. Installed as a Python wheel in the plugin venv (bundled Rust binary, no `cargo` needed at install time).

## When to use

- Recover an editable vector logo from a raster (PNG/JPEG).
- Convert a flat illustration / icon / diagram into SVG for crisp scaling.
- Stylize a photo into a flat-color vector (large `--filter-speckle` + low `--color-precision`).
- Pre-step before `svg-to-raster` if you want to upscale a small raster losslessly.

Do **not** use this skill when:
- Source is a complex photograph and you want photo-realism — vector tracing always loses gradients/texture; use `upscale-image` for raster upscaling instead.
- You need OCR'd text inside the SVG — vtracer traces strokes, not text. Use a separate OCR step.
- Input is already SVG — no-op.

## Inputs

1. **Input** — image file or directory. Required.
2. **Output dir** — default: `<input-dir>/svg/`. Never overwrites originals.
3. **Mode** — `color` (default, multi-color with clustering) or `binary` (B/W line art, faster, smaller output).
4. **Color precision** — `1..8`, default `6`. Lower = fewer colors = smaller / more abstract SVG.
5. **Layer difference** — `0..255`, default `16`. Larger = fewer layers, simpler output.
6. **Filter speckle** — pixels, default `4`. Discards regions smaller than N pixels — raise to de-noise.
7. **Path simplification** — `corner threshold` (default `60` deg), `length threshold` (default `4.0`), `splice threshold` (default `45` deg). Most users won't tune these; expose only if asked.
8. **Recursive** — `--recursive` for directory descent.

## Procedure

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

## Output

- SVG files at `<output-dir>/`.
- Summary:
  - Files processed / failed, with the failed paths from `$failed_log`.
  - Per-file: input pixels × → SVG path count (heuristic: `grep -c '<path' <file>`), file size delta.
  - Tuning suggestions if path count is suspiciously high (likely too noisy — raise `filter_speckle`) or low (likely over-simplified — drop `layer_difference`).

## Notes

- vtracer is MIT — free to bundle and use.
- For B/W technical drawings / scanned line art, `binary` mode is dramatically faster and produces cleaner output than `color`.
- Common preset suggestions:
  - **Logo / icon (clean source):** `color, color_precision=6, filter_speckle=4, layer_difference=16`. Defaults are tuned for this.
  - **Photo → flat illustration:** `color, color_precision=3, filter_speckle=20, layer_difference=32`. Aggressive simplification, painterly look.
  - **Line drawing / scan:** `binary, filter_speckle=10`. Smallest output.
- If vtracer's quality isn't enough for a specific case, fall back to Inkscape's bitmap trace or `potrace` (B/W only). vtracer is the right default for everything else.
- vtracer ships a CLI binary too (`vtracer-cli`) — the Python wheel is preferred here so the venv is self-contained.
