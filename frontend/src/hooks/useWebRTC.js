import { useEffect } from 'react';
import { socket, request } from '../services/socket';
import { rtcConfig } from '../services/rtcConfig';
import useVehicleStore from '../store/vehicleStore';
export default function useWebRTC(videoRef) {
  useEffect(() => {
    let pc = null, sessionId = null, candidates = [], previous = null;
    let retryTimer, lastFrameAt = 0, startedAt = 0, retryCount = 0;
    const state = useVehicleStore.getState;
    const patch = (data) => state().patch(data);
    const close = () => {
      clearTimeout(retryTimer);
      const old = pc; pc = null; sessionId = null; candidates = []; previous = null;
      if (old) { old.onconnectionstatechange = null; old.ontrack = null; old.close(); }
      if (videoRef.current) videoRef.current.srcObject = null;
      patch({ streamActive: false, emergency: true, webrtcStatus: 'idle', sessionId: null,
        fps: 0, packetLoss: 0, statsAvailable: false, videoRoute: 'Unknown' });
    };
    const retry = () => {
      if (!socket.connected || !state().vehicleConnected || !state().videoWanted || retryCount >= 3) return;
      retryCount += 1;
      patch({ retryCount, error: `Video disconnected. Retrying (${retryCount}/3); controls remain stopped.` });
      retryTimer = setTimeout(() => {
        if (!socket.connected || !state().vehicleConnected || !state().videoWanted) return;
        request('stream:request', { vehicleId: state().connectedVehicleId, relayOnly: state().relayOnly })
          .catch((error) => { patch({ error: error.message }); retry(); });
      }, 2000 * retryCount);
    };
    const fail = (error, id) => {
      if (!id || id !== sessionId) return;
      socket.emit('stream:error', { sessionId: id, message: error.message });
      close(); patch({ error: `Video: ${error.message}` }); retry();
    };
    const starting = (data) => {
      if (state().retryCount === 0) retryCount = 0;
      close(); sessionId = data.sessionId; startedAt = lastFrameAt = Date.now();
      patch({ sessionId, webrtcStatus: 'connecting', error: '' });
    };
    const offer = async (data) => {
      if (data.sessionId !== sessionId) return;
      const id = sessionId;
      try {
        const peer = new RTCPeerConnection(rtcConfig(state().relayOnly)); pc = peer;
        peer.onicecandidate = ({ candidate }) => {
          if (pc === peer && candidate) socket.emit('webrtc:ice-candidate', { sessionId: id, candidate });
        };
        peer.ontrack = ({ streams, track }) => {
          if (pc === peer && videoRef.current) {
            videoRef.current.srcObject = streams[0] || new MediaStream([track]);
            videoRef.current.play().catch(() => fail(new Error('Video playback failed'), id));
            track.onended = () => { if (pc === peer) fail(new Error('Camera track ended'), id); };
          }
        };
        peer.onconnectionstatechange = () => {
          if (pc !== peer) return;
          if (['failed', 'disconnected', 'closed'].includes(peer.connectionState)) fail(new Error('Video connection lost'), id);
        };
        await peer.setRemoteDescription(data.sdp);
        if (pc !== peer) return;
        for (const candidate of candidates) await peer.addIceCandidate(candidate);
        candidates = [];
        await peer.setLocalDescription(await peer.createAnswer());
        if (pc === peer) socket.emit('webrtc:answer', { sessionId: id, sdp: peer.localDescription });
      } catch (error) { fail(error, id); }
    };
    const ice = async (data) => {
      if (data.sessionId !== sessionId || !data.candidate) return;
      if (!pc?.remoteDescription) { candidates.push(data.candidate); return; }
      try { await pc.addIceCandidate(data.candidate); } catch (error) { fail(error, data.sessionId); }
    };
    const stopped = (data) => {
      if (data.sessionId !== sessionId) return;
      close();
      if (!['Stream stopped', 'Stream restarted', 'Operator disconnected'].includes(data.reason)) {
        patch({ error: data.reason }); retry();
      }
    };
    const reset = () => { retryCount = 0; patch({ videoWanted: false, retryCount: 0 }); close(); };
    socket.on('stream:starting', starting).on('webrtc:offer', offer).on('webrtc:ice-candidate', ice)
      .on('stream:stopped', stopped).on('disconnect', reset).on('vehicle:released', reset);
    const timer = setInterval(async () => {
      const peer = pc, id = sessionId;
      if (!id) return;
      if (!state().streamActive && Date.now() - startedAt > 45000) return fail(new Error('No video received; check sender and TURN settings'), id);
      if (!peer || peer.connectionState !== 'connected') return;
      try {
        const reports = await peer.getStats();
        if (peer !== pc) return;
        let pair;
        reports.forEach((r) => { if (r.type === 'transport' && r.selectedCandidatePairId) pair = reports.get(r.selectedCandidatePairId); });
        if (!pair) reports.forEach((r) => { if (r.type === 'candidate-pair' && r.selected) pair = r; });
        const local = pair && reports.get(pair.localCandidateId), remote = pair && reports.get(pair.remoteCandidateId);
        patch({ videoRoute: local?.candidateType === 'relay' || remote?.candidateType === 'relay' ? 'TURN relay'
          : local?.candidateType && remote?.candidateType ? 'Direct' : 'Unknown' });
        reports.forEach((r) => {
          if (r.type !== 'inbound-rtp' || (r.kind || r.mediaType) !== 'video') return;
          const frames = Math.max(0, (r.framesDecoded || 0) - (previous?.framesDecoded || 0));
          const fps = r.framesPerSecond ?? (previous ? 1000 * frames / (r.timestamp - previous.timestamp) : 0);
          const lost = Math.max(0, (r.packetsLost || 0) - (previous?.packetsLost || 0));
          const received = Math.max(0, r.packetsReceived - (previous?.packetsReceived || 0));
          if (frames > 0 && videoRef.current?.readyState >= 2) {
            lastFrameAt = Date.now(); retryCount = 0;
            patch({ streamActive: true, webrtcStatus: 'active', retryCount: 0, error: '' });
            // Repeated readiness is a received-frame heartbeat, also checked by the backend.
            socket.emit('stream:ready', { sessionId: id });
          }
          patch({ fps: Number.isFinite(fps) ? fps : 0, packetLoss: 100 * lost / Math.max(1, lost + received), statsAvailable: true });
          previous = r;
        });
        if (state().streamActive && Date.now() - lastFrameAt > 4000) fail(new Error('Camera frames stopped arriving'), id);
      } catch { /* Closing a peer can reject a pending stats request. */ }
    }, 1000);
    return () => {
      clearInterval(timer);
      socket.off('stream:starting', starting).off('webrtc:offer', offer).off('webrtc:ice-candidate', ice)
        .off('stream:stopped', stopped).off('disconnect', reset).off('vehicle:released', reset);
      close();
    };
  }, [videoRef]);
}
