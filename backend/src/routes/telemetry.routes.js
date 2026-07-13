/**
 * Telemetry Routes — /api/telemetry
 */
const router = require('express').Router();
const { getLatestTelemetry, getTelemetryHistory } = require('../controllers/telemetry.controller');

router.get('/latest', getLatestTelemetry);
router.get('/history', getTelemetryHistory);

module.exports = router;
