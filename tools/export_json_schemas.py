from __future__ import annotations

from pathlib import Path
import json

from atas_market_structure.models import DepthSnapshotPayload, EventSnapshotPayload, MarketStructurePayload


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def write_schema(filename: str, schema: dict[str, object]) -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEMA_DIR / filename
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    write_schema("market_structure.schema.json", MarketStructurePayload.model_json_schema())
    write_schema("event_snapshot.schema.json", EventSnapshotPayload.model_json_schema())
    write_schema("depth_snapshot.schema.json", DepthSnapshotPayload.model_json_schema())


if __name__ == "__main__":
    main()
