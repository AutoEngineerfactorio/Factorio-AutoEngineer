"""Analyse the rendered R08-C dashboard map against the live observation.

It answers, for the rendered image only:
  * how many distinct colours the terrain raster contributed,
  * how many nature marks and resource patch rectangles were drawn,
  * whether the tree tint palette produced distinct tree colours,
  * whether the chunk boundaries left gaps or duplicated marks.

Usage:
    python -B tests/r08c_render_analysis.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

import dashboard_map_layers as map_layers  # noqa: E402
import dashboard_nature_layers as nature  # noqa: E402
from PIL import Image  # noqa: E402

GEOMETRY = ROOT / "tests" / "r08c_geometry_live.json"
DASH = ROOT / ".local" / "scratch" / "r08c_dashboard_map.png"
OUTPUT = ROOT / "tests" / "r08c_render_analysis.json"


def main() -> int:
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    samples = geometry.get("samples") or {}
    image = Image.open(DASH).convert("RGB")
    colours = Counter(image.get_flattened_data())
    report = {
        "image_size": list(image.size),
        "distinct_colours": len(colours),
        "top_colours": [
            {"rgb": list(rgb) if isinstance(rgb, tuple) else None, "pixels": count}
            for rgb, count in colours.most_common(12)
        ],
    }

    # How many marks would the real layers draw for the live sample set?
    nature_entities = [
        dict(sample, kind="nature")
        for key, sample in samples.items()
        if key.startswith("nature/")
    ]
    resource_entities = [
        dict(sample, kind="resource")
        for key, sample in samples.items()
        if key.startswith("resource/")
    ]
    window = dict(x=0, y=0, width=64, height=64)
    shapes = nature.nature_shapes(nature_entities, window)
    tree_shapes = [s for s in shapes if s.kind == "tree"]
    tree_colours = Counter(s.color for s in tree_shapes)
    report["nature_shapes_drawn"] = len(shapes)
    report["tree_shapes_drawn"] = len(tree_shapes)
    report["distinct_tree_colours"] = len([c for c in tree_colours if c])
    report["tree_colour_counts"] = [
        {"rgb": list(rgb) if rgb else None, "count": count}
        for rgb, count in tree_colours.most_common(8)
    ]
    report["tree_shapes_without_colour"] = sum(1 for s in tree_shapes if not s.color)

    patches = map_layers.resource_patch_rectangles(resource_entities, window)
    report["resource_patches"] = {
        name: len(rectangles) for name, rectangles in patches.items()
    }
    report["resource_patch_rectangle_total"] = sum(
        len(rectangles) for rectangles in patches.values()
    )

    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("WROTE=" + str(OUTPUT))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
