from __future__ import annotations

import argparse
import csv
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def build_srt(tsv_path: Path, srt_path: Path) -> int:
    written = 0
    with tsv_path.open("r", encoding="utf-8") as source, srt_path.open(
        "w", encoding="utf-8"
    ) as target:
        reader = csv.DictReader(source, delimiter="\t")
        for index, row in enumerate(reader, start=1):
            text = row["text"].strip()
            if not text:
                continue
            start = format_timestamp(float(row["start"]))
            end = format_timestamp(float(row["end"]))
            target.write(f"{written + 1}\n")
            target.write(f"{start} --> {end}\n")
            target.write(f"{text}\n\n")
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert whisper TSV segments into an editable SRT subtitle file."
    )
    parser.add_argument("tsv_path", type=Path, help="Path to the whisper TSV file.")
    parser.add_argument("srt_path", type=Path, help="Path to write the SRT file.")
    args = parser.parse_args()

    written = build_srt(args.tsv_path, args.srt_path)
    print(f"Wrote {written} subtitle blocks to {args.srt_path}")


if __name__ == "__main__":
    main()
