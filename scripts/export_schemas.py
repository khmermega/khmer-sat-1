#!/usr/bin/env python3
"""Export JSON Schemas for all protocol payloads to shared/schemas/json/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.schemas import CommandAck, CommandBody, EventMessage, Housekeeping, ImageMeta  # noqa: E402
from shared.schemas.models import SCHEMA_VERSION  # noqa: E402

OUT = ROOT / "shared" / "schemas" / "json"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for model in (Housekeeping, EventMessage, CommandBody, CommandAck, ImageMeta):
        schema = model.model_json_schema()
        schema["$id"] = f"https://khmer-sat-1.invalid/schemas/{SCHEMA_VERSION}/{model.__name__}.json"
        (OUT / f"{model.__name__}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote {model.__name__}.schema.json")


if __name__ == "__main__":
    main()
