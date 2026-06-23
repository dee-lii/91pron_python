const express = require('express');
const router = express.Router();
const { VpsDB } = require('../database');
const { getCostAnalyzer } = require('../features/analytics/cost-analyzer');
const { calculateRemainingValue, getDaysByCycle, calculateUsedDays } = require('../calculator');
const { getSupportedCPUs } = require('../cpu-benchmarks');
const { calculateRankings, generatePerformanceReport } = require('../performance-calculator');
const { fetchExchangeRate } = require('../services/exchange-rate');
const { authMiddleware } = require('../auth');

// ==================== 公开 API（无需认证）====================

/**
 * 获取公开统计数据
 * GET /api/public/stats
 */
router.get('/public/stats', (req, res) => {
  try {
    const vpsList = VpsDB.getAll();
    const costAnalyzer = getCostAnalyzer();
    const stats = costAnalyzer.getTotalCostStats();

    // Calculate online/offline/expiring
    let onlineServers = 0;
    let offlineServers = 0;
    let expiringServers = 0;

    vpsList.forEach(vps => {
      // Online/Offline status
      if (vps.nezha && vps.nezha.online) {
        onlineServers++;
      } else {
        offlineServers++;
      }

      // Expiring status
      try {
        if (vps.cycle && vps.purchaseDate) {
             const totalDays = getDaysByCycle(vps.cycle);
             const usedDays = calculateUsedDays(vps.purchaseDate);
             const remainingDays = totalDays - usedDays;
             if (remainingDays >= 1 && remainingDays <= 30) {
                 expiringServers++;
             }
        }
      } catch (e) {
          // ignore error
      }
    });

    res.json({
      success: true,
      data: {
        totalServers: vpsList.length,
        monthlyCost: stats.monthly,
        yearlyCost: stats.yearly,
        averageCost: vpsList.length > 0 ? (stats.monthly / vpsList.length).toFixed(2) : 0,
        providers: [...new Set(vpsList.map(v => v.provider).filter(Boolean))].length,
        locations: [...new Set(vpsList.map(v => v.location).filter(Boolean))].length,
        onlineServers,
        offlineServers,
        expiringServers
      }
    });
  } catch (error) {
    console.error('[公开API] stats错误:', error.message);
    res.status(500).json({
      success: false,
      error: '获取统计数据失败: ' + error.message
    });
  }
});

/**
 * 获取公开服务器列表
 * GET /api/public/servers
 */
router.get('/public/servers', (req, res) => {
  try {
    const vpsList = VpsDB.getAll();

    // 返回公开信息（隐藏敏感数据）
    const publicServers = vpsList.map(vps => {
      let remainingDays = null;
      let usageRate = null;
      let expiryDate = null;
      
      try {
          if (vps.cycle && vps.purchaseDate) {
              const totalDays = getDaysByCycle(vps.cycle);
              const usedDays = calculateUsedDays(vps.purchaseDate);
              const remainingVal = calculateRemainingValue(vps.price || 0, totalDays, usedDays);
              remainingDays = remainingVal.remainingDays;
              usageRate = remainingVal.usageRate;
              
              // Calculate expiry date
              const purchaseDate = new Date(vps.purchaseDate);
              const expiry = new Date(purchaseDate.getTime() + totalDays * 24 * 60 * 60 * 1000);
              expiryDate = expiry.toISOString().split('T')[0];
          }
      } catch (e) {
          console.error(`Error calculating stats for VPS ${vps.id}:`, e.message);
      }

      return {
        id: vps.id,
        name: vps.name,
        provider: vps.provider || '未知',
        location: vps.location || '未知',
        price: vps.price,
        currency: vps.currency || 'CNY',
        cycle: vps.cycle,
        remainingDays,
        expiryDate,
        usageRate,
        online: vps.nezha ? vps.nezha.online : false,
        nezha: vps.nezha || null,
        specs: vps.specs ? {
          cpu: vps.specs.cpu,
          memory: vps.specs.memory,
          storage: vps.specs.storage,
          network: vps.specs.network
        } : null
      };
    });

    res.json({
      success: true,
      data: publicServers
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取服务器列表失败'
    });
  }
});

