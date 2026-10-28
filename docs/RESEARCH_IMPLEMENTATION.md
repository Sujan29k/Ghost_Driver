# Research platform implementation

Extend the existing authenticated two-computer application. Implementation order:

1. Sequenced reverse/direction and explicit driving authority, with local safety stops.
2. Timestamped delayed-frame selection, prediction without future-frame input, and aligned metrics.
3. Acknowledged operator commands, supervised autonomy, route selection and takeover policy.
4. Owned scenario actors, weather/friction restoration and honest hazard approximations.
5. Dashboard controls, bounded trial recording, evaluation and sender packaging.

Live CARLA version is checked on sender startup. This workspace has no remote
GPU-computer access; tests here use the actual transport/models where possible
and explicitly identified CARLA fixtures. CARLA 0.9.15 API documentation is the
compatibility baseline. Do not restart active live services or push to GitHub
as part of implementation.

The sender UI operations are serialized on a dedicated worker so CARLA RPC and
image inference never occupy the actuator loop. Autonomy uses the 0.9.15
Traffic Manager `set_path` API, while the control loop applies commands only in
manual/stopped modes. The initial takeover fallback is a latched brake. Local
trial events use the sender monotonic clock; browser/backend clock values remain
separate fields. Custom map source-building is not part of this integration.
