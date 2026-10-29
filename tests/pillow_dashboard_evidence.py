"""Capture actual dashboard pixels and inspect them with Pillow; no game writes."""
from importlib import import_module


def capture(window, path):
    window.grab().save(str(path))
    Image = import_module("PIL.Image")
    with Image.open(path) as picture:
        picture.load()
        colors = picture.convert("RGB").getcolors(picture.width * picture.height)
        visual = {"path": str(path), "size": list(picture.size),
                  "colors": len(colors or []), "not_blank": len(colors or []) > 100}
    home = window.command_center()
    visual["readings"] = {key: value.text() for key, value in home.metric_fields.items()}
    model = window.telemetry_widget("Production").model
    visual["flow_rows"] = len(model.flows)
    visual["network_rows"] = len(model.networks)
    visual["research_active"] = model.research_active
    visual["pollution_amount"] = model.pollution_amount
    return visual
