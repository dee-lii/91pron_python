const cron = require('node-cron');
const { VpsDB } = require('../../database');
const { getDaysByCycle, calculateUsedDays } = require('../../calculator');
const logger = require('../../lib/logger');
const { getTelegramNotifier } = require('./telegram-notifier');

/**
 * 续费提醒调度器
 */
class RenewalScheduler {
  constructor() {
    this.jobs = [];
    this.notifier = getTelegramNotifier();
    this.config = {
      // 检查时间: 每天早上8点
      dailyCheckCron: '0 8 * * *',
      // 提醒规则: [天数, 通知渠道]
      alertRules: [
        { days: 30, channels: ['telegram'], message: '提前30天提醒' },
        { days: 7, channels: ['telegram'], message: '提前7天提醒' },
        { days: 3, channels: ['telegram'], message: '紧急！3天内到期' },
        { days: 1, channels: ['telegram'], message: '紧急！明天到期' }
      ]
    };
  }

  /**
   * 启动调度器
   */
  start() {
    // 每日检查任务
    const dailyCheckJob = cron.schedule(
      this.config.dailyCheckCron,
      () => this.performDailyCheck(),
      {
        scheduled: true,
        timezone: 'Asia/Shanghai'
      }
    );

    this.jobs.push({
      name: 'daily-expiry-check',
      job: dailyCheckJob,
      cron: this.config.dailyCheckCron
    });

    logger.info('✅ 续费提醒调度器已启动');
    logger.info(`   检查时间: ${this.config.dailyCheckCron} (每天早上8点)`);
    logger.info(`   提醒规则: ${this.config.alertRules.length} 条`);

    // 立即执行一次检查（仅在启动时）
    if (process.env.NODE_ENV === 'development') {
      logger.info('🔍 开发模式：立即执行一次检查...');
      setTimeout(() => this.performDailyCheck(), 3000);
    }
  }

  /**
   * 停止调度器
   */
  stop() {
    this.jobs.forEach(({ name, job }) => {
      job.stop();
      logger.info(`⏹️  已停止任务: ${name}`);
    });
    this.jobs = [];
  }

  /**
   * 执行每日检查
   */
  async performDailyCheck() {
    logger.info('\n🔍 [续费检查] 开始执行每日检查...');
    const timestamp = new Date().toLocaleString('zh-CN');

    try {
      const vpsList = VpsDB.getAll();
      const expiringVps = this.getExpiringVps(vpsList);

      logger.info(`📊 [续费检查] 共检查 ${vpsList.length} 台服务器`);
      logger.info(`⏰ [续费检查] 发现 ${expiringVps.length} 台即将到期`);

      if (expiringVps.length === 0) {
        logger.info('✅ [续费检查] 暂无即将到期的服务器');
        return;
      }

      // 按紧急程度分组
      const grouped = this.groupByUrgency(expiringVps);

      // 发送汇总通知
      await this.notifier.sendExpiryBatchAlert(expiringVps);

      // 记录检查结果
      logger.info('📝 [续费检查] 检查完成');
      logger.info(`   🚨 紧急 (≤3天): ${grouped.critical.length} 台`);
      logger.info(`   ⚠️  警告 (4-7天): ${grouped.warning.length} 台`);
      logger.info(`   ℹ️  提醒 (8-30天): ${grouped.info.length} 台`);

    } catch (error) {
      logger.error(`❌ [续费检查] 执行失败: ${error.message}`);
    }
  }

  /**
   * 获取即将到期的VPS列表
   */
  getExpiringVps(vpsList) {
    const expiringVps = [];

    vpsList.forEach(vps => {
      try {
        if (!vps.cycle || !vps.purchaseDate) {
          return; // 跳过没有周期或购买日期的VPS
        }

        const totalDays = getDaysByCycle(vps.cycle);
        const usedDays = calculateUsedDays(vps.purchaseDate);
        const remainingDays = totalDays - usedDays;

        // 计算到期日期
        const purchaseTime = new Date(vps.purchaseDate).getTime();
        const expiryTime = purchaseTime + totalDays * 86400000;
        const expiryDate = new Date(expiryTime).toISOString().split('T')[0];

        // 检查是否在提醒范围内 (30天内)
        if (remainingDays > 0 && remainingDays <= 30) {
          expiringVps.push({
            ...vps,
            daysRemaining: remainingDays,
            expiryDate: expiryDate,
            urgency: this.calculateUrgency(remainingDays)
          });
        }

      } catch (error) {
        logger.error(`⚠️  处理VPS失败 (${vps.name}): ${error.message}`);
      }
    });

    // 按剩余天数排序 (最紧急的在前)
    return expiringVps.sort((a, b) => a.daysRemaining - b.daysRemaining);
  }

  /**
   * 按紧急程度分组
   */
  groupByUrgency(expiringVps) {
    return {
      critical: expiringVps.filter(v => v.daysRemaining <= 3),
      warning: expiringVps.filter(v => v.daysRemaining > 3 && v.daysRemaining <= 7),
      info: expiringVps.filter(v => v.daysRemaining > 7 && v.daysRemaining <= 30)
    };
  }

  /**
   * 计算紧急程度
   */
  calculateUrgency(daysRemaining) {
    if (daysRemaining <= 3) return 'critical';
    if (daysRemaining <= 7) return 'warning';
    return 'info';
  }

  /**
   * 手动触发检查 (用于测试)
   */
  async triggerManualCheck() {
    logger.info('🔍 手动触发续费检查...');
    await this.performDailyCheck();
  }

  /**
   * 获取下次执行时间
   */
  getNextRunTime() {
    if (this.jobs.length === 0) {
      return null;
    }

    // 计算下次8点的时间
    const now = new Date();
    const next = new Date(now);
    next.setHours(8, 0, 0, 0);

    if (next <= now) {
      next.setDate(next.getDate() + 1);
    }

    return next.toLocaleString('zh-CN');
  }

  /**
   * 获取调度器状态
   */
  getStatus() {
    return {
      running: this.jobs.length > 0,
      jobCount: this.jobs.length,
      jobs: this.jobs.map(({ name, cron }) => ({ name, cron })),
      nextRunTime: this.getNextRunTime(),
      notifierEnabled: this.notifier.enabled
    };
  }
}

// 单例模式
let schedulerInstance = null;

function getRenewalScheduler() {
  if (!schedulerInstance) {
    schedulerInstance = new RenewalScheduler();
  }
  return schedulerInstance;
}

module.exports = {
  RenewalScheduler,
  getRenewalScheduler
};
