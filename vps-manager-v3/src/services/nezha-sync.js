const { getNezhaConfig } = require('../config/nezha');
const NezhaClient = require('../nezha-client');
const logger = require('../lib/logger');

let nezhaConfig = getNezhaConfig();
let autoSyncTimer = null;
let lastSyncResult = null;

async function performAutoSync() {
  if (!nezhaConfig.apiUrl || !nezhaConfig.token) {
    logger.info('[哪吒自动同步] 配置不完整，跳过');
    return;
  }

  // Check for non-ASCII characters in token
  // eslint-disable-next-line no-control-regex
  if (/[^\x00-\x7F]/.test(nezhaConfig.token)) {
    logger.error('[哪吒自动同步] Token包含非ASCII字符，跳过同步');
    return;
  }

  try {
    logger.info('[哪吒自动同步] 开始同步...');
    const client = new NezhaClient(nezhaConfig.apiUrl, nezhaConfig.token);
    const servers = await client.syncServers();
    
    lastSyncResult = {
      success: true,
      count: servers.length,
      timestamp: new Date().toISOString(),
      servers: servers
    };
    
    logger.info(`[哪吒自动同步] 成功同步 ${servers.length} 台服务器`);
  } catch (error) {
    lastSyncResult = {
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    };
    logger.error(`[哪吒自动同步] 失败: ${error.message}`);
  }
}

function startAutoSync() {
  if (autoSyncTimer) {
    clearInterval(autoSyncTimer);
    autoSyncTimer = null;
  }

  if (!nezhaConfig.autoSync) {
    logger.info('[哪吒自动同步] 已禁用');
    return;
  }

  const intervalMs = (nezhaConfig.syncInterval || 3600) * 1000;
  logger.info(`[哪吒自动同步] 启动，间隔 ${nezhaConfig.syncInterval} 秒`);
  
  performAutoSync();
  autoSyncTimer = setInterval(performAutoSync, intervalMs);
}

function stopAutoSync() {
  if (autoSyncTimer) {
    clearInterval(autoSyncTimer);
    autoSyncTimer = null;
    logger.info('[哪吒自动同步] 已停止');
  }
}

function updateNezhaConfig(newConfig) {
  if (newConfig.apiUrl) nezhaConfig.apiUrl = newConfig.apiUrl;
  if (newConfig.token) nezhaConfig.token = newConfig.token;
  if (typeof newConfig.autoSync === 'boolean') nezhaConfig.autoSync = newConfig.autoSync;
  if (newConfig.syncInterval) nezhaConfig.syncInterval = newConfig.syncInterval;

  ConfigDB.set('nezha', nezhaConfig);

  if (nezhaConfig.autoSync) {
    startAutoSync();
  } else {
    stopAutoSync();
  }
  
  return nezhaConfig;
}

function getCurrentNezhaConfig() {
  return nezhaConfig;
}

function getLastSyncResult() {
  return lastSyncResult;
}

function getAutoSyncStatus() {
  return {
    enabled: nezhaConfig.autoSync,
    running: autoSyncTimer !== null,
    interval: nezhaConfig.syncInterval,
    lastSync: lastSyncResult
  };
}

module.exports = {
  performAutoSync,
  startAutoSync,
  stopAutoSync,
  updateNezhaConfig,
  getCurrentNezhaConfig,
  getLastSyncResult,
  getAutoSyncStatus
};
