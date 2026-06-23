const { VpsDB, ConfigDB } = require('../../database');
const http = require('http');
const https = require('https');
const { exec } = require('child_process');
const { promisify } = require('util');

const execPromise = promisify(exec);

/**
 * VPS 健康检查器
 * 提供在线状态检测、性能监控和健康度评分功能
 */
class HealthChecker {
  /**
   * ping 检测 IP 是否在线
   * @param {string} ip - IP 地址
   * @param {number} timeout - 超时时间（毫秒）
   * @returns {Promise<Object>} { online: boolean, latency: number|null, error?: string }
   */
  async pingCheck(ip, timeout = 5000) {
    if (!ip) {
      return { online: false, latency: null, error: 'IP地址为空' };
    }

    try {
      // 根据操作系统选择 ping 命令
      const platform = process.platform;
      let pingCommand;

      if (platform === 'win32') {
        pingCommand = `ping -n 1 -w ${timeout} ${ip}`;
      } else {
        // Linux/macOS
        pingCommand = `ping -c 1 -W ${Math.ceil(timeout / 1000)} ${ip}`;
      }

      const startTime = Date.now();
      const { stdout } = await execPromise(pingCommand, { timeout });
      const latency = Date.now() - startTime;

      // 检查 ping 是否成功
      const success = stdout.includes('bytes from') || stdout.includes('来自') || stdout.includes('Reply from');

      return {
        online: success,
        latency: success ? latency : null
      };
    } catch (error) {
      return {
        online: false,
        latency: null,
        error: error.message
      };
    }
  }

  /**
   * HTTP/HTTPS 检测
   * @param {string} url - URL 地址
   * @param {number} timeout - 超时时间（毫秒）
   * @returns {Promise<Object>} { online: boolean, statusCode: number|null, latency: number|null }
   */
  async httpCheck(url, timeout = 5000) {
    if (!url) {
      return { online: false, statusCode: null, latency: null, error: 'URL为空' };
    }

    return new Promise((resolve) => {
      const startTime = Date.now();
      const protocol = url.startsWith('https') ? https : http;

      const request = protocol.get(url, { timeout }, (res) => {
        const latency = Date.now() - startTime;

        resolve({
          online: res.statusCode >= 200 && res.statusCode < 400,
          statusCode: res.statusCode,
          latency
        });

        // 消费响应数据以释放内存
        res.resume();
      });

      request.on('error', (error) => {
        resolve({
          online: false,
          statusCode: null,
          latency: null,
          error: error.message
        });
      });

      request.on('timeout', () => {
        request.destroy();
        resolve({
          online: false,
          statusCode: null,
          latency: null,
          error: '请求超时'
        });
      });
    });
  }

  /**
   * 从哪吒面板获取服务器数据
   * @param {Object} nezhaConfig - { serverId: string }
   * @returns {Promise<Object|null>} 服务器数据
   */
  async fetchNezhaData(nezhaConfig) {
    if (!nezhaConfig || !nezhaConfig.serverId) {
      return null;
    }

    try {
      // 从配置中获取哪吒面板信息
      const globalNezha = ConfigDB.get('nezha');
      if (!globalNezha || !globalNezha.apiUrl) {
        return null;
      }

      const apiUrl = `${globalNezha.apiUrl}/api/v1/server/${nezhaConfig.serverId}`;
      const token = globalNezha.token;

      // 调用哪吒 API
      const response = await this.httpCheck(apiUrl, 10000);

      if (!response.online) {
        return null;
      }

      // 这里简化处理，实际应该解析 API 返回的 JSON
      // 由于我们没有真实的哪吒 API，返回模拟数据结构
      return {
        serverId: nezhaConfig.serverId,
        online: true,
        cpu: null,
        memory: null,
        disk: null,
        network: null
      };
    } catch (error) {
      return null;
    }
  }

  /**
   * 检查单个 VPS 的健康状态
   * @param {Object} vps - VPS 对象
   * @returns {Promise<Object>} 健康检查结果
   */
  async checkVpsHealth(vps) {
    const result = {
      vpsId: vps.id,
      vpsName: vps.name,
      timestamp: new Date().toISOString(),
      checks: {},
      score: 0,
      status: 'unknown',
      issues: []
    };

    // 1. IP Ping 检测
    if (vps.ip) {
      result.checks.ping = await this.pingCheck(vps.ip);
      if (!result.checks.ping.online) {
        result.issues.push('IP无法ping通');
      }
    }

    // 2. 哪吒监控数据获取
    if (vps.nezha) {
      const nezhaData = await this.fetchNezhaData(vps.nezha);
      result.checks.nezha = nezhaData;

      if (!nezhaData) {
        result.issues.push('无法获取哪吒监控数据');
      } else if (!nezhaData.online) {
        result.issues.push('哪吒监控显示离线');
      }
    }

    // 3. 计算健康度评分
    result.score = this.calculateHealthScore(result.checks, result.issues);
    result.status = this.getHealthStatus(result.score);

    return result;
  }

  /**
   * 批量检查多个 VPS 的健康状态
   * @param {Array<string>} vpsIds - VPS ID 数组（可选，不传则检查所有）
   * @returns {Promise<Array>} 健康检查结果数组
   */
  async checkMultipleVps(vpsIds = null) {
    let vpsList;

    if (vpsIds && vpsIds.length > 0) {
      vpsList = vpsIds.map(id => VpsDB.getById(id)).filter(vps => vps !== null);
    } else {
      vpsList = VpsDB.getAll();
    }

    // 并发执行健康检查
    const results = await Promise.all(
      vpsList.map(vps => this.checkVpsHealth(vps))
    );

    return results;
  }

