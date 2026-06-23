const logger = require('../../lib/logger');

/**
 * Telegram通知服务
 */
class TelegramNotifier {
  constructor() {
    this.token = process.env.TELEGRAM_BOT_TOKEN;
    this.chatId = process.env.TELEGRAM_CHAT_ID;
    this.bot = null;
    this.enabled = false;

    this.initialize();
  }

  /**
   * 初始化Telegram Bot
   */
  initialize() {
    if (!this.token || !this.chatId) {
      logger.warn('⚠️  Telegram通知未配置 (需要 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID)');
      return;
    }

    try {
      this.bot = new TelegramBot(this.token, { polling: false });
      this.enabled = true;
      logger.info('✅ Telegram通知服务已启用');
    } catch (error) {
      logger.error(`❌ Telegram Bot初始化失败: ${error.message}`);
    }
  }

  /**
   * 发送文本消息
   */
  async sendMessage(message, options = {}) {
    if (!this.enabled) {
      logger.info(`📝 [模拟通知] ${message}`);
      return { success: false, reason: 'Telegram未配置' };
    }

    try {
      const defaultOptions = {
        parse_mode: 'Markdown',
        disable_web_page_preview: true,
        ...options
      };

      await this.bot.sendMessage(this.chatId, message, defaultOptions);
      logger.info('✅ Telegram消息已发送');
      return { success: true };
    } catch (error) {
      logger.error(`❌ 发送Telegram消息失败: ${error.message}`);
      return { success: false, error: error.message };
    }
  }

  /**
   * 发送VPS到期提醒
   */
  async sendExpiryAlert(vps, daysRemaining) {
    const urgencyLevel = this.getUrgencyLevel(daysRemaining);
    const emoji = this.getUrgencyEmoji(urgencyLevel);

    const message = `
${emoji} *VPS到期提醒*

📦 服务器: \`${vps.name}\`
🏷️ 提供商: ${vps.provider || '未知'}
📍 位置: ${vps.location || '未知'}
⏰ 剩余天数: *${daysRemaining} 天*
📅 到期日期: ${vps.expiryDate || '未知'}
💰 价格: ${vps.price || '未知'} ${vps.currency || 'CNY'}

${urgencyLevel === 'critical' ? '⚠️ *紧急！请立即续费！*' : ''}
${urgencyLevel === 'warning' ? '⚠️ *请尽快续费*' : ''}
${urgencyLevel === 'info' ? 'ℹ️ 提前提醒，可以开始计划续费' : ''}
`;

    return await this.sendMessage(message.trim());
  }

  /**
   * 发送批量到期提醒汇总
   */
  async sendExpiryBatchAlert(expiringVps) {
    if (expiringVps.length === 0) {
      return { success: false, reason: '无到期服务器' };
    }

    const critical = expiringVps.filter(v => v.daysRemaining <= 3);
    const warning = expiringVps.filter(v => v.daysRemaining > 3 && v.daysRemaining <= 7);
    const info = expiringVps.filter(v => v.daysRemaining > 7 && v.daysRemaining <= 30);

    let message = '🔔 *VPS到期提醒汇总*\n\n';

    if (critical.length > 0) {
      message += `🚨 *紧急到期 (≤3天)*\n`;
      critical.forEach(v => {
        message += `  • \`${v.name}\` - ${v.daysRemaining}天\n`;
      });
      message += '\n';
    }

    if (warning.length > 0) {
      message += `⚠️ *即将到期 (4-7天)*\n`;
      warning.forEach(v => {
        message += `  • \`${v.name}\` - ${v.daysRemaining}天\n`;
      });
      message += '\n';
    }

    if (info.length > 0) {
      message += `ℹ️ *提前提醒 (8-30天)*\n`;
      info.forEach(v => {
        message += `  • \`${v.name}\` - ${v.daysRemaining}天\n`;
      });
    }

    message += `\n📊 总计: ${expiringVps.length} 台服务器`;

    return await this.sendMessage(message.trim());
  }

  /**
   * 发送健康检查告警
   */
  async sendHealthAlert(vps, issue) {
    const message = `
🚨 *VPS健康检查告警*

📦 服务器: \`${vps.name}\`
📍 位置: ${vps.location || '未知'}
🔴 问题: ${issue.type}
📝 详情: ${issue.message}
⏰ 时间: ${new Date().toLocaleString('zh-CN')}

${issue.suggestion ? `💡 建议: ${issue.suggestion}` : ''}
`;

    return await this.sendMessage(message.trim());
  }

  /**
   * 发送每日报告
   */
  async sendDailyReport(stats) {
    const message = `
📊 *VPS Manager 每日报告*

🖥️ 总服务器: ${stats.totalServers} 台
✅ 在线: ${stats.onlineServers} 台
❌ 离线: ${stats.offlineServers} 台
⏰ 即将到期: ${stats.expiringServers} 台

💰 本月支出: ¥${stats.monthlyCost || 0}
📈 环比上月: ${stats.costChange || '+0%'}

${stats.alerts && stats.alerts.length > 0 ?
  `⚠️ 今日告警: ${stats.alerts.length} 条` : '✅ 今日无告警'}
`;

    return await this.sendMessage(message.trim());
  }

  /**
   * 获取紧急程度等级
   */
  getUrgencyLevel(daysRemaining) {
    if (daysRemaining <= 3) return 'critical';
    if (daysRemaining <= 7) return 'warning';
    if (daysRemaining <= 30) return 'info';
    return 'normal';
  }

  /**
   * 获取紧急程度emoji
   */
  getUrgencyEmoji(level) {
    const emojiMap = {
      critical: '🚨',
      warning: '⚠️',
      info: 'ℹ️',
      normal: '📢'
    };
    return emojiMap[level] || '📢';
  }

  /**
   * 测试连接
   */
  async testConnection() {
    if (!this.enabled) {
      return { success: false, error: 'Telegram未配置' };
    }

    try {
      const me = await this.bot.getMe();
      await this.sendMessage('✅ Telegram通知测试成功！\n\nBot已就绪，可以接收VPS到期提醒。');
      return { success: true, botInfo: me };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
}

// 单例模式
let notifierInstance = null;

function getTelegramNotifier() {
  if (!notifierInstance) {
    notifierInstance = new TelegramNotifier();
  }
  return notifierInstance;
}

module.exports = {
  TelegramNotifier,
  getTelegramNotifier
};
