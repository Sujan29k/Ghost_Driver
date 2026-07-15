import cv2
import numpy as np
import os
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

condition = 'heavy_rain'
frame_folder = f'dataset/{condition}'

frames = sorted([f for f in os.listdir(frame_folder) if f.endswith('.jpg')])
print(f"✅ Found {len(frames)} frames")

psnr_scores = []
ssim_scores = []

for i in range(len(frames) - 1):
    try:
        frame1 = cv2.imread(os.path.join(frame_folder, frames[i]))
        frame2 = cv2.imread(os.path.join(frame_folder, frames[i+1]))

        if frame1 is None or frame2 is None:
            continue

        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        flow = cv2.calcOpticalFlowFarneback(
            gray1, gray2, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )

        h, w = frame1.shape[:2]
        flow_map = np.zeros_like(flow)
        flow_map[:,:,0] = np.arange(w)
        flow_map[:,:,1] = np.arange(h)[:,None]
        flow_map += flow

        predicted = cv2.remap(
            frame1,
            flow_map[:,:,0].astype(np.float32),
            flow_map[:,:,1].astype(np.float32),
            interpolation=cv2.INTER_LINEAR
        )

        p = psnr(frame2, predicted)
        s = ssim(frame2, predicted, multichannel=True)

        psnr_scores.append(p)
        ssim_scores.append(s)

        if i % 10 == 0:
            print(f"Frame {i:03d} — PSNR: {p:.2f} dB  SSIM: {s:.3f}")

            # Save side by side image instead of showing window
            mag, ang = cv2.cartToPolar(flow[:,:,0], flow[:,:,1])
            hsv = np.zeros_like(frame1)
            hsv[:,:,1] = 255
            hsv[:,:,0] = ang * 180 / np.pi / 2
            hsv[:,:,2] = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX)
            flow_rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

            display = np.hstack([frame2, predicted, flow_rgb])
            os.makedirs('results', exist_ok=True)
            cv2.imwrite(f'results/frame_{i:03d}.jpg', display)

    except Exception as e:
        print(f"Error at frame {i}: {e}")
        continue

print(f"\n{'='*40}")
print(f"RESULTS FOR: {condition}")
print(f"{'='*40}")
print(f"Average PSNR : {np.mean(psnr_scores):.2f} dB")
print(f"Average SSIM : {np.mean(ssim_scores):.4f}")
print(f"Min PSNR     : {np.min(psnr_scores):.2f} dB")
print(f"Max PSNR     : {np.max(psnr_scores):.2f} dB")
print(f"Frames tested: {len(psnr_scores)}")
print(f"\nCheck results/ folder for visualizations")