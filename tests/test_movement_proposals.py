import json
import math
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import supervised_agent as agent
from movement_proposals import movement_choices, resolve_choice


class MovementProposalTests(unittest.TestCase):
    def observation(self, x: float = 0, y: float = 0):
        return {
            "position": {"x": x, "y": y},
            "resources": {"resources": [{"name": "coal", "center_x": x + 1, "center_y": y - 45}]},
        }

    def test_distant_resource_becomes_approved_short_step(self):
        state = self.observation()
        choices = movement_choices(state)
        proposal = resolve_choice(
            {"choice": choices[0]["choice"], "reason": "Approach coal"}, choices
        )
        arguments = agent.validate(proposal, state["position"])
        assert arguments is not None
        self.assertLessEqual(math.hypot(arguments["targetX"], arguments["targetY"]), 5)
        self.assertLess(arguments["targetY"], 0)
        self.assertGreater(arguments["targetY"], -5)

    def test_nonzero_and_negative_positions_are_absolute_waypoints(self):
        for x, y in [(125.75, -83.2), (-500.25, 300.125)]:
            state = self.observation(x, y)
            for choice in movement_choices(state):
                proposal = resolve_choice({"choice": choice["choice"]}, [choice])
                agent.validate(proposal, state["position"])

    def test_five_tile_validator_still_rejects_raw_distant_or_diagonal_moves(self):
        for x, y in [(1, -45), (5.001, 0), (4, 4), (True, 0), (float("nan"), 0)]:
            with self.subTest(x=x, y=y), self.assertRaises((ValueError, PermissionError)):
                agent.validate({"action": "walk", "x": x, "y": y}, {"x": 0, "y": 0})
        agent.validate({"action": "walk", "x": 5, "y": 0}, {"x": 0, "y": 0})

    def test_unknown_choice_and_extra_coordinates_fail_closed(self):
        choices = movement_choices(self.observation())
        for response in [
            {"choice": "invented"},
            {"choice": "step_1", "x": 90},
            {"action": "walk", "x": 1, "y": -45},
            [],
            None,
        ]:
            with self.assertRaises(PermissionError):
                agent.validate(resolve_choice(response, choices), {"x": 0, "y": 0})

    def test_stop_and_empty_resource_scan(self):
        self.assertIsNone(agent.validate(resolve_choice({"choice": "stop"}, []), {"x": 0, "y": 0}))
        for resources in [
            {},
            {"resources": None},
            {"resources": [{"center_x": float("inf"), "center_y": 0}]},
        ]:
            choices = movement_choices({"position": {"x": 0, "y": 0}, "resources": resources})
            self.assertEqual(len(choices), 4)

    def test_real_request_contract_maps_model_choice_without_exposing_far_target(self):
        captured = []

        def response(request, **kwargs):
            captured.append(json.loads(request.data))
            return BytesIO(
                json.dumps(
                    {"choices": [{"message": {"content": '{"choice":"step_1","reason":"coal"}'}}]}
                ).encode()
            )

        with patch.object(agent.urllib.request, "urlopen", side_effect=response):
            proposal = agent.ask_ai(self.observation(), [])
        agent.validate(proposal, {"x": 0, "y": 0})
        sent = json.loads(captured[0]["messages"][-1]["content"])
        self.assertNotIn("resources", sent)
        self.assertNotIn("-45", json.dumps(sent))
        self.assertTrue(sent["offered_steps"])
