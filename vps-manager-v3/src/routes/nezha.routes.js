const express = require('express');
const router = express.Router();
const NezhaClient = require('../nezha-client');
const { authMiddleware } = require('../auth');
const {
  updateNezhaConfig,
  getCurrentNezhaConfig,
  getLastSyncResult,
  getAutoSyncStatus,
  startAutoSync,
  stopAutoSync
} = require('../services/nezha-sync');

// ==================== 哪吒探针 API ====================

/**
 * 获取哪吒配置
 */
router.get('/config', authMiddleware, (req, res) => {
  const nezhaConfig = getCurrentNezhaConfig();
  res.json({
    success: true,
    data: {
      ...nezhaConfig,
      token: nezhaConfig.token ? '****' + nezhaConfig.token.slice(-4) : ''
    }
  });
});

/**
 * 设置哪吒配置
 */
router.post('/config', authMiddleware, (req, res) => {
  const { apiUrl, token, autoSync, syncInterval } = req.body;
  const newConfig = { apiUrl, token, autoSync, syncInterval };
  
  const updatedConfig = updateNezhaConfig(newConfig);

  res.json({
    success: true,
    message: '哪吒配置已保存',
    autoSyncEnabled: updatedConfig.autoSync
  });
});

/**
 * 测试哪吒连接
 */
router.post('/test', authMiddleware, async (req, res) => {
  const { apiUrl, token } = req.body;
  const nezhaConfig = getCurrentNezhaConfig();

  try {
    const client = new NezhaClient(apiUrl || nezhaConfig.apiUrl, token || nezhaConfig.token);
    const isConnected = await client.testConnection();

    if (isConnected) {
      res.json({
        success: true,
        message: '连接成功'
      });
    } else {
      throw new Error('连接失败');
    }
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 从哪吒同步服务器列表
 */
router.get('/servers', authMiddleware, async (req, res) => {
  try {
    const nezhaConfig = getCurrentNezhaConfig();
    
    if (!nezhaConfig.apiUrl || !nezhaConfig.token) {
      return res.status(400).json({
        success: false,
        error: '请先配置哪吒 API'
      });
    }

    const client = new NezhaClient(nezhaConfig.apiUrl, nezhaConfig.token);
    const servers = await client.syncServers();

    res.json({
      success: true,
      data: servers,
      count: servers.length
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 手动同步哪吒数据
 */
router.post('/sync', authMiddleware, async (req, res) => {
  try {
    const nezhaConfig = getCurrentNezhaConfig();

    if (!nezhaConfig.apiUrl || !nezhaConfig.token) {
      return res.status(400).json({
        success: false,
        error: '请先配置哪吒 API'
      });
    }

    const client = new NezhaClient(nezhaConfig.apiUrl, nezhaConfig.token);
    const servers = await client.syncServers();

    res.json({
      success: true,
      data: servers,
      message: `成功同步 ${servers.length} 台服务器`,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 获取自动同步状态
 */
router.get('/auto-sync/status', authMiddleware, (req, res) => {
  const status = getAutoSyncStatus();
  res.json({
    success: true,
    data: status
  });
});

module.exports = router;
