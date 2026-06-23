const { HealthHistoryDB, CostHistoryDB, BudgetHistoryDB } = require('../../database');
const { getHealthChecker } = require('./health-checker');
const { getCostAnalyzer } = require('../analytics/cost-analyzer');
const { getBudgetManager } = require('../analytics/budget-manager');

/**
 * 历史数据追踪器
 * 负责记录健康检查、成本和预算使用的历史数据
 */
class HistoryTracker {
  constructor() {
    this.isInitialized = false;
  }

  /**
   * 记录健康检查结果到历史
   */
  async recordHealthCheck(checkType = 'manual') {
    try {
      const checker = getHealthChecker();
      const overview = await checker.getHealthOverview();

      const historyData = {
        checkType, // 'scheduled' 或 'manual'
        totalVps: overview.totalVps,
        avgScore: overview.avgScore,
        healthyCount: overview.statusCount.healthy,
        warningCount: overview.statusCount.warning,
        criticalCount: overview.statusCount.critical,
        downCount: overview.statusCount.down,
        problematicVps: overview.problematicVps.map(vps => ({
          id: vps.id,
          name: vps.name,
          status: vps.status,
          score: vps.score,
          issues: vps.issues
        }))
      };

      const result = HealthHistoryDB.create(historyData);
      console.log(`[历史追踪] 已记录健康检查数据 (ID: ${result.id})`);
      return result;
    } catch (error) {
      console.error('[历史追踪] 记录健康检查数据失败:', error.message);
      return null;
    }
  }

  /**
   * 记录成本快照到历史
   */
  recordCostSnapshot() {
    try {
      const costAnalyzer = getCostAnalyzer();
      const stats = costAnalyzer.getTotalCostStats();
      const byProvider = costAnalyzer.getCostByProvider();
      const byCycle = costAnalyzer.getCostByCycle();

      const now = new Date();
      const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

      const historyData = {
        period,
        totalMonthlyCost: stats.monthly,
        totalYearlyCost: stats.yearly,
        vpsCount: stats.count,
        currency: 'CNY',
        byProvider: byProvider.map(p => ({
          provider: p.provider,
          monthlyCost: p.monthlyCost,
          count: p.count
        })),
        byCycle: byCycle.map(c => ({
          cycle: c.cycle,
          monthlyCost: c.monthlyCost,
          count: c.count
        }))
      };

      const result = CostHistoryDB.create(historyData);
      console.log(`[历史追踪] 已记录成本快照 (ID: ${result.id}, 月成本: ${stats.monthly})`);
      return result;
    } catch (error) {
      console.error('[历史追踪] 记录成本快照失败:', error.message);
      return null;
    }
  }

  /**
   * 记录预算使用情况到历史
   */
  recordBudgetUsage(periodType) {
    try {
      const budgetManager = getBudgetManager();
      const status = budgetManager.getBudgetStatus(periodType);

      if (!status || !status.budget) {
        console.log(`[历史追踪] 未找到${periodType}预算，跳过记录`);
        return null;
      }

      const historyData = {
        budgetId: status.budget.id,
        periodType: status.budget.periodType,
        budgetAmount: status.budget.amount,
        usedAmount: status.usage.used,
        remainingAmount: status.usage.remaining,
        usagePercentage: status.usage.percentage,
        alertLevel: status.alert.level
      };

      const result = BudgetHistoryDB.create(historyData);
      console.log(`[历史追踪] 已记录预算使用 (ID: ${result.id}, 使用率: ${status.usage.percentage.toFixed(1)}%)`);
      return result;
    } catch (error) {
      console.error('[历史追踪] 记录预算使用失败:', error.message);
      return null;
    }
  }

  /**
   * 记录所有活跃预算的使用情况
   */
  recordAllBudgetUsage() {
    const results = [];

    // 记录月度预算
    const monthlyResult = this.recordBudgetUsage('monthly');
    if (monthlyResult) results.push(monthlyResult);

    // 记录年度预算
    const yearlyResult = this.recordBudgetUsage('yearly');
    if (yearlyResult) results.push(yearlyResult);

    return results;
  }

