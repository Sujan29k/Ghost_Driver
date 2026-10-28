"""Bounded, asynchronous local trial recording. Never records connection secrets."""
from datetime import datetime, timezone
from copy import deepcopy
import json
from pathlib import Path
import queue
import threading
import time
from uuid import uuid4


class TrialRecorder:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.worker = None
        self.active = False
        self.trial_id = None
        self.dropped = 0
        self.error = None
        self.save_frames = False
        self.frame_number = 0
        self.last_sample = 0

    def start(self, metadata, label='', save_frames=False, order=1):
        with self.lock:
            if self.active or (self.worker and self.worker.is_alive()):
                raise ValueError('Stop the current trial first')
            self.trial_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8]
            self.folder = self.root / self.trial_id
            self.folder.mkdir(parents=True)
            (self.folder / 'manifest.json').write_text(json.dumps({**metadata, 'trialId': self.trial_id,
                'label': label[:80], 'trialOrder': order, 'saveFrames': save_frames,
                'timing': 'senderMonotonicNs is the common event clock; browser/backend timestamps are separate clocks',
                'metricDefinition': 'unannotated BGR uint8; MAE, PSNR (null when identical), Gaussian 11x11 sigma=1.5 SSIM',
                'metricSampling': 'maximum 2 aligned sets/second; bounded worker, dropped jobs counted; independent of video transport',
                'simulationMode': 'asynchronous; seed is recorded, not a guarantee of determinism'}, indent=2))
            self.events, self.samples = queue.Queue(maxsize=2048), queue.Queue(maxsize=4)
            self.done = threading.Event()
            self.active, self.save_frames = True, save_frames
            self.dropped, self.error, self.frame_number, self.last_sample = 0, None, 0, 0
            self.worker = threading.Thread(target=self._write, name='trial-writer', daemon=True)
            self.worker.start()
            self.record('trial:start', {'label': label, 'order': order})
            return self.state()

    def state(self):
        with self.lock:
            return {'active': self.active, 'id': self.trial_id, 'dropped': self.dropped,
                    'error': self.error, 'saveFrames': self.save_frames}

    def record(self, kind, data):
        with self.lock:
            if not self.active:
                return
            row = {'kind': kind, 'senderMonotonicNs': time.monotonic_ns(),
                   'utc': datetime.now(timezone.utc).isoformat(), 'data': deepcopy(data)}
            try:
                self.events.put_nowait(row)
            except queue.Full:
                self.dropped += 1

    def frame(self, metrics, samples):
        with self.lock:
            if not self.active:
                return
            data = deepcopy(metrics)
            self.record('frame', data)
            if samples and time.monotonic() - self.last_sample >= .5:
                filename = f'frames-{self.frame_number:06d}.npz'
                try:
                    row = {'kind': 'frame:evaluation', 'senderMonotonicNs': time.monotonic_ns(),
                           'utc': datetime.now(timezone.utc).isoformat(), 'data': data}
                    self.samples.put_nowait((filename if self.save_frames else None, samples, row))
                    self.frame_number += 1
                    self.last_sample = time.monotonic()
                except queue.Full:
                    self.dropped += 1

    def _write(self):
        try:
            with (self.folder / 'events.jsonl').open('w', encoding='utf8') as output:
                while not self.done.is_set() or not self.events.empty() or not self.samples.empty():
                    try:
                        row = self.events.get(timeout=.1)
                        output.write(json.dumps(row, allow_nan=False) + '\n')
                    except queue.Empty:
                        pass
                    try:
                        name, arrays, row = self.samples.get_nowait()
                        import numpy as np
                        from comparison import image_metrics
                        # Raw arrays are owned by this frame job; overlays were drawn
                        # onto copies. The reference is identical for both metrics.
                        started = time.monotonic()
                        data = row['data']
                        data['metrics'] = {'delayed': image_metrics(arrays['delayed'], arrays['reference']),
                            'predicted': image_metrics(arrays['predicted'], arrays['reference']) if 'predicted' in arrays else None}
                        data['metricProcessingMs'] = (time.monotonic() - started) * 1000
                        if name:
                            data['sampleFile'] = name
                            alignment = {key: data.get(key) for key in ('epoch', 'revision', 'referenceFrame', 'delayedFrame',
                                'previousFrame', 'referenceTimestamp', 'delayedTimestamp', 'previousTimestamp', 'delayMs', 'horizonMs', 'intervalMs')}
                            np.savez_compressed(self.folder / name, **arrays, alignment=np.array(json.dumps(alignment)))
                        output.write(json.dumps(row, allow_nan=False) + '\n')
                    except queue.Empty:
                        pass
                    output.flush()
        except Exception as error:
            with self.lock:
                self.error = type(error).__name__
                self.active = False

    def stop(self):
        with self.lock:
            if self.worker is None:
                return self.state()
            self.record('trial:stop', {'dropped': self.dropped})
            self.active = False
            self.done.set()
            worker = self.worker
        worker.join(timeout=10)
        if worker.is_alive():
            raise RuntimeError('Trial writer is still flushing; wait before starting another trial')
        with self.lock:
            self.worker = None
        return self.state()
