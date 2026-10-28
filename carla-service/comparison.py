"""Time-aligned video experiment. Predictor inputs never include the reference."""
from collections import deque
from dataclasses import dataclass
import math
import threading
import time

DELAYS = (0, 100, 200, 500, 800)
VIEWS = ('compare', 'delayed', 'predicted', 'reference')


@dataclass(frozen=True)
class Observation:
    timestamp: float
    frame_id: int
    value: object
    captured_at: float
    size: int = 0


class FrameHistory:
    def __init__(self, max_frames=90, max_bytes=128 * 1024 * 1024):
        self.frames = deque()
        self.max_frames, self.max_bytes = max_frames, max_bytes
        self.bytes = 0
        self.epoch = 0
        self.lock = threading.Lock()

    def clear(self):
        with self.lock:
            self.frames.clear()
            self.bytes = 0
            self.epoch += 1

    def append(self, observation):
        if not math.isfinite(observation.timestamp):
            return
        with self.lock:
            if self.frames and (observation.timestamp <= self.frames[-1].timestamp
                                or observation.timestamp - self.frames[-1].timestamp > 1):
                self.frames.clear()
                self.bytes = 0
                self.epoch += 1
            self.frames.append(observation)
            self.bytes += observation.size
            while self.frames and (len(self.frames) > self.max_frames or self.bytes > self.max_bytes):
                self.bytes -= self.frames.popleft().size

    def select(self, delay_ms, with_epoch=False):
        with self.lock:
            if not self.frames:
                return None
            reference = self.frames[-1]
            cutoff = reference.timestamp - delay_ms / 1000
            index = next((i for i in range(len(self.frames) - 1, -1, -1)
                          if self.frames[i].timestamp <= cutoff + 1e-9), None)
            if index is None:
                return None
            selected = (self.frames[index - 1] if index > 0 else None, self.frames[index], reference)
            return (*selected, self.epoch) if with_epoch else selected


def image_metrics(candidate, reference):
    """Full-image MAE/PSNR and local Gaussian-window SSIM, before HUD/boxes."""
    import cv2
    import numpy as np
    if candidate.shape != reference.shape:
        raise ValueError('Metric images must have matching shapes')
    a, b = candidate.astype(np.float64), reference.astype(np.float64)
    mse = float(np.mean((a - b) ** 2))
    mu_a, mu_b = cv2.GaussianBlur(a, (11, 11), 1.5), cv2.GaussianBlur(b, (11, 11), 1.5)
    var_a = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a * mu_a
    var_b = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b * mu_b
    cov = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_a * mu_b
    ssim = ((2 * mu_a * mu_b + 6.5025) * (2 * cov + 58.5225) /
            ((mu_a * mu_a + mu_b * mu_b + 6.5025) * (var_a + var_b + 58.5225)))
    return {'mae': float(np.mean(np.abs(a - b))),
            'psnr': None if mse == 0 else float(10 * math.log10(255 ** 2 / mse)),
            'identical': mse == 0, 'ssim': float(np.mean(ssim))}


