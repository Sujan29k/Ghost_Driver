"""Compatibility entry point: use the unified authenticated WebRTC bridge.

The original sudip-work script is preserved in Git history. Its YOLO weights,
traffic spawning and motion view now run through bridge.py instead of a second
local OpenCV window and independent autopilot controller.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import main

if __name__ == '__main__':
    main()
