"""User-selected session objective, independent of model-generated prose."""

import math
import os
import re


class Objective:
    def __init__(self, selection):
        self.target = None
        self.resource = None
        if not isinstance(selection, str) or not selection.strip() or len(selection) > 100:
            raise ValueError("Choose a resource name or x,y coordinates")
        selection = selection.strip()
        if "," in selection:
            try:
                values = [float(v.strip()) for v in selection.split(",")]
            except ValueError:
                raise ValueError("Objective coordinates must be finite numbers") from None
            if len(values) != 2 or any(not math.isfinite(v) or abs(v) > 1e6 for v in values):
                raise ValueError("Objective coordinates outside supported bounds")
            self.target = dict(zip(("x", "y"), values))
            self.radius = 0.75
        elif re.fullmatch(r"[a-z][a-z0-9-]{0,63}", selection):
            self.resource = selection
            self.radius = 2.0
        else:
            raise ValueError("Use a resource name such as iron-ore or coordinates such as 12,-8")

    def observe(self, state):
        if self.target is None:
            resources = state.get("resources", {})
            resources = resources.get("resources", []) if isinstance(resources, dict) else []
            usable = (
                [
                    r
                    for r in resources
                    if isinstance(r, dict)
                    and r.get("name") == self.resource
                    and all(
                        type(r.get(k)) in (int, float) and math.isfinite(r[k]) and abs(r[k]) <= 1e6
                        for k in ("center_x", "center_y")
                    )
                ]
                if isinstance(resources, list)
                else []
            )
            if not usable:
                return None
            position = state["position"]
            chosen = min(
                usable,
                key=lambda r: math.hypot(
                    r["center_x"] - position["x"], r["center_y"] - position["y"]
                ),
            )
            self.target = {"x": chosen["center_x"], "y": chosen["center_y"]}
        return self.target

    def distance(self, position):
        return math.hypot(position["x"] - self.target["x"], position["y"] - self.target["y"])


def load_objective():
    value = os.environ.get("AUTOENGINEER_OBJECTIVE")
    return Objective(value) if value is not None else None
