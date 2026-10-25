import { useEffect } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';
const KEYS = new Set(['w', 'a', 's', 'd', ' ']);
let sequence = 0;
export default function useKeyboard() {
  useEffect(() => {
    const keys = new Set();
    let focused = document.hasFocus();
    const sync = () => useVehicleStore.getState().patch({ activeKeys: new Set(keys) });
    const send = () => {
      const state = useVehicleStore.getState();
      if (!socket.connected || !state.vehicleConnected || state.emergency) return;
      const enabled = state.streamActive && focused && document.hasFocus() && !document.hidden;
      socket.volatile.emit('control:direct', { sequence: ++sequence,
        throttle: enabled && keys.has('w') && !keys.has('s') ? 1 : 0,
        brake: !enabled || keys.has('s') ? 1 : 0,
        steer: enabled ? (Number(keys.has('d')) - Number(keys.has('a'))) * 0.5 : 0 });
    };
    const clear = () => { keys.clear(); sync(); send(); };
    const down = (e) => {
      const key = e.key.toLowerCase();
      if (!KEYS.has(key) || /INPUT|SELECT|TEXTAREA|BUTTON/.test(e.target.tagName)) return;
      e.preventDefault();
      if (key === ' ') {
        if (!e.repeat && socket.connected && useVehicleStore.getState().vehicleConnected) socket.emit('control:emergency', {});
        clear(); return;
      }
      if (!useVehicleStore.getState().streamActive || useVehicleStore.getState().emergency) return;
      keys.add(key); sync(); send();
    };
    const up = (e) => { if (KEYS.has(e.key.toLowerCase())) { keys.delete(e.key.toLowerCase()); sync(); send(); } };
    const blur = () => { focused = false; clear(); };
    const focus = () => { focused = true; clear(); };
    const visibility = () => { if (document.hidden) blur(); else focus(); };
    const unsubscribe = useVehicleStore.subscribe((state, previous) => {
      if (state.emergency !== previous.emergency || state.streamActive !== previous.streamActive || state.vehicleConnected !== previous.vehicleConnected) clear();
    });
    window.addEventListener('keydown', down); window.addEventListener('keyup', up);
    window.addEventListener('blur', blur); window.addEventListener('focus', focus);
    document.addEventListener('visibilitychange', visibility);
    const timer = setInterval(send, 50);
    return () => {
      clearInterval(timer); unsubscribe(); keys.clear(); send();
      window.removeEventListener('keydown', down); window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur); window.removeEventListener('focus', focus);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);
}
