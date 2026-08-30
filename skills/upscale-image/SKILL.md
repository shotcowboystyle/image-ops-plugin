---
name: upscale-image
description: Use when the user wants to AI-upscale images 2× / 3× / 4× — recovering detail in low-res sources, prepping small photos for print, enlarging AI-generated images. Wraps `upscayl-bin` (the CLI bundled with Upscayl) with its model library; falls back to standalone `realesrgan-ncnn-vulkan` if Upscayl isn't installed. GPU-accelerated via Vulkan. Triggers - "upscale this image 4x", "enlarge these photos for print", "this image is too low-res, can you fix it".
disable-model-invocation: false
allowed-tools: Bash(which *), Bash(command *), Bash(test *), Bash(upscayl-bin *), Bash(realesrgan-ncnn-vulkan *), Bash(vipsthumbnail *), Bash(vipsheader *), Bash(magick *), Bash(identify *), Bash(cjpeg *), Bash(mv *), Bash(rm *), Bash(mkdir *), Bash(find *), Read, Write
---

# Upscale Image (Upscayl)

AI upscaling via `upscayl-bin` — the CLI shipped with the Upscayl GUI. Same Vulkan-accelerated `realesrgan-ncnn-vulkan` engine as standalone, but with Upscayl's curated model selection bundled.

## When to use

- Low-res source needs to be enlarged for print or display.
- AI-generated image at 1024px wants 4096px output without re-prompting.
- Old photos / screenshots need detail recovery.

Do **not** use this skill when:
- The source is already large enough — upscaling rarely improves a 4K-native image.
- The user wants traditional bicubic / lanczos upscaling — `fast-resize` is the right tool (much faster, no AI).
- The image is text/document-heavy — upscalers can hallucinate glyph detail; consider `tesseract` re-OCR + re-typeset instead.

## Inputs

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

## Procedure

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

## Output

- Upscaled images at `<output-dir>/`.
- Summary:
  - Files processed / failed, the failure list read from `$failed_log`, and the reason per entry where the binary gave one.
  - Per-file: input dimensions → output dimensions, model used, elapsed seconds.
  - Total elapsed.
  - GPU device that was used (from upscayl-bin's stderr).

## Notes

- Upscayl's `upscayl-standard-4x` produces visibly better results than vanilla `realesrgan-x4plus` on most photos — keep the default unless the user has a reason.
- Anime/illustration content: switch to `realesrgan-x4plus-anime` or one of the anime-specific Upscayl variants. Photo models smear line art.
- Compute time: ~5–20s per 1080p input on a mid-range GPU; 1–3 minutes per image on CPU. Batch a folder overnight for CPU runs.
- Output format default is PNG because JPEG re-encoding immediately after upscale undoes some of the perceptual gain. JPEG only when the user explicitly wants smaller files.
- Combining with other skills:
  - `web-ready` after upscale → use the `gallery` profile to ship the upscaled output to the web at sensible quality.
  - `images-to-pdf` after upscale → enlarge then print at higher DPI.
- This skill does not auto-install Upscayl or download models. The user owns that step. Models are typically several hundred MB total.
