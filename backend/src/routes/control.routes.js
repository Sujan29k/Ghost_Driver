/**
 * Control Routes — /api/control
 * REST endpoints for sending vehicle commands (fallback from socket).
 */
const router = require('express').Router();
const { sendCommand, emergencyStop } = require('../controllers/control.controller');

router.post('/command', sendCommand);
router.post('/emergency-stop', emergencyStop);

module.exports = router;
