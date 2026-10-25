#!/usr/bin/env python3
"""CUDA RAFT inference worker for the Python 3.11 raft-env."""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
RAFT_ROOT = ROOT / "RAFT"
DEFAULT_CHECKPOINT = ROOT / "models" / "raft-small.pth"

import sys

sys.path.insert(0, str(RAFT_ROOT / "core"))
from raft import RAFT
from utils.utils import InputPadder


class RaftPredictor:
    def __init__(self, checkpoint: Path, iterations: int = 12) -> None:
        if not checkpoint.is_file():
            raise FileNotFoundError(f"RAFT checkpoint not found: {checkpoint}")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.iterations = iterations
        args = argparse.Namespace(
            small=True,
            mixed_precision=self.device.type == "cuda",
            alternate_corr=False,
            dropout=0.0,
        )
        model = torch.nn.DataParallel(RAFT(args))
        state = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
        model.load_state_dict(state)
        self.model = model.module.to(self.device).eval()
        self.lock = threading.Lock()

    def predict(
        self,
        previous: np.ndarray,
        current: np.ndarray,
        latency_ms: int,
        damping: float = 0.7,
        max_displacement: float = 80.0,
    ) -> Tuple[bytes, float]:
        started = time.perf_counter()
        if latency_ms <= 0:
            predicted = current.copy()
        else:
            first = cv2.cvtColor(current, cv2.COLOR_BGR2RGB)
            second = cv2.cvtColor(previous, cv2.COLOR_BGR2RGB)
            image1 = torch.from_numpy(first).permute(2, 0, 1).float()[None].to(self.device)
            image2 = torch.from_numpy(second).permute(2, 0, 1).float()[None].to(self.device)
            padder = InputPadder(image1.shape)
            image1, image2 = padder.pad(image1, image2)

            with self.lock, torch.inference_mode():
                _, flow_up = self.model(
                    image1,
                    image2,
                    iters=self.iterations,
                    test_mode=True,
                )

            flow_up = padder.unpad(flow_up)
            flow = flow_up[0].permute(1, 2, 0).float().cpu().numpy()
            steps = max(1, int(round(latency_ms / 100.0)))
            height, width = current.shape[:2]
            magnitude = np.sqrt((flow ** 2).sum(axis=-1, keepdims=True))
            flow *= np.minimum(
                1.0,
                (max_displacement / steps) / np.maximum(magnitude, 1e-6),
            )
            grid_x, grid_y = np.meshgrid(
                np.arange(width, dtype=np.float32),
                np.arange(height, dtype=np.float32),
            )
            map_x = grid_x + damping * flow[..., 0]
            map_y = grid_y + damping * flow[..., 1]
            predicted = current
            for _ in range(steps):
                predicted = cv2.remap(
                    predicted,
                    map_x,
                    map_y,
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )

        success, encoded = cv2.imencode(
            ".jpg",
            predicted,
            [cv2.IMWRITE_JPEG_QUALITY, 75],
        )
        if not success:
            raise RuntimeError("Could not encode predicted frame")
        return encoded.tobytes(), (time.perf_counter() - started) * 1000.0


class RaftHandler(BaseHTTPRequestHandler):
    predictor: RaftPredictor

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        payload = {
            "ready": True,
            "model": "raft-small",
            "device": str(self.server.predictor.device),
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/predict":
            self.send_error(404)
            return

        try:
            previous_size = int(self.headers["X-Previous-Size"])
            latency_ms = max(0, min(800, int(self.headers["X-Latency-Ms"])))
            body = self.rfile.read(int(self.headers["Content-Length"]))
            previous = cv2.imdecode(
                np.frombuffer(body[:previous_size], dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            current = cv2.imdecode(
                np.frombuffer(body[previous_size:], dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if previous is None or current is None:
                raise ValueError("Invalid JPEG frame pair")

            jpeg, inference_ms = self.server.predictor.predict(
                previous,
                current,
                latency_ms,
            )
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("X-Inference-Ms", f"{inference_ms:.1f}")
            self.end_headers()
            self.wfile.write(jpeg)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_self_test(predictor: RaftPredictor) -> None:
    previous = np.zeros((64, 64, 3), dtype=np.uint8)
    current = previous.copy()
    current[16:40, 16:40] = 255
    jpeg, inference_ms = predictor.predict(previous, current, 200)
    print(
        json.dumps(
            {
                "ok": len(jpeg) > 0,
                "model": "raft-small",
                "device": str(predictor.device),
                "inferenceMs": round(inference_ms, 1),
                "jpegBytes": len(jpeg),
            }
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="GhostDriver RAFT inference worker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    predictor = RaftPredictor(args.checkpoint, args.iterations)
    if args.self_test:
        run_self_test(predictor)
        return

    server = ThreadingHTTPServer((args.host, args.port), RaftHandler)
    server.predictor = predictor
    print(
        f"[raft] raft-small ready on {args.host}:{args.port} ({predictor.device})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
