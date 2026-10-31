"""Check model inference and CARLA connectivity without spawning or driving actors."""
import argparse
import os
from pathlib import Path
import sys


def main():
    if '--help' not in sys.argv and '-h' not in sys.argv:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-only', action='store_true', help='Skip CARLA client/server checks')
    parser.add_argument('--prediction', choices=['off', 'raft', 'farneback'], default=os.getenv('PREDICTION', 'off'))
    parser.add_argument('--device', default=os.getenv('AI_DEVICE', 'auto'))
    parser.add_argument('--image', type=Path, help='Optional saved camera image for a real detection check')
    parser.add_argument('--output', type=Path, help='Save the annotated test image')
    parser.add_argument('--host', default=os.getenv('CARLA_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=os.getenv('CARLA_PORT', '2000'))
    args = parser.parse_args()
    if args.prediction not in ('off', 'raft', 'farneback'):
        parser.error('PREDICTION must be off, raft or farneback')
    try:
        if sys.version_info < (3, 10):
            raise RuntimeError('Use Python 3.10+ with a matching CARLA client; the old Python 3.7 environment is incompatible.')
        import cv2
        import numpy as np
        import torch
        import aiortc, socketio, dotenv, certifi  # Verify sender dependencies too.
        from perception import Perception
        print(f'Python {sys.version.split()[0]} | torch {torch.__version__} | CUDA available: {torch.cuda.is_available()}')
        model = Perception(device=args.device, prediction=args.prediction)
        print('YOLO checkpoint classes:', model.model.names)
        pixels = cv2.imread(str(args.image)) if args.image else np.zeros((360, 640, 3), dtype=np.uint8)
        if pixels is None:
            raise ValueError(f'Cannot read image: {args.image}')
        pixels = cv2.resize(pixels, (640, 360))
        model.process(pixels, timestamp=0.0)
        output, metrics = model.process(pixels, timestamp=0.1)
        print(f'YOLO checkpoint loaded; road objects: {metrics["objects"]}; processing: {metrics["inferenceMs"]} ms')
        if args.prediction != 'off':
            if not metrics['prediction']['ready']:
                raise RuntimeError('Prediction did not produce a frame')
            print(f'{args.prediction.upper()} inference passed; output shape: {output.shape}')
        if args.output:
            if not cv2.imwrite(str(args.output), output):
                raise RuntimeError(f'Could not write {args.output}')
            print(f'Saved {args.output}')
        if not args.models_only:
            import carla
            client = carla.Client(args.host, args.port)
            client.set_timeout(10.0)
            client_version, server_version = client.get_client_version(), client.get_server_version()
            from carla_compat import validate_versions
            validate_versions(client_version, server_version, os.getenv('RESEARCH_ENABLED', 'true').lower() == 'true')
            world = client.get_world()
            settings = world.get_settings()
            if settings.synchronous_mode or settings.no_rendering_mode:
                raise RuntimeError('Use an asynchronous CARLA world with rendering enabled.')
            print(f'CARLA {server_version} ready | map: {world.get_map().name}')
        print('Checks passed. Live camera, traffic and remote video still require running bridge.py.')
    except Exception as exc:
        print(f'Setup check failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
