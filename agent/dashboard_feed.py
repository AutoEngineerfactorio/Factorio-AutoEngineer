"""Bounded local display frames; isolated from gameplay approval and dispatch."""
import asyncio
import json
import math
import time

PREFIX = '@AUTOENGINEER_VIEW '


def point(value):
    if not isinstance(value, dict) or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) or abs(value[k]) > 1e7 for k in ('x', 'y')):
        raise ValueError('Invalid display position')
    return {k: value[k] for k in ('x', 'y')}


def snapshot(raw):
    if not isinstance(raw, dict) or raw.get('status') != 'ok':
        raise ValueError('Display unavailable')
    data = {'position': point(raw)}
    if type(raw.get('tick')) is not int or raw['tick'] < 0:
        raise ValueError('Invalid display tick')
    if not isinstance(raw.get('surface'), str) or len(raw['surface']) > 128:
        raise ValueError('Invalid display surface')
    data.update(tick=raw['tick'], surface=raw['surface'])
    items = raw.get('inventory')
    if items == {}: items = []  # Factorio encodes an empty Lua table as {}.
    if not isinstance(items, list) or len(items) > 64:
        raise ValueError('Invalid inventory display')
    data['inventory'] = []
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not 1 <= len(item[k]) <= 128 for k in ('name', 'quality')) or type(item.get('count')) is not int or not 0 <= item['count'] <= 10**12:
            raise ValueError('Invalid inventory item')
        data['inventory'].append({k: item[k] for k in ('name', 'quality', 'count')})
    for key in ('inventory_available', 'truncated'):
        if type(raw.get(key)) is not bool: raise ValueError('Invalid inventory state')
        data[key] = raw[key]
    return data


class DashboardFeed:
    def __init__(self):
        self.features = {'visited': [], 'failed': [], 'resources': [], 'objective': None, 'proposal': None}
        self.resource_recorded = None

    def update(self, resources, memory=None, objective=None, proposal=None):
        self.resource_recorded = time.monotonic() - resources.get('age_seconds', 0)
        self.features['resources'] = [{'name': r['name'][:128], 'x': r['center_x'], 'y': r['center_y']} for r in resources.get('resources', [])[:16]]
        if memory is not None:
            self.features['visited'] = [point(p) for p in memory.data['visited'][-64:]]
            self.features['failed'] = [point(p) for p in memory.data['failed'][-64:]]
        self.features['objective'] = point(objective) if objective is not None else None
        self.features['proposal'] = point(proposal) if isinstance(proposal, dict) and proposal.get('action') == 'walk' else None

    def publish(self, raw):
        data = snapshot(raw)
        data.update(self.features)
        data['resource_age_seconds'] = max(0, time.monotonic()-self.resource_recorded) if self.resource_recorded is not None else None
        print(PREFIX + json.dumps({'schema': 1, 'status': 'ok', **data}, separators=(',', ':'), allow_nan=False), flush=True)

    async def poll(self, session, control, interval=1):
        surface = None
        while not control.stop.is_set():
            try:
                response = await asyncio.wait_for(session.call_tool('autoengineer_view'), timeout=1.5)
                if response.is_error: raise ValueError('Display read failed')
                raw = next(json.loads(p.text) for p in response.content if p.type == 'text')
                data = snapshot(raw)
                if surface is not None and surface != data['surface']:
                    control.stop.set()
                    raise ValueError('Surface changed during session')
                surface = data['surface']
                self.publish(raw)
            except Exception:
                print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
            await asyncio.sleep(interval)

    async def run(self, session, control, work):
        task = asyncio.create_task(self.poll(session, control))
        try:
            return await work()
        finally:
            task.cancel()
            # Display cleanup cannot delay the surrounding game-side stop.
            task.add_done_callback(lambda t: None if t.cancelled() else t.exception())


def parse_frame(line):
    if not line.startswith(PREFIX): return None
    if len(line) > 65536: raise ValueError('Display frame too large')
    data = json.loads(line[len(PREFIX):])
    if not isinstance(data, dict) or data.get('schema') != 1: raise ValueError('Invalid display frame')
    if data.get('status') == 'unavailable': return {'status': 'unavailable'}
    # Validate backend fields again across the child-process boundary.
    position = point(data.get('position'))
    clean = snapshot(dict(data, **position))
    for name, limit in [('visited', 64), ('failed', 64), ('resources', 16)]:
        values = data.get(name)
        if not isinstance(values, list) or len(values) > limit: raise ValueError('Invalid map markers')
        clean[name] = []
        for value in values:
            marker = point(value)
            if name == 'resources':
                if not isinstance(value.get('name'), str) or len(value['name']) > 128: raise ValueError('Invalid marker label')
                marker['name'] = value['name']
            clean[name].append(marker)
    for key in ('objective', 'proposal'):
        clean[key] = point(data[key]) if data.get(key) is not None else None
    clean['status'] = 'ok'
    age = data.get('resource_age_seconds')
    if age is not None and (type(age) not in (int, float) or not math.isfinite(age) or age < 0):
        raise ValueError('Invalid resource age')
    clean['resource_age_seconds'] = age
    return clean
