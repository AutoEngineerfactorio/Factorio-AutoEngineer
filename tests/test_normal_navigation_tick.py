"""Execute the exact backend tick handler against a deterministic offline world."""

import unittest
from pathlib import Path
from typing import Any, cast

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("Install tests/requirements-lua.txt to run the Lua tick tests")
tick = (Path(__file__).resolve().parents[1] / "backend-safety/NavigationTick.lua").read_text()


def lua_globals(lua: LuaRuntime) -> Any:
    """Typed boundary for Lua runtime-generated global table fields."""
    return cast(Any, lua.globals())


class TickTests(unittest.TestCase):
    def make(self, speed=0.15, x=4, y=0, route=None):
        lua = LuaRuntime(unpack_returned_tuples=False)
        lua.execute("""
          remote={interfaces={}}
          remote.add_interface=function(name,methods) remote.interfaces[name]=methods end
          storage={autoengineer_safety={owner='a',player=1,deadline=5000,stopped=false}}
          defines={events={on_tick=1},direction={north=0},controllers={character=1,remote=2}}
          player={valid=true,index=1,controller_type=1,driving=false,character={valid=true},surface={index=1},position={x=0,y=0},walking_state={walking=false,direction=0}}
          game={tick=0,connected_players={player},get_player=function() return player end}
          script={on_event=function(_,f) handler=f end}
          function step()
            game.tick=game.tick+1;handler()
            if player.walking_state.walking then
              local a=player.walking_state.direction*math.pi/8
              player.position.x=player.position.x+math.sin(a)*player.character_running_speed
              player.position.y=player.position.y-math.cos(a)*player.character_running_speed
            end
          end
        """)
        lua_globals(lua).player.character_running_speed = speed
        path = route or [(0, 0), (x, y)]
        pts = "{" + ",".join("{x=" + str(px) + ",y=" + str(py) + "}" for px, py in path) + "}"
        lua.execute(
            f"storage.autoengineer_nav={{owner='a',surface=1,origin={{x=0,y=0}},previous={{x=0,y=0}},target={{x={x},y={y}}},tolerance=.75,route={pts},index=1,travel=0,status='running',last_progress=0,deadline=1200}}"
        )
        lua.execute(tick)
        return lua

    def run_to_stop(self, lua):
        maximum = 0
        for _ in range(400):
            lua_globals(lua).step()
            p = lua_globals(lua).player.position
            maximum = max(maximum, (p.x * p.x + p.y * p.y) ** 0.5)
            if lua_globals(lua).storage.autoengineer_nav.status != "running":
                break
        self.assertLessEqual(maximum, 5)
        self.assertFalse(lua_globals(lua).player.walking_state.walking)
        return lua_globals(lua).storage.autoengineer_nav.status

    def test_normal_speed_cardinal_diagonal_and_corner(self):
        for x, y, route in [(4, 0, None), (3, 2, None), (4, 0, [(0, 0), (1, 1), (4, 0)])]:
            with self.subTest(target=(x, y), route=route):
                self.assertEqual(self.run_to_stop(self.make(x=x, y=y, route=route)), "arrived")

    def test_physical_budget_and_high_speed_refusal(self):
        for speed in (0.15, 0.5, 1, 2, 5):
            with self.subTest(speed=speed):
                self.assertIn(
                    self.run_to_stop(self.make(speed=speed)), ("arrived", "limit_reached")
                )

    def test_surface_and_owner_mismatch(self):
        for field in ("owner", "surface"):
            lua = self.make()
            lua_globals(lua).storage.autoengineer_nav[field] = "other" if field == "owner" else 2
            self.assertEqual(self.run_to_stop(lua), "stopped")

    def test_remote_view_and_vehicle_revoke_walking(self):
        for mutation in ("player.controller_type=2", "player.driving=true"):
            lua = self.make()
            lua_globals(lua).step()
            lua.execute(mutation)
            lua_globals(lua).step()
            self.assertEqual(lua_globals(lua).storage.autoengineer_nav.status, "stopped")
            self.assertFalse(lua_globals(lua).player.character.walking_state.walking)

    def test_inactive_handler_does_not_suppress_human_walking(self):
        lua = self.make()
        lua_globals(lua).storage.autoengineer_safety.stopped = True
        lua_globals(lua).step()
        lua.execute(
            "player.character.walking_state={walking=true,direction=4};player.walking_state={walking=true,direction=4}"
        )
        lua_globals(lua).step()
        self.assertTrue(lua_globals(lua).player.character.walking_state.walking)
        self.assertTrue(lua_globals(lua).player.walking_state.walking)

    def test_human_input_revokes_lease_and_cannot_reactivate(self):
        lua = self.make()
        lua_globals(lua).step()
        lua_globals(lua).remote.interfaces.autoengineer_control.takeover(1)
        self.assertTrue(lua_globals(lua).storage.autoengineer_safety.stopped)
        self.assertEqual(lua_globals(lua).storage.autoengineer_safety.reason, "human_takeover")
        self.assertEqual(lua_globals(lua).storage.autoengineer_nav.status, "stopped")
        lua_globals(lua).step()
        self.assertFalse(lua_globals(lua).player.character.walking_state.walking)

    def test_lease_expiry_stops_existing_walk(self):
        lua = self.make()
        lua_globals(lua).step()
        lua_globals(lua).storage.autoengineer_safety.deadline = 0
        self.assertEqual(self.run_to_stop(lua), "stopped")

    def test_cannot_resume_after_stop(self):
        lua = self.make()
        lua_globals(lua).step()
        lua_globals(lua).storage.autoengineer_safety.stopped = True
        self.assertEqual(self.run_to_stop(lua), "stopped")
        x = lua_globals(lua).player.position.x
        lua_globals(lua).storage.autoengineer_safety.stopped = False
        for _ in range(10):
            lua_globals(lua).step()
        self.assertEqual(lua_globals(lua).player.position.x, x)

    def test_blocked_physics_times_out_without_false_arrival(self):
        lua = self.make()
        lua.execute("function step() game.tick=game.tick+1;handler() end")
        self.assertEqual(self.run_to_stop(lua), "stuck")

    def test_shallow_bearing_does_not_flicker_between_cardinal_and_diagonal(self):
        lua = self.make(x=4, y=2, route=[(0, 0), (1, 0.5), (2, 1), (3, 1.5), (4, 2)])
        directions = []
        for _ in range(100):
            lua_globals(lua).step()
            if lua_globals(lua).player.walking_state.walking:
                directions.append(lua_globals(lua).player.walking_state.direction)
            if lua_globals(lua).storage.autoengineer_nav.status != "running":
                break
        self.assertEqual(lua_globals(lua).storage.autoengineer_nav.status, "arrived")
        self.assertLessEqual(sum(a != b for a, b in zip(directions, directions[1:])), 3)
        self.assertTrue(any(direction % 2 for direction in directions))


if __name__ == "__main__":
    unittest.main(verbosity=2)
