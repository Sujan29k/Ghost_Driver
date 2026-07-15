import cv2
import numpy as np
import os

condition = 'clear_traffic'
frame_folder = f'dataset/{condition}'
print('folder:', os.path.abspath(frame_folder))
print('exists:', os.path.exists(frame_folder))
frames = sorted([f for f in os.listdir(frame_folder) if f.endswith('.jpg')])
print('frames found:', len(frames))