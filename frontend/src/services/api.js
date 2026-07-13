/**
 * REST API helper.
 * Wraps fetch with error handling and JSON parsing.
 */

const BASE = import.meta.env.VITE_BACKEND_URL || 'http://localhost:4000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () => request('/api/health'),
  telemetry: {
    latest: () => request('/api/telemetry/latest'),
    history: (limit = 50) => request(`/api/telemetry/history?limit=${limit}`),
  },
  control: {
    command: (payload) => request('/api/control/command', { method: 'POST', body: JSON.stringify(payload) }),
    emergencyStop: () => request('/api/control/emergency-stop', { method: 'POST' }),
  },
};

export default api;
