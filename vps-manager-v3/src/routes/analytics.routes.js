const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../auth');
const { getCostAnalyzer } = require('../features/analytics/cost-analyzer');

// ==================== 成本分析 API（需要认证） ====================

// 获取成本总览
router.get('/cost/overview', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const overview = analyzer.getTotalCostStats();

    res.json({
      success: true,
      data: overview
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取成本总览失败: ' + error.message
    });
  }
});

// 按提供商分组的成本分析
router.get('/cost/by-provider', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const stats = analyzer.getCostByProvider();

    res.json({
      success: true,
      data: stats
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取提供商成本分析失败: ' + error.message
    });
  }
});

// 按计费周期分组的成本分析
router.get('/cost/by-cycle', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const stats = analyzer.getCostByCycle();

    res.json({
      success: true,
      data: stats
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取计费周期成本分析失败: ' + error.message
    });
  }
});

// 按地理位置分组的成本分析
router.get('/cost/by-location', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const stats = analyzer.getCostByLocation();

    res.json({
      success: true,
      data: stats
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取地理位置成本分析失败: ' + error.message
    });
  }
});

// 获取成本趋势数据
router.get('/cost/trend', authMiddleware, (req, res) => {
  try {
    const { months } = req.query;
    const analyzer = getCostAnalyzer();
    const monthCount = months ? parseInt(months) : 12;

    if (monthCount < 1 || monthCount > 24) {
      return res.status(400).json({
        success: false,
        error: '月份数量必须在1-24之间'
      });
    }

    const trend = analyzer.getCostTrend(monthCount);

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

// 获取成本占比分析
router.get('/cost/distribution', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const distribution = analyzer.getCostDistribution();

    res.json({
      success: true,
      data: distribution
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取成本占比分析失败: ' + error.message
    });
  }
});

// 获取成本排名（Top N最贵的服务器）
router.get('/cost/top-expensive', authMiddleware, (req, res) => {
  try {
    const { limit } = req.query;
    const analyzer = getCostAnalyzer();
    const limitCount = limit ? parseInt(limit) : 10;

    if (limitCount < 1 || limitCount > 100) {
      return res.status(400).json({
        success: false,
        error: '限制数量必须在1-100之间'
      });
    }

    const topExpensive = analyzer.getTopExpensiveServers(limitCount);

    res.json({
      success: true,
      data: topExpensive
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取成本排名失败: ' + error.message
    });
  }
});

// 获取完整的成本分析报告
router.get('/cost/full-report', authMiddleware, (req, res) => {
  try {
    const analyzer = getCostAnalyzer();
    const report = analyzer.getFullAnalysis();

    res.json({
      success: true,
      data: report,
      generatedAt: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '生成成本分析报告失败: ' + error.message
    });
  }
});

module.exports = router;
