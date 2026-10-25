const BASE = import.meta.env.VITE_BACKEND_URL || '';
export const api = {
  async health() {
    const response = await fetch(`${BASE}/api/health`);
    if (!response.ok) throw new Error(`Health request failed: ${response.status}`);
    return response.json();
  },
};
export default api;
