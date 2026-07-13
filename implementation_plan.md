# Ghost Driver — Phase 1: Operator Web Dashboard

## Overview

Build **Phase 1** of Ghost Driver, a teleoperation platform for driverless vehicles.

This phase covers the complete **Operator Web Dashboard** — a futuristic, dark-themed control center built with **React + Vite + Tailwind CSS (frontend)** and **Node.js + Express + Socket.IO (backend)**.

The project architecture is designed so that **CARLA, WebRTC, YOLO, and AI latency compensation** can be integrated seamlessly in later phases.

---

## Updated Folder Structure

```text
Ghostdriver/
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Header.jsx
│   │   │   │   └── StatusBar.jsx
│   │   │   │
│   │   │   ├── video/
│   │   │   │   └── VideoFeed.jsx
│   │   │   │
│   │   │   ├── telemetry/
│   │   │   │   ├── TelemetryPanel.jsx
│   │   │   │   └── TelemetryCard.jsx
│   │   │   │
│   │   │   ├── controls/
│   │   │   │   ├── ControlStatus.jsx
│   │   │   │   └── KeyboardHelp.jsx
│   │   │   │
│   │   │   └── connection/
│   │   │       └── ConnectionControls.jsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── useTelemetry.js
│   │   │   ├── useKeyboard.js
│   │   │   ├── useConnection.js
│   │   │   └── useWebRTC.js
│   │   │
│   │   ├── services/
│   │   │   ├── socket.js
│   │   │   ├── signaling.js
│   │   │   └── api.js
│   │   │
│   │   ├── store/
│   │   │   └── vehicleStore.js
│   │   │
│   │   ├── utils/
│   │   │   └── formatters.js
│   │   │
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   │
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── backend/
│   ├── src/
│   │   ├── server.js
│   │   │
│   │   ├── routes/
│   │   │   ├── telemetry.routes.js
│   │   │   ├── control.routes.js
│   │   │   └── health.routes.js
│   │   │
│   │   ├── sockets/
│   │   │   ├── telemetry.socket.js
│   │   │   ├── control.socket.js
│   │   │   └── signaling.socket.js
│   │   │
│   │   ├── services/
│   │   │   ├── carla.service.js
│   │   │   ├── webrtc.service.js
│   │   │   └── latency.service.js
│   │   │
│   │   ├── controllers/
│   │   │   ├── telemetry.controller.js
│   │   │   └── control.controller.js
│   │   │
│   │   └── config/
│   │       └── cors.js
│   │
│   ├── package.json
│   └── .env
│
├── carla-service/
│   ├── carla_controller.py
│   ├── camera_stream.py
│   ├── yolo_detector.py
│   └── requirements.txt
│
├── latency-ai/
│   ├── predictor.py
│   ├── frame_generator.py
│   └── requirements.txt
│
└── README.md
```

---

# Frontend Stack

* React
* Vite
* Tailwind CSS
* Zustand
* Socket.IO Client
* WebRTC Browser API

---

# Backend Stack

* Node.js
* Express.js
* Socket.IO
* CORS
* dotenv

---

# Python Services

## CARLA Service

Responsible for:

* Vehicle spawning
* Camera feeds
* Sensor collection
* Applying vehicle controls

---

## YOLO Service

Responsible for:

* Object detection
* Bounding box generation
* Hazard alerts

---

## AI Prediction Service

Responsible for:

* Measuring latency
* Predicting future frames
* Generating latency compensated view

---

# Phase 1 Features

## Video Feed Panel

Currently:

```text
Waiting for Vehicle Stream...
```

Future:

```text
CARLA Camera
     ↓
WebRTC
     ↓
Browser Video Element
```

---

## Telemetry Panel

Display:

* Vehicle Speed
* FPS
* Network Latency
* Packet Loss
* Connection Status

Currently uses dummy values.

Later receives data from:

```text
CARLA → Python Service → Socket.IO → React
```

---

## Keyboard Controls

Supported keys:

| Key   | Action         |
| ----- | -------------- |
| W     | Throttle       |
| S     | Brake          |
| A     | Turn Left      |
| D     | Turn Right     |
| Space | Emergency Stop |

Future flow:

```text
Keyboard
   ↓
React
   ↓
Socket.IO
   ↓
Node Backend
   ↓
Python CARLA Service
   ↓
vehicle.apply_control()
```

---

## Connection Controls

Buttons:

* Connect Vehicle
* Disconnect Vehicle
* Start Stream
* Stop Stream

Future:

* Start WebRTC session
* Exchange SDP offers
* Exchange ICE candidates

---

## Status Bar

Displays:

* CARLA Status
* WebRTC Status
* YOLO Status
* AI Prediction Status
* Network Quality

---

# Phase 2 Roadmap

After dashboard completion:

## Step 1

Implement Socket.IO connection.

## Step 2

Create WebRTC signaling server.

## Step 3

Stream webcam using WebRTC.

## Step 4

Replace webcam with CARLA camera stream.

## Step 5

Send control commands to CARLA.

## Step 6

Introduce NetEm latency simulation.

## Step 7

Integrate future frame prediction model.

---

# Final Architecture (Distributed Multi-Device Setup)

Because CARLA requires a heavy GPU and runs on Windows/Ubuntu, while the Operator uses a Mac, the system operates across a local network:

```text
[Friend's PC (Windows/Linux + NVIDIA GPU)]
│
├── CARLA Simulator (Unreal Engine)
│    ├── RGB Camera
│    └── Vehicle Controls
│
├── YOLO Detection Service
│
├── AI Prediction Service
│
└── Python CARLA Service (carla_controller.py)
         │           │
         │           │ (Local Wi-Fi Network)
         │           │
[Operator's Mac (Apple Silicon M1)]
         │           │
      WebRTC      Socket.IO
   (P2P Video)  (Telemetry/WASD)
         │           │
         ▼           ▼
      Browser UI (React) ◄────── Node.js Backend
```

This architecture separates responsibilities cleanly. The Mac acts as a lightweight command center handling just the UI and network routing, while the dedicated PC handles the heavy 3D rendering and AI processing, communicating seamlessly over the local network.
