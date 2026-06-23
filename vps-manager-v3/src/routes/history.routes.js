const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../auth');
const { getHistoryTracker } = require('../features/monitoring/history-tracker');
const { HealthHistoryDB, CostHistoryDB, BudgetHistoryDB } = require('../database');

// ==================== 历史数据与趋势分析 ====================

/**
 * 获取健康检查历史
 */
router.get('/history/health', authMiddleware, (req, res) => {
  try {
    const days = parseInt(req.query.days) || 7;
    const history = HealthHistoryDB.getByDays(days);

    res.json({
      success: true,
      data: {
        period: `最近${days}天`,
        count: history.length,
        history
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取健康历史失败: ' + error.message
    });
  }
});

/**
 * 获取成本历史
 */
router.get('/history/cost', authMiddleware, (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;
    const history = CostHistoryDB.getByDays(days);

    res.json({
      success: true,
      data: {
        period: `最近${days}天`,
        count: history.length,
        history
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取成本历史失败: ' + error.message
    });
  }
});

/**
 * 获取预算历史
 */
router.get('/history/budget/:budgetId', authMiddleware, (req, res) => {
  try {
    const budgetId = parseInt(req.params.budgetId);
    const days = parseInt(req.query.days) || 30;

    if (isNaN(budgetId)) {
      return res.status(400).json({
        success: false,
        error: '无效的预算ID'
      });
    }

    const allHistory = BudgetHistoryDB.getByBudgetId(budgetId);

    // 过滤最近N天的数据
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - days);
    const cutoffStr = cutoffDate.toISOString();

    const history = allHistory.filter(h => h.created_at >= cutoffStr);

    res.json({
      success: true,
      data: {
        budgetId,
        period: `最近${days}天`,
        count: history.length,
        history
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算历史失败: ' + error.message
    });
  }
});

/**
 * 获取健康检查趋势
 */
router.get('/trends/health', authMiddleware, async (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const days = parseInt(req.query.days) || 7;

    const trend = await tracker.getHealthTrend(days);

    res.json({
      success: true,
      data: trend
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取健康趋势失败: ' + error.message
    });
  }
});

/**
 * 获取成本趋势
 */
router.get('/trends/cost', authMiddleware, (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const days = parseInt(req.query.days) || 30;

    const trend = tracker.getCostTrend(days);

    res.json({
      success: true,
      data: trend
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取成本趋势失败: ' + error.message
    });
  }
});

/**
 * 获取预算趋势
 */
router.get('/trends/budget/:budgetId', authMiddleware, (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const budgetId = parseInt(req.params.budgetId);
    const days = parseInt(req.query.days) || 30;

    if (isNaN(budgetId)) {
      return res.status(400).json({
        success: false,
        error: '无效的预算ID'
      });
    }

    const trend = tracker.getBudgetTrend(budgetId, days);

    res.json({
      success: true,
      data: trend
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算趋势失败: ' + error.message
    });
  }
});

/**
 * 获取综合趋势（健康+成本）
 */
router.get('/trends/all', authMiddleware, async (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const days = parseInt(req.query.days) || 7;

    const trends = await tracker.getAllTrends(days);

    res.json({
      success: true,
      data: trends
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取综合趋势失败: ' + error.message
    });
  }
});

/**
 * 手动记录快照
 */
router.post('/history/snapshot', authMiddleware, async (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const results = await tracker.takeDailySnapshot();

    res.json({
      success: true,
      data: results,
      message: '快照记录完成'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '记录快照失败: ' + error.message
    });
  }
});

/**
 * 清理旧数据
 */
router.post('/history/cleanup', authMiddleware, (req, res) => {
  try {
    const tracker = getHistoryTracker();
    const results = tracker.cleanupOldData();

    res.json({
      success: true,
      data: results,
      message: '清理完成'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '清理失败: ' + error.message
    });
  }
});

module.exports = router;
