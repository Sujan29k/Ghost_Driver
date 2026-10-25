# CARLA sender

Use **[the GPU computer setup guide](../docs/FRIEND_SETUP.md)** for installation, matching the CARLA Python client, configuration, and startup commands.

`bridge.py` is the live CARLA/aiortc sender. `control_state.py` implements its independent braking watchdog. The `ghostdriver/` folder contains earlier research scripts and is not used by the live video connection.

Local safety checks without CARLA:

```sh
python3 -m unittest discover -s carla-service/tests -v
python3 bridge.py --help
```

Run the unittest command from the repository root; run the help command from this folder. Real CARLA camera/spawn/cleanup and cross-network TURN behavior still require the GPU computer and external service credentials.
