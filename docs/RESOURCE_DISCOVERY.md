# Efficient nearby-resource discovery

Each supervised session keeps a small, in-memory catalog from the existing
player-centered 50-tile resource scan. It reuses that observation for less than
ten seconds and less than eight tiles of displacement from the scan origin.
Crossing either threshold triggers a fresh scan. Empty observations are cached
too, avoiding repeated scans of empty ground. New sessions always start fresh;
resource quantities are never persisted in the visited-area map.

The catalog validates names, finite centers and nonnegative quantities, limits
results to 128 resource types, and copies returned data to prevent accidental
cache mutation. Scan failures or invalid data end the session through normal
safety cleanup; they do not silently fall back to stale data.

Results are ranked by center distance from the current player position. Centers
now beyond 50 tiles are omitted. The activity log shows fresh/cached status,
observation age, scan/cache counts, and up to eight nearest named centers.
Resource names are not hard-coded, so Space Age resource names are accepted.
Space Age gameplay itself still needs dedicated validation in the vanilla phase.

Cached observations cover the earlier scan circle, not all terrain within 50
tiles of the new position. Newly visible edge resources, mining changes and
other changes may be missed until refresh. The backend aggregates each resource
type into a bounding center; these are resource summaries, not separate connected
ore patches, nearest ore tiles, or proof of traversability. Its legacy `patches`
field counts resource entities, not connected patches. Quantities are estimates
from the last observation. This change reduces repeated calls; it does not change
the engine scan algorithm or establish a frame-time performance benchmark.

No new backend tool or permission is introduced. Human approval, one-use dispatch,
policy-v3 path validation, independent five-tile target bounds, the watchdog and
game-side emergency stopping remain active. Every movement still needs approval.
