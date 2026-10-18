import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from resource_discovery import ResourceDiscovery
from offline_loop import OfflineLoop


def scan_data():
    return {'resources': [{'name': 'iron-ore', 'center_x': 20, 'center_y': 0, 'total_amount': 500},
                          {'name': 'coal', 'center_x': 4, 'center_y': 0, 'patches': 10}]}


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def test_repeated_scans_reused_and_ranked_from_current_position(self):
        discovery = ResourceDiscovery(clock=lambda: 0)
        scan = AsyncMock(return_value=scan_data())
        first = await discovery.observe({'x': 0, 'y': 0}, scan)
        second = await discovery.observe({'x': 4, 'y': 0}, scan)
        self.assertEqual(scan.await_count, 1)
        self.assertFalse(first['cached']); self.assertTrue(second['cached'])
        self.assertEqual(second['resources'][0]['name'], 'coal')
        self.assertEqual(second['resources'][0]['distance'], 0)
        self.assertEqual(first['resources'][0]['distance'], 4)
        second['resources'][0]['name'] = 'changed'
        self.assertEqual((await discovery.observe({'x': 4, 'y': 0}, scan))['resources'][0]['name'], 'coal')

    async def test_refresh_at_eight_tiles_or_ten_seconds(self):
        now = [0]; discovery = ResourceDiscovery(clock=lambda: now[0]); scan = AsyncMock(return_value=scan_data())
        await discovery.observe({'x': 0, 'y': 0}, scan)
        await discovery.observe({'x': 7.99, 'y': 0}, scan)
        self.assertEqual(scan.await_count, 1)
        await discovery.observe({'x': 8, 'y': 0}, scan)
        self.assertEqual(scan.await_count, 2)
        now[0] = 10
        await discovery.observe({'x': 8, 'y': 0}, scan)
        self.assertEqual(scan.await_count, 3)

    async def test_empty_scans_cached_and_session_context_isolated(self):
        scan = AsyncMock(return_value={'resources': []})
        discovery = ResourceDiscovery(clock=lambda: 0)
        await discovery.observe({'x': 0, 'y': 0}, scan)
        await discovery.observe({'x': 0, 'y': 0}, scan)
        await ResourceDiscovery(clock=lambda: 0).observe({'x': 0, 'y': 0}, scan)
        self.assertEqual(scan.await_count, 2)

    async def test_invalid_refresh_does_not_fall_back_to_stale_catalog(self):
        now = [0]; discovery = ResourceDiscovery(clock=lambda: now[0]); scan = AsyncMock(return_value=scan_data())
        await discovery.observe({'x': 0, 'y': 0}, scan)
        now[0] = 11; scan.return_value = {'resources': [{'name': 'ore', 'center_x': float('nan'), 'center_y': 0}]}
        with self.assertRaises(ValueError): await discovery.observe({'x': 0, 'y': 0}, scan)

    async def test_unknown_resource_names_supported_and_distant_centers_filtered(self):
        discovery = ResourceDiscovery(clock=lambda: 0)
        scan = AsyncMock(return_value={'resources': [{'name': 'tungsten-ore', 'center_x': -49, 'center_y': 0}]})
        self.assertEqual(len((await discovery.observe({'x': 0, 'y': 0}, scan))['resources']), 1)
        self.assertEqual((await discovery.observe({'x': 4, 'y': 0}, scan))['resources'], [])

    async def test_malformed_catalogs_rejected(self):
        for response in [[], {'resources': 'bad'}, {'resources': [{}]}, {'resources': [{'name': 'ore', 'center_x': True, 'center_y': 0}]}, {'resources': [{'name': 'ore', 'center_x': 0, 'center_y': 0, 'total_amount': -1}]}]:
            with self.assertRaises(ValueError):
                await ResourceDiscovery().observe({'x': 0, 'y': 0}, AsyncMock(return_value=response))