  /**
   * 计算健康度评分（0-100）
   * @param {Object} checks - 检查结果
   * @param {Array} issues - 问题列表
   * @returns {number} 评分
   */
  calculateHealthScore(checks, issues) {
    let score = 100;

    // Ping 检测失败扣 50 分
    if (checks.ping && !checks.ping.online) {
      score -= 50;
    }

    // Ping 延迟高扣分
    if (checks.ping && checks.ping.online && checks.ping.latency) {
      if (checks.ping.latency > 1000) {
        score -= 20; // 延迟超过 1 秒
      } else if (checks.ping.latency > 500) {
        score -= 10; // 延迟超过 500ms
      }
    }

    // 哪吒监控数据缺失或离线扣分
    if (checks.nezha === null) {
      score -= 10; // 无法获取哪吒数据
    } else if (checks.nezha && !checks.nezha.online) {
      score -= 30; // 哪吒显示离线
    }

    // 确保评分在 0-100 范围内
    return Math.max(0, Math.min(100, score));
  }

  /**
   * 根据评分获取健康状态
   * @param {number} score - 健康度评分
   * @returns {string} 状态（healthy/warning/critical/down）
   */
  getHealthStatus(score) {
    if (score >= 80) return 'healthy';
    if (score >= 50) return 'warning';
    if (score >= 20) return 'critical';
    return 'down';
  }

  /**
   * 获取健康状态的图标和颜色
   * @param {string} status - 健康状态
   * @returns {Object} { icon: string, color: string, label: string }
   */
  getHealthStatusMeta(status) {
    const meta = {
      healthy: { icon: '✅', color: 'green', label: '健康' },
      warning: { icon: '⚠️', color: 'yellow', label: '警告' },
      critical: { icon: '🔴', color: 'red', label: '严重' },
      down: { icon: '❌', color: 'black', label: '宕机' },
      unknown: { icon: '❓', color: 'gray', label: '未知' }
    };

    return meta[status] || meta.unknown;
  }

  /**
   * 获取所有 VPS 的健康概览
   * @returns {Promise<Object>} 概览数据
   */
  async getHealthOverview() {
    const vpsList = VpsDB.getAll();
    const results = await this.checkMultipleVps();

    // 统计各状态数量
    const statusCount = {
      healthy: 0,
      warning: 0,
      critical: 0,
      down: 0,
      unknown: 0
    };

    results.forEach(result => {
      statusCount[result.status] = (statusCount[result.status] || 0) + 1;
    });

    // 计算平均健康度
    const avgScore = results.length > 0
      ? parseFloat((results.reduce((sum, r) => sum + r.score, 0) / results.length).toFixed(2))
      : 0;

    // 找出有问题的 VPS
    const problematicVps = results
      .filter(r => r.score < 80)
      .sort((a, b) => a.score - b.score)
      .map(r => ({
        id: r.vpsId,
        name: r.vpsName,
        score: r.score,
        status: r.status,
        issues: r.issues
      }));

    return {
      totalVps: vpsList.length,
      statusCount,
      avgScore,
      problematicVps,
      lastCheck: new Date().toISOString()
    };
  }

  /**
   * 获取单个 VPS 的详细健康报告
   * @param {string} vpsId - VPS ID
   * @returns {Promise<Object>} 详细报告
   */
  async getDetailedReport(vpsId) {
    const vps = VpsDB.getById(vpsId);

    if (!vps) {
      throw new Error('VPS不存在');
    }

    const healthCheck = await this.checkVpsHealth(vps);
    const statusMeta = this.getHealthStatusMeta(healthCheck.status);

    return {
      vps: {
        id: vps.id,
        name: vps.name,
        provider: vps.provider,
        location: vps.location,
        ip: vps.ip
      },
      health: {
        score: healthCheck.score,
        status: healthCheck.status,
        statusMeta: statusMeta,
        issues: healthCheck.issues,
        timestamp: healthCheck.timestamp
      },
      checks: healthCheck.checks,
      recommendations: this.generateRecommendations(healthCheck)
    };
  }

  /**
   * 生成优化建议
   * @param {Object} healthCheck - 健康检查结果
   * @returns {Array<string>} 建议列表
   */
  generateRecommendations(healthCheck) {
    const recommendations = [];

    if (!healthCheck.checks.ping || !healthCheck.checks.ping.online) {
      recommendations.push('服务器无法ping通，请检查网络连接或防火墙设置');
    }

    if (healthCheck.checks.ping && healthCheck.checks.ping.latency > 1000) {
      recommendations.push('网络延迟过高，建议检查网络质量或考虑更换服务器位置');
    }

    if (!healthCheck.checks.nezha) {
      recommendations.push('未配置哪吒监控，建议安装哪吒Agent以获取更详细的性能数据');
    }

    if (healthCheck.checks.nezha && !healthCheck.checks.nezha.online) {
      recommendations.push('哪吒Agent离线，请检查Agent服务状态');
    }

    if (recommendations.length === 0) {
      recommendations.push('服务器运行正常，继续保持监控');
    }

    return recommendations;
  }
}

// 单例模式
let checkerInstance = null;

function getHealthChecker() {
  if (!checkerInstance) {
    checkerInstance = new HealthChecker();
  }
  return checkerInstance;
}

module.exports = {
  HealthChecker,
  getHealthChecker
};
