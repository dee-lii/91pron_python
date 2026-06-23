const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../auth');
const { getHealthChecker } = require('../features/monitoring/health-checker');
const { getHealthCheckScheduler } = require('../features/monitoring/health-check-scheduler');

/**
 * @swagger
 * tags:
 *   name: Health
 *   description: VPS health monitoring
 */

// ==================== VPS健康检查监控 API ====================

/**
 * @swagger
 * /health/check/{id}:
 *   get:
 *     summary: Check health of a specific VPS
 *     tags: [Health]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Health check result
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: object
 *                   properties:
 *                     status:
 *                       type: string
 *                     latency:
 *                       type: number
 */
router.get('/check/:id', authMiddleware, async (req, res) => {
  try {
    const { id } = req.params;

    const checker = getHealthChecker();
    const result = await checker.getDetailedReport(id);

    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '健康检查失败: ' + error.message
    });
  }
});

/**
 * @swagger
 * /health/overview:
 *   get:
 *     summary: Get health overview of all VPS
 *     tags: [Health]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Health overview
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: object
 *                   properties:
 *                     total:
 *                       type: number
 *                     healthy:
 *                       type: number
 *                     down:
 *                       type: number
 */
router.get('/overview', authMiddleware, async (req, res) => {
  try {
    const checker = getHealthChecker();
    const overview = await checker.getHealthOverview();

    res.json({
      success: true,
      data: overview
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取健康概览失败: ' + error.message
    });
  }
});

/**
 * 批量检查多个VPS的健康状态
 */
router.post('/ping', authMiddleware, async (req, res) => {
  try {
    const { ip, timeout } = req.body;

    if (!ip) {
      return res.status(400).json({
        success: false,
        error: 'IP地址不能为空'
      });
    }

    const checker = getHealthChecker();
    const result = await checker.pingCheck(ip, timeout);

    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Ping检测失败: ' + error.message
    });
  }
});

/**
 * HTTP/HTTPS检测
 */
router.post('/http', authMiddleware, async (req, res) => {
  try {
    const { url, timeout } = req.body;

    if (!url) {
      return res.status(400).json({
        success: false,
        error: 'URL不能为空'
      });
    }

    const checker = getHealthChecker();
    const result = await checker.httpCheck(url, timeout);

    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'HTTP检测失败: ' + error.message
    });
  }
});

/**
 * 获取有问题的VPS列表
 */
router.get('/problematic', authMiddleware, async (req, res) => {
  try {
    const checker = getHealthChecker();
    const overview = await checker.getHealthOverview();

    res.json({
      success: true,
      data: overview.problematicVps
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取问题VPS列表失败: ' + error.message
    });
  }
});

/**
 * 获取健康检查调度器状态
 */
router.get('/scheduler/status', authMiddleware, (req, res) => {
  try {
    const scheduler = getHealthCheckScheduler();
    const status = scheduler.getStatus();

    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取调度器状态失败: ' + error.message
    });
  }
});

/**
 * 更新健康检查调度器配置
 */
router.put('/scheduler/config', authMiddleware, (req, res) => {
  try {
    const { enabled, cronExpression, alertThreshold, telegramAlertEnabled, checkOnStartup } = req.body;

    const scheduler = getHealthCheckScheduler();
    const config = {};

    if (typeof enabled === 'boolean') config.enabled = enabled;
    if (cronExpression) config.cronExpression = cronExpression;
    if (typeof alertThreshold === 'number') config.alertThreshold = alertThreshold;
    if (typeof telegramAlertEnabled === 'boolean') config.telegramAlertEnabled = telegramAlertEnabled;
    if (typeof checkOnStartup === 'boolean') config.checkOnStartup = checkOnStartup;

    const updatedConfig = scheduler.updateConfig(config);

    res.json({
      success: true,
      data: updatedConfig,
      message: '健康检查调度器配置已更新'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '更新调度器配置失败: ' + error.message
    });
  }
});

/**
 * 启动健康检查调度器
 */
router.post('/scheduler/start', authMiddleware, (req, res) => {
  try {
    const scheduler = getHealthCheckScheduler();

    // 先启用配置
    scheduler.updateConfig({ enabled: true });

    res.json({
      success: true,
      message: '健康检查调度器已启动'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '启动调度器失败: ' + error.message
    });
  }
});

/**
 * 停止健康检查调度器
 */
router.post('/scheduler/stop', authMiddleware, (req, res) => {
  try {
    const scheduler = getHealthCheckScheduler();

    // 停用配置
    scheduler.updateConfig({ enabled: false });

    res.json({
      success: true,
      message: '健康检查调度器已停止'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '停止调度器失败: ' + error.message
    });
  }
});

/**
 * 手动触发一次健康检查
 */
router.post('/scheduler/trigger', authMiddleware, async (req, res) => {
  try {
    const scheduler = getHealthCheckScheduler();
    const result = await scheduler.executeCheck();

    res.json({
      success: true,
      data: result,
      message: '健康检查已执行'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '执行健康检查失败: ' + error.message
    });
  }
});

module.exports = router;
