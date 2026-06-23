/**
 * 哪吒探针 API 客户端
 * 用于从哪吒探针拉取服务器信息
 */

/**
 * 哪吒 API 客户端类
 */
class NezhaClient {
  constructor(apiUrl, token) {
    this.apiUrl = apiUrl?.replace(/\/$/, ''); // 移除尾部斜杠
    this.token = token;
  }

  /**
   * 发送 HTTP 请求
   * @param {string} endpoint - API 端点
   * @param {object} options - 请求选项
   * @returns {Promise<object>} 响应数据
   */
  async request(endpoint, options = {}) {
    if (!this.apiUrl || !this.token) {
      throw new Error('哪吒 API 配置不完整');
    }

    const url = `${this.apiUrl}${endpoint}`;

    const headers = {
      'Authorization': `Bearer ${this.token}`,
      'Content-Type': 'application/json',
      ...options.headers
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      throw new Error(`哪吒 API 请求失败: ${error.message}`);
    }
  }

  /**
   * 测试连接
   * @returns {Promise<boolean>} 是否连接成功
   */
  async testConnection() {
    try {
      await this.getServerList();
      return true;
    } catch (error) {
      console.error('哪吒连接测试失败:', error);
      return false;
    }
  }

  /**
   * 获取服务器列表
   * @returns {Promise<Array>} 服务器列表
   */
  async getServerList() {
    // 哪吒 v1 API 端点是 /api/v1/server（不是 /api/v1/server/list）
    const data = await this.request('/api/v1/server');
    return data.result || data.data || [];
  }

  /**
   * 获取单个服务器详情
   * @param {number} serverId - 服务器 ID
   * @returns {Promise<object>} 服务器详情
   */
  async getServerDetail(serverId) {
    const data = await this.request(`/api/v1/server/${serverId}`);
    return data.result || data.data || {};
  }

  mapToVPS(nezhaServer) {
    const host = nezhaServer.host || {};
    const state = nezhaServer.state || {};
    const geoip = nezhaServer.geoip || {};

    const cpuArray = host.cpu || host.CPU || [];
    const cpuModel = cpuArray[0] || 'Unknown CPU';
    const cpuMatch = cpuModel.match(/(\d+)\s*Virtual\s*Core/i);
    const cpuCores = cpuMatch ? parseInt(cpuMatch[1]) : (cpuArray.length || 1);

    const memTotal = host.mem_total || host.MemTotal || 0;
    const diskTotal = host.disk_total || host.DiskTotal || 0;
    const memUsed = state.mem_used || state.MemUsed || 0;
    const diskUsed = state.disk_used || state.DiskUsed || 0;
    const cpuUsage = state.cpu || state.CPU || 0;
    const uptime = state.uptime || state.Uptime || 0;

    const memoryGB = memTotal ? Math.round(memTotal / (1024 ** 3) * 10) / 10 : 0;
    const diskGB = diskTotal ? Math.round(diskTotal / (1024 ** 3)) : 0;

    const lastActive = nezhaServer.last_active;
    const isOnline = lastActive ? 
      (typeof lastActive === 'string' ? 
        (Date.now() - new Date(lastActive).getTime() < 300000) : 
        (Date.now() / 1000 - lastActive < 300)) : 
      false;

    return {
      name: nezhaServer.name || `Server ${nezhaServer.id}`,
      specs: {
        cpu: {
          model: cpuModel.replace(/\s*\d+\s*Virtual\s*Core/i, '').trim(),
          cores: cpuCores,
          threads: null
        },
        memory: { size: memoryGB, type: null },
        storage: { size: diskGB, type: null },
        network: { bandwidth: null, traffic: null }
      },
      location: geoip.country_code ? geoip.country_code.toUpperCase() : null,
      ip: geoip.ip ? (geoip.ip.ipv4_addr || geoip.ip.ipv6_addr) : null,
      nezha: {
        serverId: nezhaServer.id,
        online: isOnline,
        lastSync: new Date().toISOString(),
        uptime: uptime ? (uptime / 86400).toFixed(1) : 0,
        cpuUsage: cpuUsage,
        memUsage: memTotal ? ((memUsed / memTotal) * 100).toFixed(1) : 0,
        diskUsage: diskTotal ? ((diskUsed / diskTotal) * 100).toFixed(1) : 0,
        platform: host.platform || host.Platform || 'unknown',
        virtualization: host.virtualization || host.Virtualization || 'unknown'
      }
    };
  }

  /**
   * 同步所有服务器数据
   * @returns {Promise<Array>} VPS 格式的服务器列表
   */
  async syncServers() {
    const servers = await this.getServerList();
    return servers.map(server => this.mapToVPS(server));
  }
}

module.exports = NezhaClient;
