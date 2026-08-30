[![Claude Code View Marketplace](https://img.shields.io/badge/Claude%20Code-View%20Marketplace-blue?style=for-the-badge&logo=github)](https://github.com/shotcowboystyle/ai-plugins)

## Image Ops Plugin

**Version:** 1.0.0

A Claude Code plugin for image editing, batch operations, format conversion, and filesystem organization of image libraries.

19 slash commands for organization and bulk editing, plus 28 skills Claude invokes on its own when a request matches.

## Installation

```bash
/plugin marketplace add https://github.com/shotcowboystyle/ai-plugins
/plugin install image-ops@shotcowboystyle
```

## Commands

### Editing

- `/image-ops:apply-filters` — apply filters (blur, sharpen, color adjustments) across a batch
- `/image-ops:bg-removal` — remove image backgrounds
- `/image-ops:crop-images` — batch-crop to aspect ratio or fixed dimensions
- `/image-ops:batch-resize` — resize a batch to target dimensions
- `/image-ops:compress-images` — lossy/lossless compression

### Conversion

- `/image-ops:convert-to-webp` — convert JPEG/PNG to WebP
- `/image-ops:separate-photos-and-video` — split mixed media imports

### Organization

- `/image-ops:organize-by-resolution` — bucket by pixel dimensions (8K / 4K / 2K / 1080p / 720p / SD / tiny)
- `/image-ops:organize-by-aspect-ratio` — bucket by ratio (1:1, 4:3, 3:2, 16:9, portrait variants, panorama)
- `/image-ops:organize-by-orientation` — portrait / landscape / square
- `/image-ops:organize-by-format` — JPEG / PNG / HEIC / WebP / RAW / other
- `/image-ops:group-by-time` — cluster by EXIF capture time into year/month/day
- `/image-ops:group-by-camera` — cluster by EXIF Make + Model
- `/image-ops:dedupe` — exact and perceptual duplicate detection
- `/image-ops:scrub-small-images` — move images below a size threshold to `small/`
- `/image-ops:sort-media` — general-purpose media sort
- `/image-ops:images-here` — quick inventory of images in the current folder

### Utilities

- `/image-ops:setup-workspace` — register or create the image workspace folder (wraps the `workspace-setup` skill)
- `/image-ops:install-gimp-plugin` — install a GIMP plugin system-wide

## Skills

All 28 skills live under `skills/<name>/SKILL.md`.

### Setup

- **install-deps** — provision system binaries (ImageMagick, exiftool, optional libvips/heif/optimizers/AVIF/JXL/Real-ESRGAN/darktable) and a plugin-owned uv venv with `Pillow` + `imagehash`. Idempotent doctor.
- **workspace-setup** — register or create the image workspace folder, persisted so the other workspace skills can find it.
- **open-workspace** — open the registered workspace in a terminal or file manager.
- **new-project** — scaffold a project folder (`source/`, `working/`, `exports/`, `references/`, `thumbnails/`) inside the workspace.
- **new-workflow** — scaffold a multi-touchpoint workflow: brief → references → generation → review → revision (N rounds) → export, with explicit human review gates and an optional cloud-AI driver.

### Resize and thumbnails

- **fast-resize** — batch resize via libvips (5–10× ImageMagick on large batches). Falls back to ImageMagick if `vips` isn't installed.
- **fast-thumbnail** — high-throughput thumbnail generation via `vipsthumbnail`, with shrink-on-load JPEG decoding for sub-second-per-image runs.
- **upscale-image** — AI upscale 2× / 3× / 4× via `upscayl-bin` (Upscayl's bundled CLI) or `realesrgan-ncnn-vulkan` fallback. GPU-accelerated, model-selectable (photo / anime / lite).

### Compression and conversion

- **optimize-png** — shrink PNGs losslessly (`oxipng`, 20–40% typical) or lossily (`pngquant`, 60–80%).
- **optimize-jpeg** — lossless JPEG squeeze (`jpegoptim`) or recompress with better quantisation (`mozjpeg`, ~10–15% smaller).
- **convert-to-avif** — modern web format via `avifenc` (~30% better than WebP at same quality).
- **to-jxl** — general-purpose JPEG XL encoder with lossless / visually-lossless / web presets.
- **from-jxl** — decode `.jxl` back to PNG or JPEG, including byte-exact recovery of a losslessly transcoded original.
- **transcode-jpeg-to-jxl-lossless** — JPEG-only archival transcode with a dry-run preview and byte-savings report.
- **web-ready** — orchestrator: ingest anything (HEIC, RAW, JPEG, PNG, TIFF) → strip EXIF → resize → encode AVIF + WebP + JPEG fallback → optimize. Profiles for blog / gallery / thumbnail / archival-web.

### Correction

- **auto-white-balance** — white balance correction (gray-world / white-patch / combined) via ImageMagick. Single image or batch, optional luminance preservation, blend strength.
- **auto-tone** — tonal correction (auto-level / auto-gamma / punch) via ImageMagick. Hue-preserving by default, blend-strength knob, batch-aware.
- **auto-deskew** — skew correction. ImageMagick `-deskew` for documents, OpenCV Hough-line fallback for photos. Inscribed-rectangle crop, max-angle guard.

### Metadata

- **read-metadata** — inspect EXIF / IPTC / XMP / GPS as structured JSON or a readable summary. Read-only.
- **set-metadata** — write arbitrary metadata tags (artist, copyright, description, keywords, GPS, capture date).
- **batch-set-copyright** — stamp copyright / artist / rights uniformly across a directory.
- **scrub-metadata** — strip EXIF / IPTC / XMP using `exiftool`. Preview, backup-first, recursive, whitelist of fields to preserve (e.g. Orientation), per-run logging.

### PDF and vector

- **images-to-pdf** — combine images into a PDF on a standard paper size (A4 default). Modes: one-per-page (auto-orient), multi-up (2/4/6/9 per page), as-is. Lossless JPEG embedding via `img2pdf`, ImageMagick fallback.
- **pdf-to-images** — rasterize PDF pages to numbered JPEG / PNG / TIFF at a chosen DPI.
- **pdf-extract-embedded-images** — recover embedded images from a PDF at native resolution, without rasterizing.
- **svg-to-raster** — rasterize SVG to PNG / PDF / PS via [CairoSVG](https://github.com/Kozea/CairoSVG) (in the plugin venv). Scale, explicit dimensions, DPI, transparent or solid background.
- **vectorize** — trace raster images (PNG / JPEG) to SVG via [vtracer](https://github.com/visioncortex/vtracer) (in the plugin venv). Color or binary mode, tunable speckle filter and layer difference.

### Requires external setup

- **nano-tech-diagrams** — create and edit tech diagrams through a nano-tech-diagrams MCP server (Nano Banana 2 via Fal AI). **This plugin ships no MCP server** — the skill documents what the user must configure themselves, and does nothing without it.

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
