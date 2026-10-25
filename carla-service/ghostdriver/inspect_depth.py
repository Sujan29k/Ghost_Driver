"""
Diagnostic montage for the geometric warp (needs evaluate_geometric.py in the same folder).

Top row   : RGB at t | depth at t (colour, log scale; sky = dark) | real RGB at t+k
Bottom row: oracle warp (true pose + true depth) | repeat | |oracle - real| error (hot = large)

Usage:
    python inspect_depth.py --data dataset_v5/Town03 --condition heavy_rain --k 12
    python inspect_depth.py --data dataset_v5/Town03 --condition clear_traffic --k 12 --index 150
Output: inspect_<condition>_k<k>_i<index>.png in the current folder.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from evaluate_geometric import geometric_warp, load_segments, read_depth


def colour_depth(d):
    d = np.clip(d, 0.5, 200.0)
    norm = (np.log(d) - np.log(0.5)) / (np.log(200.0) - np.log(0.5))
    img = cv2.applyColorMap((255 * (1 - norm)).astype(np.uint8), cv2.COLORMAP_TURBO)
    img[read_unclipped_sky(d)] = 0
    return img


def read_unclipped_sky(d):
    return d >= 199.9


def label(img, text):
    out = img.copy()
    cv2.putText(out, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset_v5/Town03")
    ap.add_argument("--condition", default="heavy_rain")
    ap.add_argument("--k", type=int, default=12, help="frames ahead (5 = 200 ms, 12 = 500 ms, 20 = 800 ms)")
    ap.add_argument("--index", type=int, default=100, help="position inside the longest segment")
    args = ap.parse_args()

    segments = load_segments(Path(args.data) / args.condition)
    seg = max(segments, key=len)
    i = min(args.index, len(seg) - args.k - 1)
    if i < 1:
        raise SystemExit("Longest segment is too short for k=%d." % args.k)
    cur = cv2.imread(str(seg[i]["rgb"]))
    real = cv2.imread(str(seg[i + args.k]["rgb"]))
    depth = read_depth(seg[i]["depth"])
    pred = geometric_warp(cur, depth, seg[i]["pose"], seg[i + args.k]["pose"])
    err = np.abs(pred.astype(np.float32) - real.astype(np.float32)).mean(axis=2)
    err_img = cv2.applyColorMap(np.clip(err * 4, 0, 255).astype(np.uint8), cv2.COLORMAP_HOT)

    print("segment length %d, position %d, k=%d" % (len(seg), i, args.k))
    print("depth (m): min %.2f  median %.2f  max %.1f  | fraction >= 200 m: %.2f"
          % (depth.min(), np.median(depth), depth.max(), float((depth >= 200).mean())))
    top = np.hstack([label(cur, "RGB t"), label(colour_depth(depth), "depth t"), label(real, "real t+%d" % args.k)])
    bottom = np.hstack([label(pred, "oracle warp"), label(cur, "repeat"), label(err_img, "oracle error")])
    name = "inspect_%s_k%d_i%d.png" % (args.condition, args.k, i)
    cv2.imwrite(name, np.vstack([top, bottom]))
    print("saved", name)


if __name__ == "__main__":
    main()python inspect_depth.py --data dataset_v5/Town03 --condition heavy_rain --k 12
python inspect_depth.py --data dataset_v5/Town03 --condition clear_traffic --k 12