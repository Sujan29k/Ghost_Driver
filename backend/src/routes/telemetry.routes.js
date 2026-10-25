/**
 * Telemetry Routes — /api/telemetry
 */
const router = require('express').Router();
const {
	getLatestTelemetry,
	getTelemetryHistory,
	getLatencyHistory,
} = require('../controllers/telemetry.controller');

router.get('/latest', getLatestTelemetry);
router.get('/history', getTelemetryHistory);
router.get('/latency-history', getLatencyHistory);

module.exports = router;
