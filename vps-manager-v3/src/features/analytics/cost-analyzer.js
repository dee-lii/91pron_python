const { VpsDB } = require('../../database');
const { getDaysByCycle } = require('../../calculator');

/**
 * 成本分析器
 * 提供各种维度的成本统计和趋势分析
 */
class CostAnalyzer {
  /**
   * 计算单个VPS的月均成本
   */
  calculateMonthlyCost(vps) {
    if (!vps.price || !vps.cycle) {
      return 0;
    }

    try {
      const totalDays = getDaysByCycle(vps.cycle);
      const monthlyDays = 30;

      // 将价格转换为月均成本
      return (vps.price / totalDays) * monthlyDays;
    } catch (error) {
      // 不支持的周期，返回0
      console.warn(`[成本分析] 不支持的周期: ${vps.cycle} (VPS: ${vps.name})`);
      return 0;
    }
  }

  /**
   * 计算单个VPS的年均成本
   */
  calculateYearlyCost(vps) {
    return this.calculateMonthlyCost(vps) * 12;
  }

  /**
   * 获取总成本统计
   */
  getTotalCostStats() {
    const vpsList = VpsDB.getAll();

    let totalMonthly = 0;
    let totalYearly = 0;
    let activeCurrency = 'CNY';

    vpsList.forEach(vps => {
      totalMonthly += this.calculateMonthlyCost(vps);
      totalYearly += this.calculateYearlyCost(vps);
      if (vps.currency) {
        activeCurrency = vps.currency;
      }
    });

    return {
      monthly: parseFloat(totalMonthly.toFixed(2)),
      yearly: parseFloat(totalYearly.toFixed(2)),
      currency: activeCurrency,
      serverCount: vpsList.length
    };
  }

  /**
   * 按提供商分组统计成本
   */
  getCostByProvider() {
    const vpsList = VpsDB.getAll();
    const providerStats = {};

    vpsList.forEach(vps => {
      const provider = vps.provider || '未知';

      if (!providerStats[provider]) {
        providerStats[provider] = {
          provider: provider,
          monthly: 0,
          yearly: 0,
          count: 0,
          servers: []
        };
      }

      providerStats[provider].monthly += this.calculateMonthlyCost(vps);
      providerStats[provider].yearly += this.calculateYearlyCost(vps);
      providerStats[provider].count += 1;
      providerStats[provider].servers.push({
        id: vps.id,
        name: vps.name,
        price: vps.price,
        cycle: vps.cycle
      });
    });

    // 转换为数组并排序
    const results = Object.values(providerStats).map(stat => ({
      ...stat,
      monthly: parseFloat(stat.monthly.toFixed(2)),
      yearly: parseFloat(stat.yearly.toFixed(2))
    }));

    return results.sort((a, b) => b.monthly - a.monthly);
  }

  /**
   * 按计费周期分组统计成本
   */
  getCostByCycle() {
    const vpsList = VpsDB.getAll();
    const cycleStats = {};

    vpsList.forEach(vps => {
      const cycle = vps.cycle || 'unknown';

      if (!cycleStats[cycle]) {
        cycleStats[cycle] = {
          cycle: cycle,
          monthly: 0,
          yearly: 0,
          count: 0,
          totalPrice: 0
        };
      }

      cycleStats[cycle].monthly += this.calculateMonthlyCost(vps);
      cycleStats[cycle].yearly += this.calculateYearlyCost(vps);
      cycleStats[cycle].count += 1;
      cycleStats[cycle].totalPrice += vps.price || 0;
    });

    const results = Object.values(cycleStats).map(stat => ({
      ...stat,
      monthly: parseFloat(stat.monthly.toFixed(2)),
      yearly: parseFloat(stat.yearly.toFixed(2)),
      totalPrice: parseFloat(stat.totalPrice.toFixed(2)),
      avgPrice: parseFloat((stat.totalPrice / stat.count).toFixed(2))
    }));

    return results.sort((a, b) => b.monthly - a.monthly);
  }