  /**
   * 执行完整的每日快照
   * 记录健康、成本和预算数据
   */
  async takeDailySnapshot() {
    console.log('[历史追踪] 开始执行每日快照...');

    const results = {
      health: null,
      cost: null,
      budgets: []
    };

    // 1. 记录健康检查
    results.health = await this.recordHealthCheck('scheduled');

    // 2. 记录成本快照
    results.cost = this.recordCostSnapshot();

    // 3. 记录所有预算使用
    results.budgets = this.recordAllBudgetUsage();

    console.log('[历史追踪] 每日快照完成');
    console.log(`  健康检查: ${results.health ? '✅' : '❌'}`);
    console.log(`  成本快照: ${results.cost ? '✅' : '❌'}`);
    console.log(`  预算记录: ${results.budgets.length} 条`);

    return results;
  }

  /**
   * 清理过期的历史数据
   */
  cleanupOldData() {
    console.log('[历史追踪] 开始清理过期数据...');

    const results = {
      health: 0,
      cost: 0
    };

    // 清理90天前的健康检查记录
    results.health = HealthHistoryDB.deleteOlderThan(90);

    // 清理365天前的成本记录
    results.cost = CostHistoryDB.deleteOlderThan(365);

    console.log('[历史追踪] 清理完成');
    console.log(`  健康检查: 删除 ${results.health} 条`);
    console.log(`  成本快照: 删除 ${results.cost} 条`);

    return results;
  }

  /**
   * 获取健康检查趋势
   */
  async getHealthTrend(days = 7) {
    const history = HealthHistoryDB.getByDays(days);

    return {
      period: `最近${days}天`,
      dataPoints: history.map(h => ({
        date: h.created_at,
        avgScore: h.avg_score,
        totalVps: h.total_vps,
        healthyCount: h.healthy_count,
        warningCount: h.warning_count,
        criticalCount: h.critical_count,
        downCount: h.down_count
      }))
    };
  }

  /**
   * 获取成本趋势
   */
  getCostTrend(days = 30) {
    const history = CostHistoryDB.getByDays(days);

    return {
      period: `最近${days}天`,
      dataPoints: history.map(h => ({
        date: h.created_at,
        period: h.period,
        monthlyCost: h.total_monthly_cost,
        yearlyCost: h.total_yearly_cost,
        vpsCount: h.vps_count
      }))
    };
  }

  /**
   * 获取预算使用趋势
   */
  getBudgetTrend(budgetId, days = 30) {
    const history = BudgetHistoryDB.getByBudgetId(budgetId);

    // 过滤最近N天的数据
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - days);
    const cutoffStr = cutoffDate.toISOString();

    const filtered = history.filter(h => h.created_at >= cutoffStr);

    return {
      budgetId,
      period: `最近${days}天`,
      dataPoints: filtered.map(h => ({
        date: h.created_at,
        budgetAmount: h.budget_amount,
        usedAmount: h.used_amount,
        remainingAmount: h.remaining_amount,
        usagePercentage: h.usage_percentage,
        alertLevel: h.alert_level
      }))
    };
  }

  /**
   * 获取所有趋势数据（综合视图）
   */
  async getAllTrends(days = 7) {
    const [health, cost] = await Promise.all([
      this.getHealthTrend(days),
      Promise.resolve(this.getCostTrend(days))
    ]);

    return {
      period: `最近${days}天`,
      health,
      cost
    };
  }
}

// 单例模式
let trackerInstance = null;

function getHistoryTracker() {
  if (!trackerInstance) {
    trackerInstance = new HistoryTracker();
  }
  return trackerInstance;
}

module.exports = {
  HistoryTracker,
  getHistoryTracker
};
