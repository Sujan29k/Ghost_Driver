"""Optional motion extrapolation adapted from sudip-work's RAFT worker.

The preview estimates a future image; it never controls the vehicle. Frame-pair
timing comes from CARLA timestamps, not an assumed camera or inference FPS.
"""
import argparse
from functools import lru_cache
import logging
import math
from pathlib import Path
import time

DEFAULT_RAFT_WEIGHTS = Path(__file__).parent / 'ghostdriver/models/raft-small.pth'


@lru_cache(maxsize=4)
def sampling_grid(height, width):
    import numpy as np
    return np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))


def warp_flow(current, flow, interval, horizon_ms, motion_scale=0.7, max_displacement=80):
    """Shared live/offline extrapolation; return image and fraction of capped pixels."""
    import cv2
    import numpy as np
    if not 0 < interval <= 1 or not 0 <= horizon_ms <= 2000:
        raise ValueError('Invalid timestamped prediction pair')
    if not math.isfinite(motion_scale) or motion_scale < 0:
        raise ValueError('Motion scale must be finite and nonnegative')
    if max_displacement is not None and (not math.isfinite(max_displacement) or max_displacement <= 0):
        raise ValueError('Displacement cap must be positive or None')
    if flow.shape != (*current.shape[:2], 2) or not np.isfinite(flow).all():
        raise ValueError('Invalid motion field')
    displacement = flow * (horizon_ms / 1000 / interval) * motion_scale
    magnitude = np.linalg.norm(displacement, axis=2, keepdims=True)
    capped = 0.0
    if max_displacement is not None:
        capped = float(np.mean(magnitude > max_displacement))
        displacement *= np.minimum(1.0, max_displacement / np.maximum(magnitude, 1e-6))
    height, width = current.shape[:2]
    gx, gy = sampling_grid(height, width)
    output = cv2.remap(current, gx + displacement[..., 0], gy + displacement[..., 1],
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return output, capped


def check_checkpoint(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Model checkpoint missing: {path}')
    with path.open('rb') as checkpoint:
        if checkpoint.read(80).startswith(b'version https://git-lfs.github.com/spec'):
            raise ValueError(f'{path} is a Git LFS pointer, not model weights. Download the actual checkpoint.')
    return path


class RaftFlow:
    def __init__(self, weights=DEFAULT_RAFT_WEIGHTS, device='auto', iterations=12):
        import cv2
        import numpy as np
        import torch
        from vendor.raft.raft import RAFT
        from vendor.raft.utils.utils import InputPadder

        self.cv2, self.torch, self.padder = cv2, torch, InputPadder
        if device == 'auto':
            device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        elif str(device).isdigit():
            device = f'cuda:{device}'
        self.device = torch.device(device)
        self.iterations = iterations
        args = argparse.Namespace(small=True, mixed_precision=False,
                                  alternate_corr=False, dropout=0.0)
        self.model = RAFT(args)
        state = torch.load(str(check_checkpoint(weights)), map_location='cpu', weights_only=True)
        self.model.load_state_dict({key.removeprefix('module.'): value for key, value in state.items()})
        self.model.to(self.device).eval()
        logging.getLogger('ghostdriver').info('RAFT-Small device: %s; refinement iterations: %d', self.device, iterations)
        # At least 128px per dimension: the coarsest correlation grid must have
        # more than one cell to avoid division by zero in bilinear sampling.
        self(np.zeros((128, 128, 3), dtype=np.uint8), np.zeros((128, 128, 3), dtype=np.uint8))

    def __call__(self, previous, current):
        cv2, torch = self.cv2, self.torch
        height, width = current.shape[:2]
        scale = min(1.0, 320 / width)
        size = (max(128, round(width * scale)), max(128, round(height * scale)))
        def tensor(pixels):
            rgb = cv2.cvtColor(cv2.resize(pixels, size), cv2.COLOR_BGR2RGB)
            return torch.from_numpy(rgb).permute(2, 0, 1).float()[None].to(self.device)
        # Backward flow (current -> previous) is the sampling displacement for
        # extrapolating current pixels forward, as in sudip-work/raft_worker.py.
        first, second = tensor(current), tensor(previous)
        padder = self.padder(first.shape)
        first, second = padder.pad(first, second)
        with torch.inference_mode():
            _, flow = self.model(first, second, iters=self.iterations, test_mode=True)
        flow = padder.unpad(flow)[0].permute(1, 2, 0).float().cpu().numpy()
        flow = cv2.resize(flow, (width, height))
        flow[..., 0] *= width / size[0]
        flow[..., 1] *= height / size[1]
        return flow


class PredictionView:
    def __init__(self, method='raft', horizon_ms=250, weights=DEFAULT_RAFT_WEIGHTS, device='auto', iterations=12):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        self.method, self.horizon_ms = method, horizon_ms
        self.previous, self.previous_at = None, None
        self.flow = RaftFlow(weights, device, iterations) if method == 'raft' else self.farneback

    def farneback(self, previous, current):
        cv2 = self.cv2
        return cv2.calcOpticalFlowFarneback(
            cv2.cvtColor(current, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), None,
            0.5, 3, 15, 3, 5, 1.2, 0)

    def predict_pair(self, previous, current, interval, horizon_ms):
        cv2, np = self.cv2, self.np
        if previous.shape != current.shape or not 0 < interval <= 1 or not 0 <= horizon_ms <= 2000:
            raise ValueError('Invalid timestamped prediction pair')
        if horizon_ms == 0:
            return current.copy()
        flow = self.flow(previous, current)
        if not np.isfinite(flow).all():
            raise RuntimeError('Motion model returned non-finite flow')
        return warp_flow(current, flow, interval, horizon_ms)[0]

    def process(self, current, timestamp):
        cv2, np = self.cv2, self.np
        started = time.monotonic()
        interval = timestamp - self.previous_at if self.previous_at is not None else 0
        ready = (self.previous is not None and self.previous.shape == current.shape
                 and math.isfinite(interval) and 0 < interval <= 1)
        predicted = current.copy()
        if ready:
            flow = self.flow(self.previous, current)
            if not np.isfinite(flow).all():
                raise RuntimeError('Motion model returned non-finite flow')
            predicted = warp_flow(current, flow, interval, self.horizon_ms)[0]
        self.previous, self.previous_at = current.copy(), timestamp
        label = f'{self.method.upper()} estimate +{self.horizon_ms} ms' if ready else 'Prediction buffering'
        cv2.putText(predicted, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.putText(predicted, 'ESTIMATED VIEW', (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        return predicted, {'method': self.method, 'ready': ready, 'horizonMs': self.horizon_ms,
                           'inferenceMs': round((time.monotonic() - started) * 1000, 1)}
