/**
 * useWebRTC — Dashboard is the RECEIVER (answerer) side.
 *
 * Flow:
 *   1. Operator clicks "Start Stream" → startStream(vehicleId) → emits stream:request
 *   2. Backend confirms → emits stream:starting
 *   3. Vehicle grabs webcam, creates offer → relayed here via webrtc:offer
 *   4. We set remote description, create answer, send back
 *   5. ICE candidates exchanged
 *   6. ontrack fires → video element gets srcObject → stream plays
 */
import { useEffect, useRef, useCallback } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';

const RTC_CONFIG = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ],
};

export function useWebRTC(videoRef) {
  const pcRef = useRef(null);
  const fromIdRef = useRef(null); // vehicle's socket ID — needed to route ICE back

  const { setStreamActive, setWebRTCStatus, setSessionId } = useVehicleStore();

  /**
   * Operator requests a stream from a specific vehicle.
   * @param {string} vehicleId — the vehicle's socket ID
   */
  const startStream = useCallback((vehicleId) => {
    setWebRTCStatus('connecting');
    socket.emit('stream:request', { vehicleId });
  }, [setWebRTCStatus]);

  /** Stop stream and close peer connection */
  const stopStream = useCallback(() => {
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    if (videoRef?.current) {
      videoRef.current.srcObject = null;
    }
    setStreamActive(false);
    setWebRTCStatus('idle');
    setSessionId(null);
    fromIdRef.current = null;
  }, [videoRef, setStreamActive, setWebRTCStatus, setSessionId]);

  useEffect(() => {
    /** Backend confirms stream is starting */
    socket.on('stream:starting', ({ sessionId }) => {
      setSessionId(sessionId);
      console.log('[WebRTC] Stream starting, session:', sessionId?.slice(0, 8));
    });

    /** Receive SDP offer from vehicle → create answer */
    socket.on('webrtc:offer', async ({ sessionId, sdp, fromId }) => {
      console.log('[WebRTC] Received offer from vehicle:', fromId?.slice(0, 6));
      fromIdRef.current = fromId;

      // Tear down any existing connection
      if (pcRef.current) {
        pcRef.current.close();
      }

      const pc = new RTCPeerConnection(RTC_CONFIG);
      pcRef.current = pc;

      // Send our ICE candidates to the vehicle
      pc.onicecandidate = ({ candidate }) => {
        if (candidate && fromIdRef.current) {
          socket.emit('webrtc:ice-candidate', {
            sessionId,
            candidate,
            targetId: fromIdRef.current,
          });
        }
      };

      // When video track arrives → show it
      pc.ontrack = ({ streams }) => {
        console.log('[WebRTC] 🎥 Video track received!');
        if (videoRef?.current && streams[0]) {
          videoRef.current.srcObject = streams[0];
          setStreamActive(true);
          setWebRTCStatus('active');
        }
      };

      pc.onconnectionstatechange = () => {
        console.log('[WebRTC] State:', pc.connectionState);
        if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
          setStreamActive(false);
          setWebRTCStatus('idle');
        }
      };

      // Set vehicle's offer, create our answer
      await pc.setRemoteDescription(new RTCSessionDescription(sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      // Send answer back to vehicle
      socket.emit('webrtc:answer', {
        sessionId,
        sdp: answer,
        targetId: fromId,
      });
      console.log('[WebRTC] Answer sent to vehicle');
    });

    /** ICE candidates from vehicle */
    socket.on('webrtc:ice-candidate', async ({ candidate }) => {
      if (pcRef.current && candidate) {
        try {
          await pcRef.current.addIceCandidate(new RTCIceCandidate(candidate));
        } catch (e) {
          console.warn('[WebRTC] ICE add failed:', e.message);
        }
      }
    });

    /** Vehicle stopped stream */
    socket.on('stream:stopped', () => {
      stopStream();
    });

    /** Backend error */
    socket.on('stream:error', ({ message }) => {
      console.error('[WebRTC] Stream error:', message);
      setWebRTCStatus('error');
    });

    return () => {
      socket.off('stream:starting');
      socket.off('webrtc:offer');
      socket.off('webrtc:ice-candidate');
      socket.off('stream:stopped');
      socket.off('stream:error');
    };
  }, [videoRef, stopStream, setSessionId, setStreamActive, setWebRTCStatus]);

  return { startStream, stopStream };
}

export default useWebRTC;
