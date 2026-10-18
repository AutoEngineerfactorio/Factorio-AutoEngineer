"""Local, explicitly world-scoped exploration hints; never authorizes movement."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

LIMIT = 10000


def point(position):
    values = [position.get(k) for k in ('x', 'y')]
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e7 for v in values):
        raise ValueError('Invalid exploration position')
    return values


class ExplorationMemory:
    def __init__(self, world, directory=None):
        if not isinstance(world, str) or not world.strip() or len(world) > 200:
            raise ValueError('Use a nonempty world identifier of at most 200 characters')
        self.path = Path(directory or Path(__file__).resolve().parents[1] / '.local/exploration') / (hashlib.sha256(world.encode()).hexdigest() + '.json')
        self.data = {'schema': 1, 'visited': [], 'failed': []}
        if self.path.exists():
            if self.path.stat().st_size > 2000000:
                raise ValueError('Exploration map exceeds supported size')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or set(data) != set(self.data) or type(data['schema']) is not int or data['schema'] != 1:
                raise ValueError('Unsupported exploration map')
            for name in ('visited', 'failed'):
                if not isinstance(data[name], list) or len(data[name]) > LIMIT:
                    raise ValueError('Invalid exploration map entries')
                for entry in data[name]:
                    if not isinstance(entry, dict) or set(entry) != {'x', 'y'}:
                        raise ValueError('Invalid exploration map point')
                    point(entry)
            self.data = data

    def visited(self, position):
        x, y = point(position)
        return any(math.floor(p['x']/2) == math.floor(x/2) and math.floor(p['y']/2) == math.floor(y/2) for p in self.data['visited'])

    def blocked(self, position):
        return any(math.dist(point(position), point(p)) <= 1 for p in self.data['failed'])

    def remember(self, position, *, failed=False):
        x, y = point(position)
        name = 'failed' if failed else 'visited'
        if (self.blocked(position) if failed else self.visited(position)):
            return
        self.data[name].append({'x': x, 'y': y})
        self.data[name] = self.data[name][-LIMIT:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement retains the last valid map if writing is interrupted.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as output:
                temporary = output.name
                json.dump(self.data, output, allow_nan=False, separators=(',', ':'))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def load_memory():
    world = os.environ.get('AUTOENGINEER_WORLD')
    return ExplorationMemory(world) if world is not None else None
