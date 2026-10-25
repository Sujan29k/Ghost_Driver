"""
GhostDriver - geometric (depth + ego-pose) future-frame prediction vs flow warping.

Needs data from collect_data_v5.py (depth PNGs + camera pose in metadata.csv).

Math (camera axes as in CARLA: x forward, y right, z up; M = 4x4 camera-to-world pose):
    back-project   P  = ( d , (u-cx)*d/f , -(v-cy)*d/f )            f = (W/2)/tan(FOV/2)
    to world       Pw = M_src @ P
    pose forecast  M_(t+k) = M_t @ (M_(t-1)^-1 @ M_t)^k             (constant speed + yaw rate)
    re-project     P' = M_tgt^-1 @ Pw ;  u' = cx + f*Y'/X' ,  v' = cy - f*Z'/X'
The image is rendered by splatting depth into the target view (z-buffer), closing small holes,
then sampling the source image at the re-projected coordinates (no holes in the output).
Static-world assumption: moving vehicles are NOT handled by this model.

Methods:
    repeat          the current frame
    repeat_blur     the current frame, Gaussian-blurred (control: PSNR/SSIM can reward blur)
    farneback       stepwise Farneback flow warp (same as evaluate_prediction.py)
    geo_oracle      true depth + TRUE future pose   (upper bound / sanity check, not a forecast)
    geo_const       true depth + constant-twist pose forecast
    geo_ground      ground-plane depth (no depth sensor) + constant-twist pose forecast

Usage:
    python evaluate_geometric.py --selftest
    python evaluate_geometric.py --data dataset_v5/Town03 --stride 25
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

W, H, FOV = 640, 480, 90.0
F = (W / 2.0) / np.tan(np.radians(FOV / 2.0))
CX, CY = W / 2.0, H / 2.0
CAM_HEIGHT = 1.5
FRAME_MS = 40.0
POSE_COLS = ["m%d%d" % (r, c) for r in range(3) for c in range(4)]
_U, _V = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
_CLOSE_KERNEL = np.ones((5, 5), np.uint8)


# ----------------------------- geometry -----------------------------
def to_cam(depth):
    """Depth map (H x W, metres along the camera axis) -> homogeneous camera points (4 x N)."""
    X = depth.reshape(-1).astype(np.float64)
    Y = ((_U - CX) / F).reshape(-1) * X
    Z = (-(_V - CY) / F).reshape(-1) * X
    return np.stack([X, Y, Z, np.ones_like(X)])


def project(P):
    X = P[0]
    safe = np.where(X > 1e-6, X, 1e-6)
    return CX + F * P[1] / safe, CY - F * P[2] / safe


def extrapolate_pose(M_prev, M_cur, k):
    """Constant-twist forecast: M_(t+k) = M_t (M_(t-1)^-1 M_t)^k."""
    rel = np.linalg.inv(M_prev) @ M_cur
    M = M_cur.copy()
    for _ in range(k):
        M = M @ rel
    return M


def geometric_warp(src, depth_src, M_src, M_tgt, far=200.0):
    """Render the scene seen from M_src (image + depth) as it would look from M_tgt."""
    Pw = M_src @ to_cam(depth_src)
    Pt = np.linalg.inv(M_tgt) @ Pw
    u, v = project(Pt)
    X = Pt[0]
    ui, vi = np.rint(u).astype(np.int64), np.rint(v).astype(np.int64)
    ok = (X > 0.3) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)

    # depth seen from the target camera: splat with a z-buffer (nearest wins), then close holes
    idx, z = vi[ok] * W + ui[ok], X[ok]
    order = np.argsort(-z)                       # far first, so the nearest point is written last
    zbuf = np.zeros(H * W, np.float32)
    zbuf[idx[order]] = z[order]
    zbuf = cv2.morphologyEx(zbuf.reshape(H, W), cv2.MORPH_CLOSE, _CLOSE_KERNEL)
    zbuf[zbuf <= 0] = far

    # for every target pixel: where was that surface point in the source image?
    Pt_cam = to_cam(zbuf)
    Ps = np.linalg.inv(M_src) @ (M_tgt @ Pt_cam)
    us, vs = project(Ps)
    bad = Ps[0] <= 0.1
    us[bad], vs[bad] = -1.0, -1.0
    return cv2.remap(src, us.reshape(H, W).astype(np.float32), vs.reshape(H, W).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def depth_ground(far=60.0, max_d=80.0):
    """Sensor-free depth: flat road below the horizon, a constant far depth above it."""
    d = np.full((H, W), far, np.float32)
    below = _V > CY + 2
    d[below] = np.minimum(F * CAM_HEIGHT / (_V[below] - CY), max_d)
    return d


# ----------------------------- metrics and flow baseline (self-contained) -----------------------------
def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 100.0 if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))


def ssim(a, b):
    """Mean SSIM on grayscale, 11x11 Gaussian window (standard constants)."""
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float64)
    b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)
    mu_a, mu_b = blur(a), blur(b)
    var_a, var_b = blur(a * a) - mu_a ** 2, blur(b * b) - mu_b ** 2
    cov = blur(a * b) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2))
    return float(s.mean())


def predict_flow_farneback(prev, cur):
    """Flow from the current frame to the previous one (pixels)."""
    g0 = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    g1 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(g0, g1, None, pyr_scale=0.5, levels=3, winsize=15,
                                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


WARP_CFG = {"damping": 0.7, "max_disp": 80.0}


def warp_forward(cur, flow, k):
    """Stepwise flow warp (the baseline from evaluate_prediction.py): apply the flow k times."""
    flow = flow.astype(np.float32)
    if WARP_CFG["max_disp"] > 0:
        mag = np.sqrt((flow ** 2).sum(axis=-1, keepdims=True))
        flow = flow * np.minimum(1.0, (WARP_CFG["max_disp"] / float(k)) / np.maximum(mag, 1e-6))
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    mx, my = gx + WARP_CFG["damping"] * flow[..., 0], gy + WARP_CFG["damping"] * flow[..., 1]
    img = cur
    for _ in range(k):
        img = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return img


# ----------------------------- data -----------------------------
def read_depth(path):
    d = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    return None if d is None else d.astype(np.float32) / 100.0     # centimetres -> metres


def pose_from_row(row):
    M = np.eye(4)
    vals = [float(row[c]) for c in POSE_COLS]
    M[:3, :4] = np.array(vals).reshape(3, 4)
    return M


def load_segments(cond_dir):
    rows = list(csv.DictReader((cond_dir / "metadata.csv").open(newline="", encoding="utf-8")))
    if not rows or "depth_file" not in rows[0] or POSE_COLS[0] not in rows[0]:
        raise SystemExit("%s has no depth/pose columns. Collect with collect_data_v5.py." % cond_dir)
    by_seg = defaultdict(list)
    for r in rows:
        by_seg[int(r["segment_id"])].append(dict(
            frame=int(r["frame_id"]), rgb=cond_dir / "rgb" / r["filename"],
            depth=cond_dir / "depth" / r["depth_file"], pose=pose_from_row(r)))
    segments = []
    for sid in sorted(by_seg):
        items = sorted(by_seg[sid], key=lambda x: x["frame"])
        cur = [items[0]]
        for it in items[1:]:
            if it["frame"] == cur[-1]["frame"] + 1:
                cur.append(it)
            else:
                segments.append(cur)
                cur = [it]
        segments.append(cur)
    return segments


# ----------------------------- self-test -----------------------------
def _render(M, texture_seed=0):
    """Ray-cast a synthetic scene (textured ground z=0 and a wall at x=40) from pose M."""
    r = np.stack([np.ones_like(_U), (_U - CX) / F, -(_V - CY) / F]).reshape(3, -1)
    d = M[:3, :3] @ r
    o = M[:3, 3:4]
    with np.errstate(divide="ignore", invalid="ignore"):
        t_ground = np.where(d[2] < -1e-9, -o[2] / d[2], np.inf)
        t_wall = np.where(d[0] > 1e-9, (40.0 - o[0]) / d[0], np.inf)
    t = np.minimum(t_ground, t_wall)
    t[t <= 0] = np.inf
    hit = o + d * np.where(np.isfinite(t), t, 0)
    ground = t_ground <= t_wall
    # smooth (band-limited) textures, so the test measures the warp and not aliasing of hard edges
    g = 128 + 50 * np.sin(hit[0] * 1.3) * np.cos(hit[1] * 1.1) + 40 * np.sin(hit[0] * 0.5 + hit[1] * 0.7)
    wl = 128 + 60 * np.sin(hit[1] * 0.9) * np.cos(hit[2] * 1.2)
    val = np.where(ground, g, wl)
    val = np.where(np.isfinite(t), val, 200)
    img = np.clip(np.stack([val, val * 0.8 + 20, val * 0.6 + 40], axis=-1), 0, 255)
    depth = np.where(np.isfinite(t), t, 655.0)          # camera-axis depth (ray has x component 1)
    return img.reshape(H, W, 3).astype(np.uint8), depth.reshape(H, W).astype(np.float32)


def _pose(x, y, z, yaw_deg):
    c, s = np.cos(np.radians(yaw_deg)), np.sin(np.radians(yaw_deg))
    M = np.eye(4)
    M[:3, :3] = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    M[:3, 3] = [x, y, z]
    return M


def selftest():
    print("Self-test on a synthetic scene (checks the math, not CARLA's conventions).")
    M0 = _pose(0, 0, CAM_HEIGHT, 0)
    img0, dep0 = _render(M0)
    for name, (dx, yaw) in {"1.5 m forward": (1.5, 0), "4 m forward + 4 deg yaw": (4.0, 4.0)}.items():
        Mt = _pose(dx, 0.3 * dx * np.sin(np.radians(yaw)), CAM_HEIGHT, yaw)
        truth, _ = _render(Mt)
        pred = geometric_warp(img0, dep0, M0, Mt)
        print("  %-26s repeat %.2f dB | geometric warp %.2f dB"
              % (name, psnr(img0, truth), psnr(pred, truth)))
    # constant-twist pose forecast: 0.5 m forward and 1 deg yaw per step, forecast 10 steps
    Ma, Mb = _pose(0, 0, CAM_HEIGHT, 0), _pose(0.5, 0, CAM_HEIGHT, 0)
    print("  forecast of straight motion: x after 10 more steps = %.2f m (expected 5.50)"
          % extrapolate_pose(Ma, Mb, 10)[0, 3])
    Mr = extrapolate_pose(np.eye(4), _pose(0.5, 0, 0, 1.0), 10)
    print("  forecast with turning: yaw after 10 more steps = %.2f deg (expected 11.00: 1 deg already + 10 more)"
          % np.degrees(np.arctan2(Mr[1, 0], Mr[0, 0])))
    g = depth_ground()
    print("  ground-plane depth: row 400 -> %.2f m (expected %.2f)" % (g[400, 320], F * CAM_HEIGHT / (400 - CY)))


# ----------------------------- evaluation -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", default="dataset_v5/Town03")
    ap.add_argument("--conditions", nargs="*", default=None)
    ap.add_argument("--latencies", nargs="+", type=int, default=[200, 500, 800])
    ap.add_argument("--stride", type=int, default=25)
    ap.add_argument("--damping", type=float, default=0.7, help="Farneback baseline damping")
    ap.add_argument("--max-disp", type=float, default=80.0, help="Farneback baseline cap")
    ap.add_argument("--blur-sigma", type=float, default=2.0,
                    help="Gaussian blur of the repeat_blur control (is the gain just blur?)")
    ap.add_argument("--out", default="eval_geometric")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    WARP_CFG.update(damping=args.damping, max_disp=args.max_disp)

    data = Path(args.data)
    conditions = args.conditions or sorted(p.name for p in data.iterdir() if (p / "metadata.csv").exists())
    out = Path(args.out)
    (out / "examples").mkdir(parents=True, exist_ok=True)
    methods = ["repeat", "repeat_blur", "farneback", "geo_oracle", "geo_const", "geo_ground"]
    ks = {lat: int(round(lat / FRAME_MS)) for lat in args.latencies}
    ground = depth_ground()
    rows, shown = [], set()

    for cond in conditions:
        segments = load_segments(data / cond)
        n = sum(len(range(1, len(s), args.stride)) for s in segments)
        print("[%s] segments %s | about %d positions" % (cond, [len(s) for s in segments], n), flush=True)
        done = 0
        for seg in segments:
            for i in range(1, len(seg), args.stride):
                needed = [lat for lat in args.latencies if i + ks[lat] < len(seg)]
                if not needed:
                    continue
                done += 1
                if done % 20 == 0:
                    print("   %s: %d positions" % (cond, done), flush=True)
                prev = cv2.imread(str(seg[i - 1]["rgb"]), cv2.IMREAD_COLOR)
                cur = cv2.imread(str(seg[i]["rgb"]), cv2.IMREAD_COLOR)
                dep = read_depth(seg[i]["depth"])
                if prev is None or cur is None or dep is None:
                    continue
                flow = predict_flow_farneback(prev, cur)
                for lat in needed:
                    k = ks[lat]
                    target = cv2.imread(str(seg[i + k]["rgb"]), cv2.IMREAD_COLOR)
                    if target is None:
                        continue
                    M_pred = extrapolate_pose(seg[i - 1]["pose"], seg[i]["pose"], k)
                    preds = {
                        "repeat": cur,
                        "repeat_blur": cv2.GaussianBlur(cur, (0, 0), args.blur_sigma),
                        "farneback": warp_forward(cur, flow, k),
                        "geo_oracle": geometric_warp(cur, dep, seg[i]["pose"], seg[i + k]["pose"]),
                        "geo_const": geometric_warp(cur, dep, seg[i]["pose"], M_pred),
                        "geo_ground": geometric_warp(cur, ground, seg[i]["pose"], M_pred),
                    }
                    for m in methods:
                        rows.append(dict(condition=cond, latency_ms=lat, method=m,
                                         psnr=psnr(preds[m], target), ssim=ssim(preds[m], target)))
                    if (cond, lat) not in shown:
                        shown.add((cond, lat))
                        tiles = []
                        for img, name in zip([target] + [preds[m] for m in methods], ["real"] + methods):
                            t = img.copy()
                            cv2.putText(t, name, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            tiles.append(t)
                        tiles += [np.zeros_like(cur)] * (8 - len(tiles))
                        cv2.imwrite(str(out / "examples" / ("%s_%dms.png" % (cond, lat))),
                                    np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:8])]))

    if not rows:
        raise SystemExit("No samples built.")
    with (out / "samples.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def mean(cond, lat, m, key):
        v = [r[key] for r in rows if r["condition"] == cond and r["latency_ms"] == lat and r["method"] == m]
        return float(np.mean(v)) if v else float("nan")

    print("\n=== PSNR dB / SSIM per condition (mean of samples) ===")
    print("%-14s %5s " % ("condition", "lat") + " ".join("%15s" % m for m in methods))
    for cond in conditions:
        for lat in args.latencies:
            print("%-14s %5d " % (cond, lat) + " ".join(
                "%7.2f/%.3f" % (mean(cond, lat, m, "psnr"), mean(cond, lat, m, "ssim")) for m in methods))
    print("\n=== Weather-balanced average (mean of the per-condition means) ===")
    for lat in args.latencies:
        cells = []
        for m in methods:
            p = np.nanmean([mean(c, lat, m, "psnr") for c in conditions])
            s = np.nanmean([mean(c, lat, m, "ssim") for c in conditions])
            cells.append("%s %.2f/%.3f" % (m, p, s))
        print("%d ms -> " % lat + " | ".join(cells))
    print("\nSaved to %s/ (samples.csv, examples/)" % out)


if __name__ == "__main__":
    main()