class ComparisonPipeline:
    def __init__(self, device='auto', raft_weights=None, delay_ms=200, method='raft', view='compare', reference=False):
        self.history = FrameHistory()
        self.device, self.raft_weights = device, raft_weights
        self.predictors = {}
        self.lock = threading.Lock()
        self.revision = 0
        self.settings = {}
        self.configure(delay_ms, method, view, reference)

    def configure(self, delay_ms, method, view, reference=False):
        if type(delay_ms) is not int or delay_ms not in DELAYS:
            raise ValueError('Delay must be 0, 100, 200, 500 or 800 ms')
        if method not in ('off', 'raft', 'farneback') or view not in VIEWS or type(reference) is not bool:
            raise ValueError('Invalid video comparison configuration')
        with self.lock:
            self.settings = {'delayMs': delay_ms, 'method': method, 'view': view, 'reference': reference}
            self.revision += 1
            self.history.clear()

    def configuration(self):
        with self.lock:
            return dict(self.settings)

    def is_current(self, details):
        with self.lock, self.history.lock:
            return (details.get('revision') == self.revision and details.get('epoch') == self.history.epoch
                    and time.monotonic() - details.get('sourceCapturedAt', 0) < 2)

    def report(self, details):
        """Age status even while a slow inference call has not returned yet."""
        if details and details.get('status') == 'ready' and not self.is_current(details):
            status = 'stale' if time.monotonic() - details.get('sourceCapturedAt', 0) >= 2 else 'buffering'
            return {**details, 'status': status, 'predictionReady': False, 'predictionStatus': status}
        return details

    def process(self, annotate=None, evaluate=False):
        import cv2
        import numpy as np
        from prediction import PredictionView
        started = time.monotonic()
        with self.lock:
            settings, revision = dict(self.settings), self.revision
        selected = self.history.select(settings['delayMs'], with_epoch=True)
        details = {**settings, 'revision': revision, 'status': 'buffering', 'predictionReady': False}
        if selected is None:
            return None, details, None, {'enabled': False}
        previous, delayed, reference, epoch = selected
        details['epoch'] = epoch
        if time.monotonic() - reference.captured_at >= 2:
            return None, {**details, 'status': 'stale'}, None, {'enabled': False}

        def pixels(item):
            if isinstance(item.value, np.ndarray):
                return item.value.copy()
            image = item.value
            return np.frombuffer(image.raw_data, np.uint8).reshape(image.height, image.width, 4)[:, :, :3].copy()

        current, baseline = pixels(reference), pixels(delayed)
        horizon = max(0.0, (reference.timestamp - delayed.timestamp) * 1000)
        interval = delayed.timestamp - previous.timestamp if previous else None
        details.update(referenceFrame=reference.frame_id, delayedFrame=delayed.frame_id,
                       previousFrame=previous.frame_id if previous else None,
                       referenceTimestamp=reference.timestamp, delayedTimestamp=delayed.timestamp,
                       previousTimestamp=previous.timestamp if previous else None,
                       intervalMs=interval * 1000 if interval is not None else None,
                       horizonMs=horizon, sourceCapturedAt=reference.captured_at,
                       status='ready', predictionMs=0.0, predictionStatus='off')
        predicted = None
        need_prediction = settings['view'] in ('compare', 'predicted') and settings['method'] != 'off'
        if need_prediction:
            if horizon <= 1e-6:
                predicted = baseline.copy()
            elif previous is not None and 0 < interval <= 1:
                try:
                    method = settings['method']
                    if method not in self.predictors:
                        kwargs = {'device': self.device}
                        if self.raft_weights is not None:
                            kwargs['weights'] = self.raft_weights
                        self.predictors[method] = PredictionView(method, **kwargs)
                    predict_started = time.monotonic()
                    predicted = self.predictors[method].predict_pair(pixels(previous), baseline, interval, horizon)
                    details['predictionMs'] = (time.monotonic() - predict_started) * 1000
                except Exception as error:
                    # A failed estimate is never silently replaced by the reference.
                    details['predictionStatus'] = 'unavailable: ' + type(error).__name__
            else:
                details['predictionStatus'] = 'buffering'
        if predicted is not None:
            details.update(predictionReady=True, predictionStatus='ready')

        samples = None
        if evaluate:
            # The recorder computes metrics on its bounded worker queue. Neither
            # the baseline nor inference waits for SSIM or image compression.
            samples = {'reference': current, 'delayed': baseline}
            if predicted is not None:
                samples['predicted'] = predicted
        metrics = {'enabled': False}
        if annotate:
            # Detection operates on the delayed observation, never leaks reference pixels.
            annotated, metrics = annotate(baseline, timestamp=delayed.timestamp)
        else:
            annotated = baseline.copy()

        def label(image, title, line):
            image = image.copy()
            cv2.rectangle(image, (0, 0), (image.shape[1], 42), (12, 16, 20), -1)
            cv2.putText(image, title, (8, 17), cv2.FONT_HERSHEY_SIMPLEX, .45, (80, 240, 240), 1)
            cv2.putText(image, line, (8, 34), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1)
            return image

        delayed_view = label(annotated, 'DELAYED - NO PREDICTION', f'Injected {settings["delayMs"]} ms | source #{delayed.frame_id}')
        predicted_view = label(predicted if predicted is not None else np.zeros_like(baseline),
            'PREDICTED - ESTIMATED VIEW', f'{settings["method"].upper()} | +{horizon:.0f} ms | {details["predictionStatus"]}')
        reference_view = label(current, 'VEHICLE REFERENCE', 'Newest at sender; also has transmission delay')
        if settings['view'] == 'compare':
            panels = [delayed_view, predicted_view]
            if settings['reference']:
                panels.append(reference_view)
        else:
            panels = [{'delayed': delayed_view, 'predicted': predicted_view, 'reference': reference_view}[settings['view']]]
        details['processingMs'] = (time.monotonic() - started) * 1000
        if not self.is_current(details):
            return None, {**details, 'status': 'stale-or-reset'}, None, metrics
        # Predicted-only cannot authorize driving on a placeholder.
        if settings['view'] == 'predicted' and predicted is None:
            return None, {**details, 'status': 'unavailable'}, samples, metrics
        return np.hstack(panels), details, samples, metrics