/**
 * 获取公开排名数据
 * GET /api/public/rankings
 */
router.get('/public/rankings', (req, res) => {
  try {
    const vpsList = VpsDB.getAll();

    // 按性价比排序（价格从低到高）
    const rankings = vpsList
      .filter(vps => vps.price && vps.cycle)
      .map(vps => {
        try {
          const totalDays = getDaysByCycle(vps.cycle);
          const monthlyCost = totalDays > 0 ? (vps.price / totalDays) * 30 : 0;

          return {
            id: vps.id,
            name: vps.name,
            provider: vps.provider || '未知',
            location: vps.location || '未知',
            monthlyCost: monthlyCost.toFixed(2),
            currency: vps.currency || 'CNY',
            specs: vps.specs
          };
        } catch (error) {
          // 不支持的周期，跳过
          return null;
        }
      })
      .filter(Boolean) // 过滤掉null
      .sort((a, b) => parseFloat(a.monthlyCost) - parseFloat(b.monthlyCost))
      .slice(0, 10); // 只返回前10名

    res.json({
      success: true,
      data: rankings
    });
  } catch (error) {
    console.error('[公开API] rankings错误:', error.message);
    res.status(500).json({
      success: false,
      error: '获取排名数据失败: ' + error.message
    });
  }
});

// ==================== 计算与汇率 API ====================

/**
 * 基础计算 API
 */
router.post('/calculate', (req, res) => {
  const { totalCost, totalDays, usedDays } = req.body;

  try {
    const result = calculateRemainingValue(totalCost, totalDays, usedDays);
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    res.status(400).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 按周期计算 API
 */
router.post('/calculate-by-cycle', (req, res) => {
  const { totalCost, cycle, purchaseDate } = req.body;

  try {
    const totalDays = getDaysByCycle(cycle);
    const usedDays = calculateUsedDays(purchaseDate);
    const result = calculateRemainingValue(totalCost, totalDays, usedDays);

    res.json({
      success: true,
      data: {
        ...result,
        cycle,
        purchaseDate
      }
    });
  } catch (error) {
    res.status(400).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 获取汇率 API
 */
router.get('/exchange-rate', async (req, res) => {
  const { from, to } = req.query;

  if (!from || !to) {
    return res.status(400).json({
      success: false,
      error: '缺少参数: from, to'
    });
  }

  try {
    const fromUpper = from.toUpperCase();
    const toUpper = to.toUpperCase();

    const result = await fetchExchangeRate(fromUpper, toUpper);

    res.json({
      success: true,
      data: {
        base: fromUpper,
        target: toUpper,
        rate: result.rate,
        timestamp: new Date().toISOString(),
        source: result.source,
        fromCache: result.fromCache || false
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ==================== CPU 性能 API ====================

/**
 * 获取 CPU 型号列表
 */
router.get('/cpu/models', (req, res) => {
  res.json({
    success: true,
    data: getSupportedCPUs()
  });
});

/**
 * 获取性价比排行榜
 */
router.post('/performance/rankings', authMiddleware, (req, res) => {
  const { vpsList, sortBy = 'overall' } = req.body;

  if (!vpsList || !Array.isArray(vpsList)) {
    return res.status(400).json({
      success: false,
      error: 'vpsList 参数无效'
    });
  }

  try {
    const rankings = calculateRankings(vpsList, sortBy);

    res.json({
      success: true,
      data: rankings,
      sortBy
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 生成性价比报告
 */
router.post('/performance/report', authMiddleware, (req, res) => {
  const { vpsList } = req.body;

  if (!vpsList || !Array.isArray(vpsList)) {
    return res.status(400).json({
      success: false,
      error: 'vpsList 参数无效'
    });
  }

  try {
    const report = generatePerformanceReport(vpsList);

    res.json({
      success: true,
      data: report
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

module.exports = router;
