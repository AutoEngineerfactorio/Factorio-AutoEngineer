"""Bounded, session-local resource observations; never initiates movement."""
import copy
import math
import time


class ResourceDiscovery:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.origin = None
        self.recorded = None
        self.resources = []
        self.scans = 0
        self.hits = 0

    async def observe(self, position, scan):
        point = tuple(position.get(k) for k in ('x', 'y'))
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
            raise ValueError('Invalid resource observation position')
        now = self.clock()
        refresh = (self.origin is None or now - self.recorded >= 10 or
                   now < self.recorded or math.dist(point, self.origin) >= 8)
        if refresh:
            response = await scan()
            if not isinstance(response, dict):
                raise ValueError('Invalid resource scan')
            entries = response.get('resources', [])
            if not isinstance(entries, list) or len(entries) > 128:
                raise ValueError('Invalid resource catalog')
            clean = []
            for resource in entries:
                if not isinstance(resource, dict) or not isinstance(resource.get('name'), str) or not 1 <= len(resource['name']) <= 128:
                    raise ValueError('Invalid resource name')
                if any(type(resource.get(k)) not in (int, float) or not math.isfinite(resource[k]) for k in ('center_x', 'center_y')):
                    raise ValueError('Invalid resource location')
                clean.append({k: resource[k] for k in ('name', 'center_x', 'center_y')})
                for key in ('patches', 'total_amount'):
                    value = resource.get(key)
                    if value is not None:
                        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                            raise ValueError('Invalid resource quantity')
                        clean[-1][key] = value
            self.resources = clean
            self.origin = point
            self.recorded = self.clock()
            self.scans += 1
        else:
            self.hits += 1
        resources = copy.deepcopy(self.resources)
        for resource in resources:
            resource['distance'] = round(math.dist(point, (resource['center_x'], resource['center_y'])), 3)
        resources = [r for r in resources if r['distance'] <= 50]
        resources.sort(key=lambda r: (r['distance'], r['name']))
        return {'scan_radius': 50, 'resources': resources,
                'cached': not refresh, 'age_seconds': round(max(0, self.clock()-self.recorded), 3),
                'scan_origin': {'x': self.origin[0], 'y': self.origin[1]}}
