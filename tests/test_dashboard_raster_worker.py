"""Worker raster generation uses one process and stays out of Tk's hot path."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import dashboard_view


class WorkerRasterTests(unittest.TestCase):
    def test_raster_job_is_submitted_not_computed_on_ui_thread(self):
        v = Mock()
        v._raster_executor = Mock()
        v._raster_future = None
        v._raster_requested_key = None
        v.raster_key = None
        v.map_image = None
        terrain = {"origin": {"x": 0, "y": 0}, "rasters": []}
        with patch.object(dashboard_view, "raster_pixels", side_effect=AssertionError(
            "Raster computed on Tk thread"
        )):
            dashboard_view.LiveView.draw_raster(
                v, terrain, {"x": 0, "y": 0}, 200, 100, 40
            )
        v._raster_executor.submit.assert_called_once()
        v.after.assert_called_once_with(50, v._collect_raster)
        v.canvas.create_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
