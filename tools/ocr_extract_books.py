from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from typing import Any

import fitz
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PDF_EXTENSIONS = {".pdf"}
PAGE_NUMBER_PATTERN = re.compile(r"(?:page|p)[_\-\s]*0*(\d+)", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"(\d+)")
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
NUMERIC_NOISE_PATTERN = re.compile(r"^[\d\s\.,:;+\-$%#/\\()'\"`~_=<>|]+$")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class BookSource:
    book_name: str
    path: Path
    source_kind: str
    page_images: tuple[Path, ...] = ()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract OCR text for books from PDFs or image-page directories.",
    )
    parser.add_argument(
        "--input-root",
        action="append",
        default=[],
        help="Root directory to scan for books. Each child PDF, image, or image directory is treated as one book.",
    )
    parser.add_argument(
        "--book",
        action="append",
        default=[],
        help="Explicit book path to process. Supports PDF files, image files, or directories of page images.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/strategy_library/_source_extracts/ocr",
        help="Directory where *.txt and *.pages.json files will be written.",
    )
    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=220,
        help="Rasterization DPI used for PDF pages.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.55,
        help="Minimum OCR confidence for a line to be kept.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a book when both output files already exist.",
    )
    parser.add_argument(
        "--include-noisy-lines",
        action="store_true",
        help="Keep tiny numeric or punctuation-heavy OCR lines that are usually chart noise.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    explicit_books = [Path(item).resolve() for item in args.book]
    input_roots = [Path(item).resolve() for item in args.input_root]
    if not explicit_books and not input_roots:
        input_roots = [Path("data/pdf_pages").resolve()]

    books = discover_books(input_roots=input_roots, explicit_books=explicit_books)
    if not books:
        print("No OCR book sources found.", file=sys.stderr)
        return 1

    ocr_engine = RapidOCR()
    processed = 0
    skipped = 0
    failures = 0

    for book in books:
        output_stem = sanitize_filename(book.book_name)
        txt_path = output_dir / f"{output_stem}.txt"
        json_path = output_dir / f"{output_stem}.pages.json"
        if args.skip_existing and txt_path.exists() and json_path.exists():
            skipped += 1
            print(f"skip {book.book_name}: outputs already exist")
            continue

        try:
            payload = extract_book(
                book=book,
                ocr_engine=ocr_engine,
                pdf_dpi=args.pdf_dpi,
                min_confidence=args.min_confidence,
                include_noisy_lines=args.include_noisy_lines,
            )
            txt_content = build_book_text(payload["pages"])
            txt_path.write_text(txt_content, encoding="utf-8")
            json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            processed += 1
            print(
                f"done {book.book_name}: {len(payload['pages'])} pages -> "
                f"{txt_path.name}, {json_path.name}"
            )
        except Exception as exc:  # pragma: no cover - CLI smoke path
            failures += 1
            print(f"error {book.book_name}: {exc}", file=sys.stderr)

    print(f"summary processed={processed} skipped={skipped} failed={failures}")
    return 0 if failures == 0 else 1


def discover_books(*, input_roots: list[Path], explicit_books: list[Path]) -> list[BookSource]:
    discovered: list[BookSource] = []
    seen: set[Path] = set()

    def append_book(candidate: Path) -> None:
        resolved = candidate.resolve()
        if resolved in seen:
            return
        source = classify_book_path(resolved)
        if source is None:
            return
        seen.add(resolved)
        discovered.append(source)

    for book in explicit_books:
        append_book(book)

    for root in input_roots:
        if not root.exists():
            print(f"warn missing input root: {root}", file=sys.stderr)
            continue

        if root.is_file():
            append_book(root)
            continue

        child_candidates = sorted(root.iterdir(), key=lambda item: natural_sort_key(item.name))
        matched_children = False
        for child in child_candidates:
            if classify_book_path(child.resolve()) is None:
                continue
            matched_children = True
            append_book(child)
        if not matched_children:
            append_book(root)

    discovered.sort(key=lambda item: natural_sort_key(item.book_name))
    return discovered


def classify_book_path(path: Path) -> BookSource | None:
    if path.is_dir():
        page_images = collect_directory_pages(path)
        if not page_images:
            return None
        return BookSource(
            book_name=path.name,
            path=path,
            source_kind="image_directory",
            page_images=page_images,
        )

    suffix = path.suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return BookSource(book_name=path.stem, path=path, source_kind="pdf")
    if suffix in IMAGE_EXTENSIONS:
        return BookSource(book_name=path.stem, path=path, source_kind="image")
    return None


def collect_directory_pages(directory: Path) -> tuple[Path, ...]:
    images = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not images:
        return ()

    numbered = []
    for image in images:
        page_number = extract_page_number(image.stem)
        if page_number is not None:
            numbered.append((page_number, image))

    if numbered:
        numbered.sort(key=lambda item: (item[0], natural_sort_key(item[1].name)))
        return tuple(image for _, image in numbered)

    images.sort(key=lambda item: natural_sort_key(item.name))
    return tuple(images)


def extract_book(
    *,
    book: BookSource,
    ocr_engine: RapidOCR,
    pdf_dpi: int,
    min_confidence: float,
    include_noisy_lines: bool,
) -> dict[str, Any]:
    started_at = datetime.now(tz=UTC)
    pages = []
    for page_number, source_ref, image_array in iterate_book_pages(book, pdf_dpi=pdf_dpi):
        pages.append(
            extract_page(
                image_array=image_array,
                page_number=page_number,
                source_ref=source_ref,
                ocr_engine=ocr_engine,
                min_confidence=min_confidence,
                include_noisy_lines=include_noisy_lines,
            )
        )

    return {
        "schema_version": "1.0.0",
        "book_name": book.book_name,
        "book_output_stem": sanitize_filename(book.book_name),
        "source_kind": book.source_kind,
        "source_path": str(book.path),
        "generated_at": started_at.isoformat(),
        "ocr_engine": {
            "name": "rapidocr-onnxruntime",
            "version": importlib.metadata.version("rapidocr-onnxruntime"),
            "pdf_dpi": pdf_dpi,
            "min_confidence": min_confidence,
            "include_noisy_lines": include_noisy_lines,
        },
        "page_count": len(pages),
        "pages": pages,
    }


def iterate_book_pages(book: BookSource, *, pdf_dpi: int) -> list[tuple[int, str, np.ndarray]]:
    if book.source_kind == "pdf":
        return list(iter_pdf_pages(book.path, pdf_dpi=pdf_dpi))
    if book.source_kind == "image_directory":
        return [
            (index, str(path), load_image(path))
            for index, path in enumerate(book.page_images, start=1)
        ]
    if book.source_kind == "image":
        return [(1, str(book.path), load_image(book.path))]
    raise ValueError(f"Unsupported book source kind: {book.source_kind}")


def iter_pdf_pages(path: Path, *, pdf_dpi: int) -> list[tuple[int, str, np.ndarray]]:
    pages: list[tuple[int, str, np.ndarray]] = []
    matrix = fitz.Matrix(pdf_dpi / 72.0, pdf_dpi / 72.0)
    with fitz.open(path) as document:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            buffer = np.frombuffer(pixmap.samples, dtype=np.uint8)
            image_array = buffer.reshape(pixmap.height, pixmap.width, pixmap.n)
            pages.append((page_index + 1, f"{path}#page={page_index + 1}", image_array))
    return pages


def load_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGB"))


def extract_page(
    *,
    image_array: np.ndarray,
    page_number: int,
    source_ref: str,
    ocr_engine: RapidOCR,
    min_confidence: float,
    include_noisy_lines: bool,
) -> dict[str, Any]:
    page_height, page_width = image_array.shape[:2]
    raw_results, _ = ocr_engine(image_array)
    lines = []
    dropped_line_count = 0

    for item in raw_results or []:
        polygon = [[float(point[0]), float(point[1])] for point in item[0]]
        text = normalize_text(str(item[1]))
        confidence = float(item[2])
        if not text or confidence < min_confidence:
            dropped_line_count += 1
            continue

        bbox = polygon_to_bbox(polygon)
        if not include_noisy_lines and looks_like_noise(
            text=text,
            confidence=confidence,
            bbox=bbox,
            page_width=page_width,
            page_height=page_height,
        ):
            dropped_line_count += 1
            continue

        lines.append(
            {
                "text": text,
                "confidence": round(confidence, 4),
                "polygon": polygon,
                "bbox": bbox,
            }
        )

    lines.sort(key=lambda item: reading_sort_key(item["bbox"]))
    for index, line in enumerate(lines, start=1):
        line["reading_order"] = index

    page_text = build_page_text(lines)
    return {
        "page_number": page_number,
        "source_ref": source_ref,
        "width": page_width,
        "height": page_height,
        "text": page_text,
        "line_count": len(lines),
        "dropped_line_count": dropped_line_count,
        "lines": lines,
    }


def build_book_text(pages: list[dict[str, Any]]) -> str:
    chunks = []
    for page in pages:
        chunks.append(f"===== Page {page['page_number']} =====")
        chunks.append(page["text"])
    return "\n\n".join(chunks).strip() + "\n"


def build_page_text(lines: list[dict[str, Any]]) -> str:
    if not lines:
        return ""

    heights = [line["bbox"]["height"] for line in lines]
    median_height = sorted(heights)[len(heights) // 2]
    gap_threshold = max(18.0, median_height * 0.9)

    fragments: list[str] = []
    previous_bottom: float | None = None
    for line in lines:
        current_top = line["bbox"]["top"]
        if previous_bottom is not None and current_top - previous_bottom > gap_threshold:
            fragments.append("")
        fragments.append(line["text"])
        previous_bottom = line["bbox"]["bottom"]
    return "\n".join(fragments).strip()


def polygon_to_bbox(polygon: list[list[float]]) -> dict[str, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    return {
        "left": round(left, 2),
        "top": round(top, 2),
        "right": round(right, 2),
        "bottom": round(bottom, 2),
        "width": round(right - left, 2),
        "height": round(bottom - top, 2),
    }


def reading_sort_key(bbox: dict[str, float]) -> tuple[float, float, float]:
    snapped_top = round(bbox["top"] / 6.0) * 6.0
    return (snapped_top, bbox["left"], bbox["bottom"])


def looks_like_noise(
    *,
    text: str,
    confidence: float,
    bbox: dict[str, float],
    page_width: int,
    page_height: int,
) -> bool:
    has_word_characters = bool(CJK_PATTERN.search(text) or LATIN_PATTERN.search(text))
    has_cjk = bool(CJK_PATTERN.search(text))
    numeric_like = bool(NUMERIC_NOISE_PATTERN.fullmatch(text))
    contains_digits = any(character.isdigit() for character in text)
    normalized = text.casefold()
    tiny_height = bbox["height"] <= max(12.0, page_height * 0.018)
    tiny_width = bbox["width"] <= max(28.0, page_width * 0.02)
    area_ratio = (bbox["width"] * bbox["height"]) / max(float(page_width * page_height), 1.0)

    if normalized == "notebooklm":
        return True
    if not has_word_characters and numeric_like and (tiny_height or tiny_width or area_ratio < 0.00018):
        return True
    if contains_digits and not has_cjk and bbox["height"] <= max(24.0, page_height * 0.03) and bbox["width"] <= max(220.0, page_width * 0.09):
        return True
    if not has_word_characters and len(text) <= 3 and confidence < 0.85:
        return True
    if len(text) == 1 and confidence < 0.9:
        return True
    return False


def normalize_text(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def extract_page_number(stem: str) -> int | None:
    match = PAGE_NUMBER_PATTERN.search(stem)
    if not match:
        return None
    return int(match.group(1))


def natural_sort_key(value: str) -> list[object]:
    parts = TOKEN_PATTERN.split(value.lower())
    key: list[object] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return key


def sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip()
    cleaned = WHITESPACE_PATTERN.sub("_", cleaned)
    return cleaned or "ocr_book"


if __name__ == "__main__":
    raise SystemExit(main())
