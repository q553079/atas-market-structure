from __future__ import annotations

from pathlib import Path

import yaml

from atas_market_structure.models import InstrumentProfile


class InstrumentProfileLoader:
    """Load strict instrument_profile_v1 YAML files from disk."""

    def load(self, path: str | Path) -> InstrumentProfile:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("instrument profile YAML must decode to one object")
        return InstrumentProfile.model_validate(payload)

    def load_many(self, directory: str | Path) -> list[InstrumentProfile]:
        root = Path(directory)
        return [self.load(path) for path in sorted(root.glob("*.yaml"))]
