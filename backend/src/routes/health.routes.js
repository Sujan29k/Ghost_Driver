/**
 * Health Routes — GET /api/health
 * Returns overall system health and service statuses.
 */
const router = require('express').Router();
const { getSystemHealth } = require('../controllers/telemetry.controller');

router.get('/', getSystemHealth);

module.exports = router;
