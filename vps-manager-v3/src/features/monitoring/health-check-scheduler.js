const cron = require('node-cron');
const { ConfigDB } = require('../../database');
const { getHealthChecker } = require('./health-checker');
const { getTelegramNotifier } = require('../notification/telegram-notifier');
const logger = require('../../lib/logger');

/**
 * 健康检查调度器
 * 定期检查VPS健康状态，发现问题时发送告警
 */
class HealthCheckScheduler {
  constructor() {
    this.task = null;
    this.isRunning = false;
    this.lastCheckTime = null;
    this.lastCheckResult = null;
  }

  /**
   * 启动健康检查调度器
   */
  start() {
    // 检查是否已启用
    const config = this.getConfig();

    if (!config.enabled) {
      logger.info('❌ 健康检查调度器未启用（需要手动开启）');
      return;
    }

    if (this.isRunning) {
      logger.warn('⚠️  健康检查调度器已在运行');
      return;
    }

    // 创建定时任务
    // 默认：每小时检查一次
    const cronExpression = config.cronExpression || '0 * * * *';

    this.task = cron.schedule(cronExpression, async () => {
      await this.executeCheck();
    });

    this.isRunning = true;
    logger.info(`✅ 健康检查调度器已启动`);
    logger.info(`   检查时间: ${cronExpression}`);
    logger.info(`   告警阈值: 评分 < ${config.alertThreshold || 80}`);

    // 开发模式：立即执行一次检查（可选）
    if (process.env.NODE_ENV === 'development' && config.checkOnStartup) {
      logger.info('🔍 开发模式：立即执行一次健康检查...');
      setTimeout(() => this.executeCheck(), 3000);
    }
  }

  /**
   * 停止健康检查调度器
   */
  stop() {
    if (this.task) {
      this.task.stop();
      this.task = null;
    }

    this.isRunning = false;
    logger.info('❌ 健康检查调度器已停止');
  }

  /**
   * 重启调度器
   */
  restart() {
    this.stop();
    this.start();
  }

  /**
   * 执行健康检查
   */
  async executeCheck() {
    logger.info('[健康检查] 开始执行...');

    try {
      const checker = getHealthChecker();
      const overview = await checker.getHealthOverview();

      this.lastCheckTime = new Date().toISOString();
      this.lastCheckResult = overview;

      logger.info(`[健康检查] 完成 - 总计 ${overview.totalVps} 台VPS`);
      logger.info(`[健康检查] 平均评分: ${overview.avgScore}`);
      logger.info(`[健康检查] 有问题的VPS: ${overview.problematicVps.length} 台`);

      // 记录到历史数据
      const tracker = getHistoryTracker();
      await tracker.recordHealthCheck('scheduled');

      // 如果有问题的VPS，发送告警
      if (overview.problematicVps.length > 0) {
        await this.sendAlert(overview);
      }

      return overview;
    } catch (error) {
      logger.error(`[健康检查] 失败: ${error.message}`);
      return null;
    }
  }

  /**
   * 发送告警
   */
  async sendAlert(overview) {
    const config = this.getConfig();

    // 检查是否启用了Telegram告警
    if (!config.telegramAlertEnabled) {
      logger.info('[健康检查] Telegram告警未启用，跳过发送');
      return;
    }

    try {
      const notifier = getTelegramNotifier();

      // 构建告警消息
      const message = this.buildAlertMessage(overview);

      // 发送Telegram通知
      await notifier.sendMessage(message);

      logger.info('[健康检查] Telegram告警已发送');
    } catch (error) {
      logger.error(`[健康检查] 发送告警失败: ${error.message}`);
    }
  }

  /**
   * 构建告警消息
   */
  buildAlertMessage(overview) {
    const { problematicVps, avgScore, statusCount } = overview;

    let message = '🚨 *VPS健康告警*\n\n';
    message += `📊 *健康概览*\n`;
    message += `• 平均评分: ${avgScore}/100\n`;
    message += `• 健康: ${statusCount.healthy} 台\n`;
    message += `• 警告: ${statusCount.warning} 台\n`;
    message += `• 严重: ${statusCount.critical} 台\n`;
    message += `• 宕机: ${statusCount.down} 台\n\n`;

    message += `⚠️ *有问题的VPS (${problematicVps.length}台)*\n\n`;

    problematicVps.forEach((vps, index) => {
      const statusIcon = this.getStatusIcon(vps.status);
      message += `${index + 1}. ${statusIcon} *${vps.name}*\n`;
      message += `   评分: ${vps.score}/100\n`;
      message += `   问题: ${vps.issues.join(', ')}\n\n`;
    });

    message += `🕐 检查时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}`;

    return message;
  }

  /**
   * 获取状态图标
   */
  getStatusIcon(status) {
    const icons = {
      healthy: '✅',
      warning: '⚠️',
      critical: '🔴',
      down: '❌',
      unknown: '❓'
    };
    return icons[status] || icons.unknown;
  }

  /**
   * 获取配置
   */
  getConfig() {
    const config = ConfigDB.get('health_check_scheduler') || {};

    return {
      enabled: config.enabled || false,                      // 默认关闭
      cronExpression: config.cronExpression || '0 * * * *',  // 默认每小时
      alertThreshold: config.alertThreshold || 80,           // 默认评分<80告警
      telegramAlertEnabled: config.telegramAlertEnabled || false,  // 默认关闭Telegram告警
      checkOnStartup: config.checkOnStartup || false         // 默认启动时不检查
    };
  }

  /**
   * 更新配置
   */
  updateConfig(newConfig) {
    const currentConfig = this.getConfig();
    const updatedConfig = { ...currentConfig, ...newConfig };

    ConfigDB.set('health_check_scheduler', updatedConfig);

    // 如果修改了启用状态或cron表达式，重启调度器
    if ('enabled' in newConfig || 'cronExpression' in newConfig) {
      this.restart();
    }

    return updatedConfig;
  }

  /**
   * 获取调度器状态
   */
  getStatus() {
    const config = this.getConfig();

    return {
      enabled: config.enabled,
      isRunning: this.isRunning,
      cronExpression: config.cronExpression,
      alertThreshold: config.alertThreshold,
      telegramAlertEnabled: config.telegramAlertEnabled,
      lastCheckTime: this.lastCheckTime,
      lastCheckResult: this.lastCheckResult
    };
  }
}

// 单例模式
let schedulerInstance = null;

function getHealthCheckScheduler() {
  if (!schedulerInstance) {
    schedulerInstance = new HealthCheckScheduler();
  }
  return schedulerInstance;
}

module.exports = {
  HealthCheckScheduler,
  getHealthCheckScheduler
};
