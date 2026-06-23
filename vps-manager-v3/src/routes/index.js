const express = require('express');
const router = express.Router();

const authRoutes = require('./auth.routes');
const vpsRoutes = require('./vps.routes');
const tagsRoutes = require('./tags.routes');
const nezhaRoutes = require('./nezha.routes');
const analyticsRoutes = require('./analytics.routes');
const budgetsRoutes = require('./budgets.routes');
const healthRoutes = require('./health.routes');
const historyRoutes = require('./history.routes');
const batchRoutes = require('./batch.routes');
const notificationRoutes = require('./notification.routes');
const publicRoutes = require('./public.routes');

router.use('/auth', authRoutes);
router.use('/vps', vpsRoutes);
router.use('/tags', tagsRoutes);
router.use('/nezha', nezhaRoutes);
router.use('/analytics', analyticsRoutes);
router.use('/budgets', budgetsRoutes);
router.use('/health', healthRoutes);
router.use('/batch', batchRoutes);
router.use('/notification', notificationRoutes);

router.use('/', publicRoutes);
router.use('/', historyRoutes);

module.exports = router;
