# Rasterize PDF to Images

Convert PDF pages to raster images (JPEG, PNG, or TIFF) using `pdftoppm`. Each page becomes a numbered image file. Different from `pdf-extract-embedded-images` — this rasterizes the entire page content.

## When to use

- Converting a scanned PDF or document PDF to standalone images for archival, editing, or distribution.
- Extracting pages as thumbnails or preview images at lower DPI.
- Creating image sequences from a multi-page PDF without needing OCR or text extraction.

## Inputs to gather

- **Input PDF file** — path to the PDF. Required.
- **DPI (resolution)** — dots per inch. Default: 300 (suitable for archival and print). Ask if the user needs lower DPI for faster processing or smaller file size (e.g., 150 for thumbnails, 600 for high-quality scans).
- **Output format** — `jpeg`, `png`, or `tiff`. Default: `jpeg` (good balance of size and quality). PNG for lossless, TIFF for archival.
- **Page range** (optional) — ask if they want all pages or a subset. If a subset, capture start page and end page (e.g., pages 5–10).
- **Output directory** — optional. Default: current directory.

## Procedure

### 1. Check tooling

```bash
command -v pdftoppm >/dev/null || {
  echo "pdftoppm not installed — see the install-deps skill (poppler-utils)" >&2
  exit 1
}
```

### 2. Validate PDF

```bash
file "$input" 
pdfinfo "$input" || { echo "not a readable PDF: $input" >&2; exit 1; }
```

If invalid, abort. Print the page count for user awareness — it also determines the filename padding width (see step 5).

### 3. Build command

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

### 4. Execute

```bash
pdftoppm -r "$dpi" "-$format" $page_flags "$input" "$output_prefix" \
  || { echo "pdftoppm failed on $input" >&2; exit 1; }
```

Show progress and warn if the PDF is large (many pages or high DPI — processing may take a minute or more).

### 5. Report

After conversion:

- Count of images created.
- Output directory and filename pattern. `pdftoppm` pads the page number to the width of the total page count — a 9-page PDF gives `output-1.jpg`, a 40-page PDF gives `output-01.jpg`, a 500-page PDF gives `output-001.jpg`. Read the actual names off disk rather than predicting them.
- File sizes and total space used.
- If a page range was used, note which pages were extracted.

## Output / side effects

- Numbered image files created. The zero-padding width is derived from the document's total page count (not a fixed width), and the separator is a hyphen by default.
- Original PDF unchanged.

## Notes

- **Rasterization vs. embedding:** `pdftoppm` rasterizes the entire page at the specified DPI. This is lossy compared to the original PDF vector content, but suitable for archival, sharing, or thumbnail workflows. See `pdf-extract-embedded-images` for extracting embedded photos without rasterization.
- **DPI guidance:** 300 DPI is standard for documents and photos. 150 DPI is adequate for thumbnails or web preview. 600 DPI or higher for fine scanning or print-quality archival.
- **Format choice:** JPEG for smaller files (good for photos within PDFs). PNG for lossless (documents with text). TIFF for professional archival (larger files, lossless, can embed metadata).
- **Large PDFs:** Page rasterization is I/O and CPU intensive. A 100-page PDF at 300 DPI can take 1–2 minutes. Warn the user before starting large jobs.
- Depends on poppler (`apt install poppler-utils` on Debian/Ubuntu, `brew install poppler` on macOS). Use `install-deps` rather than installing by hand.
