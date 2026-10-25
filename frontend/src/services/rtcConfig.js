// Received only after Socket.IO authentication; never embedded in the Vite bundle.
let iceServers = [];
export function setIceServers(servers) { iceServers = servers; }
export function rtcConfig(relayOnly = false) {
  return { iceServers, iceTransportPolicy: relayOnly ? 'relay' : 'all' };
}
