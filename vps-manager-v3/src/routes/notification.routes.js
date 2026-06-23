const express = require('express');
const router = express.Router();
const { VpsDB } = require('../database');
const { authMiddleware } = require('../auth');
const { getTelegramNotifier } = require('../features/notification/telegram-notifier');
const { getRenewalScheduler } = require('../features/notification/renewal-scheduler');

const telegramNotifier = getTelegramNotifier();
const renewalScheduler = getRenewalScheduler();

// ==================== 通知系统 API ====================

/**
 * 测试Telegram连接
 */
router.post('/telegram/test', authMiddleware, async (req, res) => {
  try {
    const result = await telegramNotifier.testConnection();
    res.json({
      success: result.success,
      data: result.botInfo,
      message: result.success ? 'Telegram连接测试成功' : result.error
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 手动触发续费检查
 */
router.post('/renewal/check', authMiddleware, async (req, res) => {
  try {
    await renewalScheduler.triggerManualCheck();
    res.json({
      success: true,
      message: '续费检查已执行，请查看Telegram消息'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 获取续费调度器状态
 */
router.get('/renewal/status', authMiddleware, (req, res) => {
  const status = renewalScheduler.getStatus();
  res.json({
    success: true,
    data: status
  });
});

/**
 * 获取即将到期的VPS列表
 */
router.get('/expiring', authMiddleware, (req, res) => {
  try {
    const vpsList = VpsDB.getAll();
    const expiringVps = renewalScheduler.getExpiringVps(vpsList);
    const grouped = renewalScheduler.groupByUrgency(expiringVps);

    res.json({
      success: true,
      data: {
        total: expiringVps.length,
        list: expiringVps,
        grouped: {
          critical: grouped.critical.length,
          warning: grouped.warning.length,
          info: grouped.info.length
        }
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

module.exports = router;
