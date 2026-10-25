import asyncio
import socketio
import cv2
import numpy as np
import time
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from ultralytics import YOLO

# ── 1. CONFIGURATION ──
BACKEND_URL = 'http://localhost:4000'
VIDEO_FILE = 'driving.mp4'  # Name of your pre-recorded video

# ── 2. GLOBAL STATE ──
sio = socketio.AsyncClient()
pc = None
model = YOLO('yolov8n_coco128-5/weights/best.pt')

# ── 3. VIDEO STREAM TRACK (Replacing CARLA camera) ──
class YoloVideoStreamTrack(VideoStreamTrack):
    """
    A WebRTC track that reads from an MP4 file, processes it with YOLO
    and Optical Flow, and sends the frames to the dashboard.
    """
    def __init__(self, video_path):
        super().__init__()
        self.cap = cv2.VideoCapture(video_path)
        self.prev_gray = None

    async def recv(self):
        # This function is called by aiortc to get the next frame
        pts, time_base = await self.next_timestamp()

        ret, frame = self.cap.read()
        if not ret:
            # If video ends, loop back to the start
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                # If still failing, return a blank frame
                return VideoFrame.from_ndarray(np.zeros((480, 640, 3), dtype=np.uint8), format="rgb24")

        # ── OPTICAL FLOW ──
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        predicted_frame = frame.copy()

        if self.prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )
            h, w = frame.shape[:2]
            flow_map = np.zeros_like(flow)
            flow_map[:, :, 0] = np.arange(w)
            flow_map[:, :, 1] = np.arange(h)[:, None]
            flow_map += flow
            predicted_frame = cv2.remap(
                frame,
                flow_map[:, :, 0].astype(np.float32),
                flow_map[:, :, 1].astype(np.float32),
                cv2.INTER_LINEAR
            )
        self.prev_gray = gray

        # ── YOLO DETECTION ──
        results = model(frame, conf=0.4, verbose=False)
        boxes = results[0].boxes
        detection_frame = frame.copy()
        frame_area = frame.shape[0] * frame.shape[1]

        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls = int(box.cls)
            conf = float(box.conf)
            name = model.names[cls]
            proximity = ((x2 - x1) * (y2 - y1)) / frame_area

            if name not in ['car', 'truck', 'bus', 'person', 'bicycle', 'motorcycle']:
                continue

            color = (0, 255, 0)
            if proximity > 0.05:
                color = (0, 0, 255) # Red for close objects

            cv2.rectangle(detection_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(detection_frame, f'{name} {conf:.2f}', (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        cv2.putText(detection_frame, 'LIVE DETECTION + YOLO', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(predicted_frame, 'OPTICAL FLOW PREDICTION', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # For WebRTC, let's display both side-by-side just like cv2.imshow
        # Resize to fit reasonable WebRTC dimensions (e.g. 1280x480 total)
        display = np.hstack([detection_frame, predicted_frame])
        display_resized = cv2.resize(display, (1280, 480))

        # WebRTC expects RGB format, OpenCV uses BGR natively
        rgb_frame = cv2.cvtColor(display_resized, cv2.COLOR_BGR2RGB)

        # Create WebRTC VideoFrame
        video_frame = VideoFrame.from_ndarray(rgb_frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame

# ── 4. SOCKET.IO EVENTS ──
@sio.event
async def connect():
    print("✅ Connected to Node.js backend!")
    # Announce ourselves to the dashboard
    await sio.emit('vehicle:join', {'name': 'CARLA-Sim'})

@sio.event
async def connect_error(data):
    print("❌ Connection failed!")

@sio.event
async def disconnect():
    print("⚠️ Disconnected from backend!")

@sio.on('stream:start')
async def on_stream_start(data):
    global pc
    session_id = data['sessionId']
    operator_id = data['operatorId']
    print(f"📡 Stream requested by dashboard (session: {session_id[:8]})")

    # Clean up old connection if exists
    if pc:
        await pc.close()

    # Create WebRTC Peer Connection
    pc = RTCPeerConnection()

    # Add the YOLO video track!
    video_track = YoloVideoStreamTrack(VIDEO_FILE)
    pc.addTrack(video_track)

    # Generate SDP Offer and set local description
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    print("📨 Sending WebRTC Offer to Dashboard...")
    await sio.emit('webrtc:offer', {
        'sessionId': session_id,
        'targetId': operator_id,
        'sdp': {'type': offer.type, 'sdp': offer.sdp}
    })

@sio.on('webrtc:answer')
async def on_webrtc_answer(data):
    global pc
    if pc:
        print("📩 Answer received from Dashboard")
        sdp = data['sdp']
        answer = RTCSessionDescription(sdp=sdp['sdp'], type=sdp['type'])
        await pc.setRemoteDescription(answer)
        print("🎉 WebRTC P2P Connection Established!")

@sio.on('webrtc:ice-candidate')
async def on_webrtc_ice_candidate(data):
    global pc
    if pc and 'candidate' in data:
        cand_dict = data['candidate']
        if cand_dict and 'candidate' in cand_dict:
            try:
                # Add ICE Candidate from the dashboard
                cand = candidate_from_sdp(cand_dict['candidate'])
                cand.sdpMid = cand_dict.get('sdpMid')
                cand.sdpMLineIndex = cand_dict.get('sdpMLineIndex')
                await pc.addIceCandidate(cand)
            except Exception as e:
                pass # Some candidates fail parsing, safe to ignore on localhost

# ── 5. MAIN LOOP ──
async def main():
    print("Connecting to Backend...")
    try:
        await sio.connect(BACKEND_URL)
        await sio.wait()
    except Exception as e:
        print(f"Error connecting to backend: {e}")

if __name__ == '__main__':
    print("🚗 GhostDriver Mock Service Starting...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        if pc:
            asyncio.run(pc.close())
        print("Done.")