  /**
   * 按地理位置分组统计成本
   */
  getCostByLocation() {
    const vpsList = VpsDB.getAll();
    const locationStats = {};

    vpsList.forEach(vps => {
      const location = vps.location || '未知';

      if (!locationStats[location]) {
        locationStats[location] = {
          location: location,
          monthly: 0,
          yearly: 0,
          count: 0
        };
      }

      locationStats[location].monthly += this.calculateMonthlyCost(vps);
      locationStats[location].yearly += this.calculateYearlyCost(vps);
      locationStats[location].count += 1;
    });

    const results = Object.values(locationStats).map(stat => ({
      ...stat,
      monthly: parseFloat(stat.monthly.toFixed(2)),
      yearly: parseFloat(stat.yearly.toFixed(2))
    }));

    return results.sort((a, b) => b.monthly - a.monthly);
  }

  /**
   * 获取成本趋势数据（模拟过去12个月）
   * 注：实际应用中需要历史数据表支持
   */
  getCostTrend(months = 12) {
    const currentStats = this.getTotalCostStats();
    const trend = [];

    const now = new Date();

    for (let i = months - 1; i >= 0; i--) {
      const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

      // 当前只返回当前月的数据，其他月份为0
      // 未来可以通过历史数据表获取实际数据
      trend.push({
        month: monthKey,
        cost: i === 0 ? currentStats.monthly : 0,
        serverCount: i === 0 ? currentStats.serverCount : 0
      });
    }

    return trend;
  }

  /**
   * 获取成本占比分析
   */
  getCostDistribution() {
    const total = this.getTotalCostStats();
    const byProvider = this.getCostByProvider();
    const byCycle = this.getCostByCycle();

    return {
      total: total,
      byProvider: byProvider.map(p => ({
        name: p.provider,
        value: p.monthly,
        percentage: parseFloat(((p.monthly / total.monthly) * 100).toFixed(2)),
        count: p.count
      })),
      byCycle: byCycle.map(c => ({
        name: c.cycle,
        value: c.monthly,
        percentage: parseFloat(((c.monthly / total.monthly) * 100).toFixed(2)),
        count: c.count
      }))
    };
  }

  /**
   * 获取成本排名（Top N最贵的VPS）
   */
  getTopExpensiveServers(limit = 10) {
    const vpsList = VpsDB.getAll();

    const serversWithMonthlyCost = vpsList.map(vps => ({
      id: vps.id,
      name: vps.name,
      provider: vps.provider,
      location: vps.location,
      price: vps.price,
      cycle: vps.cycle,
      currency: vps.currency,
      monthlyCost: this.calculateMonthlyCost(vps),
      yearlyCost: this.calculateYearlyCost(vps)
    }));

    return serversWithMonthlyCost
      .sort((a, b) => b.monthlyCost - a.monthlyCost)
      .slice(0, limit)
      .map((server, index) => ({
        rank: index + 1,
        ...server,
        monthlyCost: parseFloat(server.monthlyCost.toFixed(2)),
        yearlyCost: parseFloat(server.yearlyCost.toFixed(2))
      }));
  }

  /**
   * 获取完整的成本分析报告
   */
  getFullAnalysis() {
    return {
      overview: this.getTotalCostStats(),
      byProvider: this.getCostByProvider(),
      byCycle: this.getCostByCycle(),
      byLocation: this.getCostByLocation(),
      distribution: this.getCostDistribution(),
      topExpensive: this.getTopExpensiveServers(10),
      trend: this.getCostTrend(12)
    };
  }
}

// 单例模式
let analyzerInstance = null;

function getCostAnalyzer() {
  if (!analyzerInstance) {
    analyzerInstance = new CostAnalyzer();
  }
  return analyzerInstance;
}

module.exports = {
  CostAnalyzer,
  getCostAnalyzer
};
