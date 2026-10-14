"""Write the guide format schemas (version 0.2) as JSON files next to PLAN.md.

    python make_schemas.py

The definitions live in the app: app/backend/app/guide_builder/schemas.py.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app" / "backend"))
from app.guide_builder import schemas  # noqa: E402

OUT = Path(__file__).resolve().parents[1]
for name, sch in (("guide-schema.json", schemas.GUIDE), ("ai-outline-schema.json", schemas.AI_OUTLINE),
                  ("ai-section-schema.json", schemas.AI_SECTION)):
    (OUT / name).write_text(json.dumps(sch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUT / name)
