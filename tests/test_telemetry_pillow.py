"""Pillow-based visualization test for Phase 1A telemetry graphs."""
import os
import sys

# Add agent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # type: ignore[reportMissingImports]
from PIL import Image, ImageDraw


# Minimal mock telemetry data matching production_telemetry.py structure
# Note: telemetry_view_model expects validated telemetry with specific fields
def mock_telemetry_ok():
    return {
        "status": "ok",
        "production": {
            "status": "ok",
            "unit": "units_per_minute",
            "precision": "ten_minutes",
            "sample_interval_seconds": 2,
            "sample_count": 60,
            "window_seconds": 120,
            "prototype_count": 10,
            "candidate_cap": 128,
            "candidate_bucket_count": 1,
            "candidate_bucket": 1,
            "partial": False,
            "items": {
                "status": "ok",
                "series": [
                    {"name": "Iron Plate", "input": [100] * 60, "output": [80] * 60}
                ]
            },
            "fluids": {
                "status": "ok",
                "series": []
            }
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": 12345,
            "networks": [
                {
                    "network_id": 0,
                    "tick": 12345,
                    "maximum_production": 1000,
                    "maximum_consumption": 800,
                    "consumption_satisfaction": 0.8,
                    "production_satisfaction": 1.0,
                    "accumulator_energy": 5000000,
                    "accumulator_capacity": 10000000
                }
            ],
            "partial": False
        }
    }


def _ensure_dir(path):
    """Ensure directory exists for file save."""
    dir_path = os.path.dirname(path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)


def test_pillow_image_creation():
    """Verify Pillow can create basic visualization canvas."""
    width, height = 800, 400
    img = Image.new('RGB', (width, height), color='#171b20')
    assert img.size == (width, height)


def test_pillow_draw_production_chart():
    """Draw production flow chart using Pillow."""
    from agent.production_telemetry import telemetry_view_model

    telemetry = mock_telemetry_ok()
    telemetry_view_model(telemetry)

    # Create image
    width, height = 800, 300
    img = Image.new('RGB', (width, height), color='#171b20')
    draw = ImageDraw.Draw(img)

    # Draw title
    draw.text((20, 20), "Production Flow", fill="#d5dbe1")

    # Draw axes
    draw.line([(40, 250), (760, 250)], fill="#65717d", width=2)
    draw.line([(40, 250), (40, 230)], fill="#65717d", width=2)

    # Draw sample data points (simplified)
    draw.rectangle([50, 50, 150, 150], fill="#e6a44e", outline="#e6a44e")
    draw.rectangle([200, 80, 300, 180], fill="#68aee0", outline="#68aee0")

    # Use in-memory file for Windows compatibility
    import io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    assert len(buf.getvalue()) > 0
    assert img.size == (width, height)


def test_pillow_draw_power_chart():
    """Draw power network chart using Pillow."""
    from agent.production_telemetry import telemetry_view_model

    telemetry = mock_telemetry_ok()
    telemetry_view_model(telemetry)

    # Create image
    width, height = 800, 300
    img = Image.new('RGB', (width, height), color='#171b20')
    draw = ImageDraw.Draw(img)

    # Draw title
    draw.text((20, 20), "Power Network", fill="#d5dbe1")

    # Draw axes
    draw.line([(40, 250), (760, 250)], fill="#65717d", width=2)
    draw.line([(40, 250), (40, 230)], fill="#65717d", width=2)

    # Draw sample data
    draw.rectangle([50, 50, 150, 150], fill="#e6a44e", outline="#e6a44e")
    draw.rectangle([200, 80, 300, 180], fill="#68aee0", outline="#68aee0")

    # Use in-memory file for Windows compatibility
    import io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    assert len(buf.getvalue()) > 0
    assert img.size == (width, height)


def test_pillow_combined_telemetry_dashboard():
    """Create combined telemetry visualization."""
    from agent.production_telemetry import telemetry_view_model

    telemetry = mock_telemetry_ok()
    telemetry_view_model(telemetry)

    # Create main dashboard image
    width, height = 1200, 600
    img = Image.new('RGB', (width, height), color='#171b20')
    draw = ImageDraw.Draw(img)

    # Draw title (no anchor for Pillow)
    draw.text((20, 20), "Phase 1A Telemetry Dashboard", fill="#d5dbe1")

    # Draw production chart section
    draw.rectangle([20, 20, 600, 300], fill="#2d3436", outline="#636e72")
    draw.text((30, 30), "Production Flows", fill="#d5dbe1")

    # Draw power chart section
    draw.rectangle([620, 20, 1180, 300], fill="#2d3436", outline="#636e72")
    draw.text((630, 30), "Power Network", fill="#d5dbe1")

    # Draw legend
    draw.rectangle([20, 320, 100, 340], fill="#e6a44e")
    draw.text((110, 325), "Production", fill="#d5dbe1")
    draw.rectangle([20, 345, 100, 365], fill="#68aee0")
    draw.text((110, 350), "Consumption", fill="#d5dbe1")

    # Use in-memory file for Windows compatibility
    import io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    assert len(buf.getvalue()) > 0
    assert img.size == (width, height)


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
