"""YOLO from sudip-work, with optional Farneback motion visualization.

Inference runs in the bridge's dedicated worker, never in its control loop.
The image-area warning is advisory, not a distance estimate or driving policy.
"""
from pathlib import Path
import time
from prediction import check_checkpoint, DEFAULT_RAFT_WEIGHTS

DEFAULT_WEIGHTS = Path(__file__).parent / 'ghostdriver/yolov8n_coco128-5/weights/best.pt'
ROAD_CLASSES = {'car', 'truck', 'bus', 'person', 'bicycle', 'motorcycle'}


class Perception:
    def __init__(self, weights=DEFAULT_WEIGHTS, device='auto', confidence=0.4, flow=False,
                 prediction='off', prediction_ms=250, raft_weights=DEFAULT_RAFT_WEIGHTS, raft_iterations=12):
        from ultralytics import YOLO
        import cv2
        import numpy as np
        weights = check_checkpoint(weights)
        self.cv2, self.np = cv2, np
        self.model = YOLO(str(weights))
        self.device = None if device == 'auto' else device
        self.confidence, self.flow = confidence, flow
        self.previous_gray = None
        self.predictor = None
        if prediction != 'off':
            from prediction import PredictionView
            self.predictor = PredictionView(prediction, prediction_ms, raft_weights, device, raft_iterations)
        # Warm up before declaring the sender ready. Missing/incompatible models
        # fail explicitly rather than silently switching to unprocessed video.
        self.model.predict(np.zeros((360, 640, 3), dtype=np.uint8),
                           device=self.device, conf=confidence, verbose=False)

    def process(self, pixels, timestamp=None):
        cv2, np = self.cv2, self.np
        started = time.monotonic()
        result = self.model.predict(pixels, device=self.device,
                                    conf=self.confidence, verbose=False)[0]
        annotated = pixels.copy()
        count, warning = 0, False
        height, width = pixels.shape[:2]
        # Copy tensors to CPU once rather than synchronizing CUDA for every box.
        for box in result.boxes.data.cpu().tolist():
            x1, y1, x2, y2, confidence, class_id = box[:6]
            name = result.names[int(class_id)]
            if name not in ROAD_CLASSES:
                continue
            count += 1
            large = (x2 - x1) * (y2 - y1) / (height * width) > 0.05
            warning |= large
            color = (0, 80, 255) if large else (0, 255, 100)
            x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f'{name} {confidence:.2f}', (x1, max(18, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(annotated, f'YOLO | road objects: {count}', (12, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)
        if warning:
            cv2.putText(annotated, 'Large object in view - advisory', (12, 78),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 2)
        panels = [annotated]
        prediction_metrics = {'method': 'off', 'ready': False}
        if self.predictor is not None:
            predicted, prediction_metrics = self.predictor.process(
                pixels, time.monotonic() if timestamp is None else timestamp)
            panels.append(predicted)
        if self.flow:
            gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
            motion = np.zeros_like(pixels)
            if self.previous_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(self.previous_gray, gray, None,
                    pyr_scale=0.5, levels=3, winsize=15, iterations=3,
                    poly_n=5, poly_sigma=1.2, flags=0)
                magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                hsv = np.zeros_like(pixels)
                hsv[..., 0] = angle * 90 / np.pi
                hsv[..., 1] = 255
                hsv[..., 2] = np.clip(magnitude * 20, 0, 255)
                motion = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            self.previous_gray = gray
            cv2.putText(motion, 'Farneback motion (not future video)', (12, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            panels.append(motion)
        return np.hstack(panels), {'enabled': True, 'objects': count, 'warning': warning,
                           'inferenceMs': round((time.monotonic() - started) * 1000, 1),
                           'flow': self.flow, 'prediction': prediction_metrics}
