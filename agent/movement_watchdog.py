"""Observe movement outside the backend gameplay queue; uncertain motion stops."""
import asyncio
import json
import math
import time
from agent_events import emit


class MovementStalled(RuntimeError):
    pass


async def monitored_walk(session, arguments, *, interval=.3, stall_seconds=5, total_seconds=25):
    async def observe():
        origin = last = None
        began = last_progress = time.monotonic()
        while True:
            await asyncio.sleep(interval)
            response = await asyncio.wait_for(session.call_tool('autoengineer_status',
                arguments={'owner': arguments['safetyOwner']}), timeout=1.5)
            data = None
            for part in response.content:
                if part.type == 'text': data = json.loads(part.text)
            if response.is_error or not isinstance(data, dict) or data.get('status') != 'active':
                raise RuntimeError('Movement observation unavailable')
            point = (data.get('x'), data.get('y'))
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
                raise RuntimeError('Invalid movement observation')
            if origin is None: origin = point
            if last is None or math.dist(last, point) >= .05:
                last, last_progress = point, time.monotonic()
            if time.monotonic()-last_progress >= stall_seconds or time.monotonic()-began >= total_seconds:
                emit('movement_stalled', elapsed=time.monotonic()-began)
                raise MovementStalled('Movement watchdog ended the session')

    walk = asyncio.create_task(session.call_tool('walk_to_position', arguments=arguments))
    watch = asyncio.create_task(observe())
    try:
        await asyncio.wait([walk, watch], return_when=asyncio.FIRST_COMPLETED)
        if watch.done():
            try:
                await watch
            except MovementStalled:
                raise
            except Exception:
                emit('movement_failed', status='other')
                raise
        return await walk
    finally:
        walk.cancel()
        watch.cancel()
        # The surrounding SafetySession starts game-side stopping immediately.
        # Do not wait indefinitely for a blocked transport to acknowledge cancel.
        for task in (walk, watch):
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
