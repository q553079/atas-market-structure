# OCR Source Extraction

This OCR pipeline is intentionally separate from the main ATAS market-structure service.

Its job is limited to source-text extraction for books and slide decks. It does not update strategy cards, machine-readable outputs, or routing indexes.

## Boundaries

The OCR workflow writes only to:

- `docs/strategy_library/_source_extracts/ocr`

It does not write to:

- `docs/strategy_library/patterns`
- `docs/strategy_library/machine`
- `docs/strategy_library/strategy_index.json`
- `docs/thread_coordination.md`

## Runtime Isolation

The OCR runner uses a separate Docker image:

- `Dockerfile.ocr`
- Compose service: `strategy-library-ocr`
- Compose profile: `ocr`

The main backend service remains on its existing image and dependency set.

The OCR container:

- does not expose any ports
- does not start unless the `ocr` profile is requested
- mounts only `./data` and `./docs`
- exits after the batch run completes

This keeps OCR CPU and memory usage isolated from the normal replay and API workflows.

## Supported Inputs

The OCR script supports three source types:

1. PDF file
2. Single image file
3. Directory of page images

Default discovery scans:

- `data/pdf_pages`

Each child PDF, image, or image-directory under that root is treated as one book.

You can also pass explicit paths with `--book`.

## Outputs

For each discovered book, the OCR pipeline writes:

1. `BOOK_NAME.txt`
2. `BOOK_NAME.pages.json`

Both are written under:

- `docs/strategy_library/_source_extracts/ocr`

### TXT file

The text file is page-separated:

```text
===== Page 1 =====

...

===== Page 2 =====

...
```

### Pages JSON

The JSON file preserves page-level text and line layout:

- `book_name`
- `source_kind`
- `source_path`
- `generated_at`
- `ocr_engine`
- `page_count`
- `pages[]`

Each page contains:

- `page_number`
- `source_ref`
- `width`
- `height`
- `text`
- `line_count`
- `dropped_line_count`
- `lines[]`

Each OCR line contains:

- `text`
- `confidence`
- `polygon`
- `bbox`
- `reading_order`

This gives downstream threads enough structure to recover page boundaries and line positions without touching strategy-library outputs.

## Commands

Build the OCR image:

```powershell
docker compose --profile ocr build strategy-library-ocr
```

Run the default scan:

```powershell
docker compose --profile ocr run --rm strategy-library-ocr
```

Run one explicit book directory:

```powershell
docker compose --profile ocr run --rm strategy-library-ocr `
  --book /workspace/data/pdf_pages/baocangdawang `
  --output-dir /workspace/docs/strategy_library/_source_extracts/ocr
```

Run one explicit PDF:

```powershell
docker compose --profile ocr run --rm strategy-library-ocr `
  --book /workspace/docs/strategy_library/_source_extracts/example_book.pdf `
  --output-dir /workspace/docs/strategy_library/_source_extracts/ocr
```

Force noisy chart numerics to be kept:

```powershell
docker compose --profile ocr run --rm strategy-library-ocr `
  --book /workspace/data/pdf_pages/baocangdawang `
  --include-noisy-lines
```

## Local Fallback

If Docker is unavailable, the same script can be run locally:

```powershell
python .\tools\ocr_extract_books.py `
  --input-root .\data\pdf_pages `
  --output-dir .\docs\strategy_library\_source_extracts\ocr
```

## Notes on OCR Quality

The default output filters tiny numeric-only fragments that usually come from chart overlays, axes, or footprint annotations.

That filter improves book-text readability for mixed chart-and-text pages, but it can be disabled with `--include-noisy-lines` when every numeric fragment matters.
