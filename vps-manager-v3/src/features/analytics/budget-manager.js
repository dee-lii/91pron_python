const { BudgetDB } = require('../../database');
const { getCostAnalyzer } = require('./cost-analyzer');

/**
 * 预算管理器
 * 提供预算设置、监控和告警功能
 */
class BudgetManager {
  /**
   * 获取预算使用情况
   */
  getBudgetStatus(periodType) {
    const budget = BudgetDB.getByPeriodType(periodType);

    if (!budget) {
      return {
        hasBudget: false,
        periodType: periodType,
        message: `未设置${periodType === 'monthly' ? '月度' : '年度'}预算`
      };
    }

    const costAnalyzer = getCostAnalyzer();
    const costStats = costAnalyzer.getTotalCostStats();

    const actualCost = periodType === 'monthly' ? costStats.monthly : costStats.yearly;
    const used = actualCost;
    const remaining = budget.amount - used;
    const usagePercentage = (used / budget.amount) * 100;

    return {
      hasBudget: true,
      budget: {
        id: budget.id,
        amount: budget.amount,
        currency: budget.currency,
        periodType: budget.period_type,
        startDate: budget.start_date,
        endDate: budget.end_date,
        notes: budget.notes
      },
      usage: {
        used: parseFloat(used.toFixed(2)),
        remaining: parseFloat(remaining.toFixed(2)),
        percentage: parseFloat(usagePercentage.toFixed(2)),
        isOverBudget: remaining < 0
      },
      alert: this.generateAlert(usagePercentage, remaining)
    };
  }

  /**
   * 生成预算告警
   */
  generateAlert(usagePercentage, remaining) {
    if (remaining < 0) {
      return {
        level: 'critical',
        message: '预算已超支！',
        icon: '🚨',
        suggestion: '建议立即调整预算或优化成本'
      };
    }

    if (usagePercentage >= 90) {
      return {
        level: 'warning',
        message: '预算使用率已超过90%',
        icon: '⚠️',
        suggestion: '预算即将用尽，请注意控制成本'
      };
    }

    if (usagePercentage >= 75) {
      return {
        level: 'info',
        message: '预算使用率已超过75%',
        icon: 'ℹ️',
        suggestion: '请关注预算使用情况'
      };
    }

    return {
      level: 'normal',
      message: '预算使用正常',
      icon: '✅',
      suggestion: null
    };
  }

  /**
   * 获取完整的预算概览
   */
  getOverview() {
    const monthlyStatus = this.getBudgetStatus('monthly');
    const yearlyStatus = this.getBudgetStatus('yearly');

    return {
      monthly: monthlyStatus,
      yearly: yearlyStatus
    };
  }

  /**
   * 预测预算耗尽日期（基于当前使用率）
   */
  predictExhaustionDate(periodType) {
    const status = this.getBudgetStatus(periodType);

    if (!status.hasBudget) {
      return null;
    }

    if (status.usage.isOverBudget) {
      return {
        exhausted: true,
        message: '预算已超支'
      };
    }

    // 简单预测：假设每月/每年支出恒定
    const daysInPeriod = periodType === 'monthly' ? 30 : 365;
    const dailyCost = status.usage.used / 30; // 假设当前是月初到现在的数据
    const daysToExhaustion = status.usage.remaining / dailyCost;

    if (daysToExhaustion > daysInPeriod) {
      return {
        exhausted: false,
        message: `按当前使用率，预算可支撑到${periodType === 'monthly' ? '月' : '年'}底`
      };
    }

    const exhaustionDate = new Date();
    exhaustionDate.setDate(exhaustionDate.getDate() + Math.floor(daysToExhaustion));

    return {
      exhausted: false,
      estimatedDate: exhaustionDate.toISOString().split('T')[0],
      daysRemaining: Math.floor(daysToExhaustion),
      message: `预计${Math.floor(daysToExhaustion)}天后预算耗尽`
    };
  }

  /**
   * 获取预算健康度评分 (0-100)
   */
  getHealthScore(periodType) {
    const status = this.getBudgetStatus(periodType);

    if (!status.hasBudget) {
      return {
        score: null,
        message: '未设置预算'
      };
    }

    let score = 100;

    // 根据使用率扣分
    if (status.usage.percentage > 100) {
      score = 0; // 超支
    } else if (status.usage.percentage > 90) {
      score = 30;
    } else if (status.usage.percentage > 75) {
      score = 60;
    } else if (status.usage.percentage > 50) {
      score = 85;
    }

    return {
      score: score,
      rating: this.getRating(score),
      message: this.getHealthMessage(score)
    };
  }

  /**
   * 获取评级
   */
  getRating(score) {
    if (score >= 85) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 30) return 'fair';
    return 'poor';
  }

  /**
   * 获取健康度消息
   */
  getHealthMessage(score) {
    if (score >= 85) return '预算使用健康';
    if (score >= 60) return '预算使用良好';
    if (score >= 30) return '预算使用紧张';
    return '预算超支或即将超支';
  }

  /**
   * 建议预算调整
   */
  suggestBudgetAdjustment(periodType) {
    const status = this.getBudgetStatus(periodType);

    if (!status.hasBudget) {
      const costAnalyzer = getCostAnalyzer();
      const costStats = costAnalyzer.getTotalCostStats();
      const currentCost = periodType === 'monthly' ? costStats.monthly : costStats.yearly;

      return {
        suggested: parseFloat((currentCost * 1.2).toFixed(2)), // 建议120%的当前成本
        reason: '建议设置预算为当前成本的120%，留有20%缓冲空间'
      };
    }

    if (status.usage.isOverBudget) {
      return {
        suggested: parseFloat((status.usage.used * 1.1).toFixed(2)),
        reason: '当前已超支，建议将预算调整为实际使用的110%'
      };
    }

    if (status.usage.percentage > 90) {
      return {
        suggested: parseFloat((status.budget.amount * 1.15).toFixed(2)),
        reason: '使用率超过90%，建议增加15%预算'
      };
    }

    return {
      suggested: status.budget.amount,
      reason: '当前预算设置合理，无需调整'
    };
  }
}

// 单例模式
let managerInstance = null;

function getBudgetManager() {
  if (!managerInstance) {
    managerInstance = new BudgetManager();
  }
  return managerInstance;
}

module.exports = {
  BudgetManager,
  getBudgetManager
};
