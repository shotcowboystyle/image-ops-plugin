[![Claude Code View Marketplace](https://img.shields.io/badge/Claude%20Code-View%20Marketplace-blue?style=for-the-badge&logo=github)](https://github.com/shotcowboystyle/ai-plugins)

## Image Ops Plugin

**Version:** 1.1.0

A Claude Code plugin for image editing, batch operations, format conversion, and filesystem organization of image libraries.

19 slash commands for organization and bulk editing, plus 28 skills Claude invokes on its own when a request matches.

## Installation

```bash
/plugin marketplace add https://github.com/shotcowboystyle/ai-plugins
/plugin install image-ops@shotcowboystyle
```

## Portable by construction

This plugin is generated from a runtime-neutral source of truth in `.agent/`:

```
.agent/agent.md            the agent definition — purpose, constraints, conventions
.agent/manifest.json       plugin metadata, per-skill and per-command metadata
.agent/skills/<name>.md    one skill body each, with no runtime-specific syntax
.agent/commands/<name>.md  one command body each, for commands that carry their own prompt
```

`AGENTS.md` is generated from those files and can be used verbatim by any agent runtime.
The Claude Code layer — `skills/`, `commands/`, and `.claude-plugin/plugin.json` — is
generated too, and must not be hand-edited.

```bash
python3 scripts/build.py           # regenerate after editing .agent/
python3 scripts/build.py --check   # fail if anything on disk is stale
```


<!-- BEGIN GENERATED: components -->

## Commands

- `/image-ops:apply-filters` — Apply artistic or corrective filters to images with ImageMagick.
- `/image-ops:batch-resize` — Resize a whole folder of images to target dimensions or a scale factor.
- `/image-ops:bg-removal` — Remove the background from every image in a folder.
- `/image-ops:compress-images` — Reduce image file size while holding quality at an acceptable level.
- `/image-ops:convert-to-webp` — Convert every image in the current directory to WebP.
- `/image-ops:crop-images` — Crop images to fixed dimensions, an aspect ratio, or a custom area.
- `/image-ops:dedupe` — Find and remove duplicate and near-duplicate images.
- `/image-ops:group-by-camera` — Cluster images into folders by EXIF camera make and model.
- `/image-ops:group-by-time` — Cluster images into year and month folders by EXIF capture time.
- `/image-ops:images-here` — Flatten images out of nested sub-folders into the current directory.
- `/image-ops:install-gimp-plugin` — Install and register a GIMP plugin or extension.
- `/image-ops:organize-by-aspect-ratio` — Sort images into aspect-ratio buckets.
- `/image-ops:organize-by-format` — Sort images into sub-folders by file format.
- `/image-ops:organize-by-orientation` — Sort images into portrait, landscape, and square buckets.
- `/image-ops:organize-by-resolution` — Sort images into sub-folders by resolution.
- `/image-ops:scrub-small-images` — Move thumbnails, icons, and other sub-threshold images out of a library.
- `/image-ops:separate-photos-and-video` — Split a mixed folder into photos and videos sub-folders.
- `/image-ops:setup-workspace` — Register or create the image production workspace folder.
- `/image-ops:sort-media` — Sort a mixed media folder into type-based sub-folders.

## Skills

- **auto-deskew** — Use when the user wants to automatically straighten a tilted image — scanned documents, phone-captured pages, photographed receipts, or slightly off-axis photos. Detects the dominant skew angle and rotates the image to vertical/horizontal, optionally cropping the resulting transparent triangles. Uses ImageMagick `-deskew` for documents and a Hough-line fallback (via Python + OpenCV) for photographs.
- **auto-tone** — Use when the user wants automatic tonal correction — fix flat/washed-out / underexposed / low-contrast images by stretching levels, normalising contrast, and gamma-correcting to a neutral midtone. Implements auto-level (per-channel histogram stretch), auto-gamma (midtone correction), and a combined "punch" mode via ImageMagick. Operates on JPEG/PNG/TIFF/WebP.
- **auto-white-balance** — Use when the user wants to automatically correct the white balance of an image (or batch) — neutralise colour casts from indoor lighting, mixed light, underwater shots, scans, or uncalibrated cameras. Implements gray-world (default), white-patch (per-channel auto-level), and a combined mode via ImageMagick. Operates on JPEG/PNG/TIFF/WebP; for RAW use `darktable-cli` instead.
- **batch-set-copyright** — Use when the user wants to batch-stamp copyright, artist, and rights information across every image in a directory — a photo library heading for distribution or archival. Convenience wrapper around exiftool. For arbitrary tags (description, keywords, GPS) on individual files, use `set-metadata` instead.
- **convert-to-avif** — Use when the user wants AVIF output — modern web format with ~30% better compression than WebP at the same visual quality, and ~50% better than JPEG. Wraps `avifenc`. Companion to the `/convert-to-webp` command. Best target for new web work; check browser support if delivering to ancient clients.
- **fast-resize** — Use when the user wants to resize a large batch of images (>500 files) where ImageMagick throughput is the bottleneck. Wraps libvips for 5–10× faster batch resize at lower memory. Falls back to ImageMagick if `vips` isn't installed. Same outputs as the `/batch-resize` command — different engine.
- **fast-thumbnail** — Use when the user wants to generate thumbnails at scale — index views, contact sheets, web previews, or just shrinking a library to manageable sizes. Wraps `vipsthumbnail` for sub-second-per-image generation, much faster than ImageMagick on large batches.
- **from-jxl** — Use when the user wants to decode JPEG XL images (.jxl) back to PNG or JPEG — for compatibility with tools that cannot read JXL, for display, or for further editing. Also recovers the byte-exact original JPEG from a lossless transcode. Reverse of `to-jxl`.
- **images-to-pdf** — Use when the user wants to combine a folder or list of images into a single PDF — typically on a standard paper size (A4 default) for digital printers, document-style sharing, or proof sheets. Modes - one-per-page (default; auto-orient portrait/landscape per image), multi-up (2/4/6/9 per page), as-is (native pixel size). Prefers `img2pdf` for lossless JPEG embedding; falls back to ImageMagick for non-JPEG sources or when img2pdf is missing.
- **install-deps** — Provision the plugin's tools — system binaries via the host package manager, Python tools into a plugin-owned uv venv at <data-dir>/venv/. Idempotent doctor — run before any command reports a missing dep. Never touches system Python or fights PEP 668.
- **nano-tech-diagrams** — Create and edit tech diagrams via a nano-tech-diagrams MCP server (Nano Banana 2 through Fal AI). Text-to-image, image-to-image, whiteboard cleanup, and 28+ style presets. Requires an externally configured MCP server — this plugin does not ship one.
- **new-project** — Create a new image project inside the user's registered image workspace. Use when the user says "new image project", "create an image project called X", "scaffold a new image set", or similar. Creates a project subfolder with source, working, exports, references layout and an optional git init.
- **new-workflow** — Scaffold a multi-touchpoint image workflow inside the registered image workspace — a structured pipeline with explicit human review gates and optional cloud-AI generation/edit steps (Fal nano-banana via MCP). Use when the user says "new image workflow", "scaffold a workflow", "set up an image pipeline", "iterative image project", or describes a job that needs multiple rounds of generation → review → revision → export.
- **open-workspace** — Open the user's registered image workspace folder. Use when the user says "open my image workspace", "take me to my image workspace", or similar. Reads the path from workspace.json and opens a terminal (or Finder/file manager) there.
- **optimize-jpeg** — Use when the user wants to shrink JPEG files — losslessly with `jpegoptim` (~5–15% reduction, no re-encode) or with re-compression via `mozjpeg` (~10–15% better than libjpeg-turbo at the same visual quality). Web-prep workhorse for photo libraries.
- **optimize-png** — Use when the user wants to shrink PNG files in a batch — losslessly with `oxipng` (typical 20–40% reduction, byte-identical decode) or aggressively with `pngquant` (lossy palette quantisation, 60–80% reduction with near-imperceptible quality loss for web use). Web-prep workhorse.
- **pdf-extract-embedded-images** — Use when the user wants to recover the images embedded in a PDF at their native resolution, without rasterizing the pages — a PDF that is essentially a wrapper around photos. For rendering whole pages to images instead, use `pdf-to-images`.
- **pdf-to-images** — Use when the user wants to rasterize PDF pages into numbered image files (JPEG, PNG, or TIFF) at a chosen resolution (DPI) — one image per page, with optional page-range selection. For recovering the photos embedded in a PDF at native resolution instead, use `pdf-extract-embedded-images`.
- **read-metadata** — Use when the user wants to inspect EXIF, IPTC, XMP, or GPS metadata on images without modifying anything — read out as structured JSON or a human-readable summary. Read-only counterpart to `scrub-metadata` (removes) and `set-metadata` (writes).
- **scrub-metadata** — Strip EXIF / IPTC / XMP metadata from images using exiftool. Use when the user wants to remove identifying metadata (GPS, camera, timestamps, thumbnails) from a single image, a folder, or a recursive tree before sharing or publishing. Supports preview, backup-first, whitelist of fields to keep (e.g. Orientation), and recursive operation. Logs each run to notes/.
- **set-metadata** — Use when the user wants to write arbitrary EXIF, IPTC, or XMP tags to images — artist, copyright, description, keywords, GPS coordinates, capture date, lens or camera model. For stamping only copyright/artist/rights uniformly across a whole directory, `batch-set-copyright` is the narrower wrapper.
- **svg-to-raster** — Use when the user wants to rasterize SVG files — convert SVG to PNG, PDF, or PostScript at a chosen resolution. Wraps CairoSVG (Python, in the plugin venv). Single file or batch. Companion to `vectorize` (other direction).
- **to-jxl** — Use when the user wants to encode images of any raster format (PNG, GIF, WebP, TIFF, JPEG) to JPEG XL (.jxl) with a chosen quality preset — lossless, visually lossless, or web. General-purpose JXL encoder. For a JPEG-only archive where the goal is a byte-exact-recoverable lossless transcode with a savings report, use `transcode-jpeg-to-jxl-lossless` instead.
- **transcode-jpeg-to-jxl-lossless** — Use when the user wants to archive a JPEG-only library as JPEG XL — losslessly transcodes JPEG to .jxl, preserving the original bitstream for byte-exact recovery, with a dry-run preview and a byte-savings report (~15–25% reduction). Prefer this over the general-purpose `to-jxl` skill whenever the sources are exclusively JPEG and archival is the goal.
- **upscale-image** — Use when the user wants to AI-upscale images 2× / 3× / 4× — recovering detail in low-res sources, prepping small photos for print, enlarging AI-generated images. Wraps `upscayl-bin` (the CLI bundled with Upscayl) with its model library; falls back to standalone `realesrgan-ncnn-vulkan` if Upscayl isn't installed. GPU-accelerated via Vulkan.
- **vectorize** — Use when the user wants to trace a raster image (PNG/JPEG) into an SVG vector — useful for logos, line art, diagrams, and stylized illustrations. Wraps `vtracer` (Rust-backed, via Python wheel in the plugin venv). Companion to `svg-to-raster` (other direction).
- **web-ready** — Use when the user wants to take a folder of images (any mix of HEIC, RAW, PNG, JPEG, TIFF, WebP) and produce a web-ready set — EXIF stripped, resized to a sensible max dimension, encoded in modern formats (AVIF + WebP, with JPEG fallback), and optimized for size. End-to-end orchestrator over the single-purpose skills in this plugin.
- **workspace-setup** — Register or create the user's image operations workspace — a folder on disk where they keep image projects. Use on first run, or when the user says "set up my image workspace", "register my image workspace", "change my image workspace path", or similar. Persists the path so other skills (open-workspace, new-project) can reference it.

<!-- END GENERATED: components -->

## Dependencies

- **ImageMagick** (`magick`, `identify`) — dimension probing and most pixel work
- **exiftool** (`libimage-exiftool-perl`) — metadata read/write/scrub and timestamp extraction
- **Python 3 + `imagehash` + `Pillow`** (optional) — perceptual deduplication
- **fdupes** (optional) — fast exact-duplicate detection
- **libvips** (optional, recommended >500 images) — `fast-resize`, `fast-thumbnail`
- **poppler-utils** (optional) — `pdf-to-images`, `pdf-extract-embedded-images`
- **libjxl-tools**, **libavif**, **oxipng**, **pngquant**, **jpegoptim**, **mozjpeg** (optional) — the compression and conversion skills
- **darktable-cli** (optional) — RAW ingestion in `web-ready`

Run the `install-deps` skill rather than installing these by hand — it detects the host package manager and provisions the plugin-owned venv without touching system Python.

## Conventions

All organization commands:

- Default to the current working directory, and ask before operating recursively.
- Preview the plan before touching files.
- Prefer symlinks or CSV manifests over physical moves for large batches.
- Log every run to `notes/{command-name}-{timestamp}.md`.
- Never delete — the disposal bucket is `archive/` or `small/`, and the user decides when to empty it.

## Author

**Curtis Blanton**
- Website: [shotcowboystyle.com](https://shotcowboystyle.com)
- Email: public@shotcowboystyle.com
- GitHub: [@shotcowboystyle](https://github.com/shotcowboystyle)

## License

MIT.
