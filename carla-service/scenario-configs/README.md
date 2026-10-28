# Scenario preset configurations

The dashboard starts these named presets dynamically against the currently loaded map. The sender records the resolved map, ego spawn, route points, hazard location, weather values, friction trigger, actor blueprints, traffic counts, seed, and active takeover policy in each trial manifest. Presets use the running map's roads; coordinates are resolved at runtime because a Town01 coordinate is invalid on a different map.

All asynchronous runs are reproducible only as recorded configurations, not bit-for-bit deterministic. These JSON files are experiment plans and document the supported effects and expected behavior.
