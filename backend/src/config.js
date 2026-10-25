const { timingSafeEqual } = require('node:crypto');
function sameToken(actual, expected) {
  if (typeof actual !== 'string' || actual.length > 1024) return false;
  const a = Buffer.from(actual), b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
function loadConfig(env = process.env) {
  const tokens = { dashboard: env.DASHBOARD_TOKEN, sender: env.SENDER_TOKEN };
  for (const token of Object.values(tokens)) {
    if (!token || token.length < 32) throw new Error('Set distinct DASHBOARD_TOKEN and SENDER_TOKEN values (at least 32 characters) in backend/.env');
  }
  if (tokens.dashboard === tokens.sender) throw new Error('Dashboard and sender tokens must be different');
  const iceServers = [];
  if (env.STUN_URL) {
    if (!/^stun:(?:[a-zA-Z0-9.-]+|\[[a-fA-F0-9:]+\])(?::\d{1,5})?$/.test(env.STUN_URL)) throw new Error('STUN_URL must be a stun: server address');
    iceServers.push({ urls: env.STUN_URL });
  }
  const turn = [env.TURN_URL, env.TURN_USERNAME, env.TURN_PASSWORD];
  if (turn.some(Boolean)) {
    if (!turn.every(Boolean) || !/^turns?:(?:[a-zA-Z0-9.-]+|\[[a-fA-F0-9:]+\])(?::\d{1,5})?(?:\?transport=(udp|tcp))?$/.test(env.TURN_URL)) {
      throw new Error('Set TURN_URL (turn: or turns: address), TURN_USERNAME and TURN_PASSWORD together');
    }
    iceServers.push({ urls: env.TURN_URL, username: env.TURN_USERNAME, credential: env.TURN_PASSWORD });
  }
  return { tokens, iceServers, allowDemo: env.ALLOW_DEMO === 'true' };
}
module.exports = { loadConfig, sameToken };
