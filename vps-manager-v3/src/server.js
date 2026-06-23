/**
 * VPS Manager v3.1 - 全生命周期管理平台
 * 提供静态文件服务、汇率 API、哪吒集成、性价比分析
 */

// 必须在所有其他导入之前加载环境变量
require('dotenv').config();

const express = require('express');
const path = require('path');
const helmet = require('helmet');
const cors = require('cors');
const { globalLimiter } = require('./middleware/rate-limit');
const { getTelegramNotifier } = require('./features/notification/telegram-notifier');
const { getRenewalScheduler } = require('./features/notification/renewal-scheduler');
const { getHealthCheckScheduler } = require('./features/monitoring/health-check-scheduler');
const { getNezhaConfig } = require('./config/nezha');
const { startAutoSync, stopAutoSync } = require('./services/nezha-sync');
const apiRoutes = require('./routes');
const logger = require('./lib/logger');
const { notFoundHandler, errorHandler } = require('./middleware/error-handler');

// Swagger Documentation
const swaggerUi = require('swagger-ui-express');
const swaggerSpecs = require('./config/swagger');

const app = express();
const PORT = process.env.PORT || 3000;

// 中间件配置

// Helmet - 安全响应头
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "unpkg.com", "cdn.tailwindcss.com"],
      scriptSrcAttr: ["'unsafe-inline'"], // 允许内联事件处理器（onclick等）
      styleSrc: ["'self'", "'unsafe-inline'", "cdn.tailwindcss.com", "fonts.googleapis.com"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'", "cdn.jsdelivr.net"], // 允许CDN source maps
      fontSrc: ["'self'", "data:", "fonts.googleapis.com", "fonts.gstatic.com"],
      objectSrc: ["'none'"],
      mediaSrc: ["'self'"],
      frameSrc: ["'none'"],
      // 开发环境不强制升级到 HTTPS
      // upgradeInsecureRequests: [], // 已移除，允许 HTTP 访问
    },
  },
  // 开发环境禁用 HSTS，避免强制 HTTPS
  hsts: false,
}));

// CORS配置
const corsOptions = {
  origin: function (origin, callback) {
    const allowedOrigins = process.env.ALLOWED_ORIGINS
      ? process.env.ALLOWED_ORIGINS.split(',')
      : ['http://localhost:3000', 'http://127.0.0.1:3000'];

    // 开发环境允许无origin (例如 Postman)
    if (!origin && process.env.NODE_ENV === 'development') {
      return callback(null, true);
    }

    if (allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(null, false);
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  maxAge: 86400
};

app.use(cors(corsOptions));

app.use(express.json({ limit: '1mb' })); // 限制请求体大小
app.use(express.static(path.join(__dirname)));

// API Documentation (Swagger) - Only in non-production environments
if (process.env.NODE_ENV !== 'production') {
  app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpecs));
  logger.info(`📚 Swagger UI available at http://localhost:${PORT}/api-docs`);
}

// 全局速率限制 (应用到所有API)
app.use('/api/', globalLimiter);

// 挂载所有路由
app.use('/api', apiRoutes);

// 全局错误处理（必须在所有路由之后）
app.use('/api', notFoundHandler);
app.use(errorHandler);

// ==================== 启动服务器 ====================

if (process.env.NODE_ENV !== 'test') {
  const server = app.listen(PORT, () => {
    logger.info(`🚀 VPS Manager v3.1 启动成功！`);
    logger.info(`📍 访问地址: http://localhost:${PORT}`);
    logger.info(`🔧 环境: ${process.env.NODE_ENV || 'development'}`);

    // 启动哪吒自动同步
    const nezhaConfig = getNezhaConfig();
    if (nezhaConfig.autoSync) {
      startAutoSync();
    }

    // 启动续费提醒调度器
    const renewalScheduler = getRenewalScheduler();
    renewalScheduler.start();

    // 启动健康检查调度器（如果已启用）
    const healthCheckScheduler = getHealthCheckScheduler();
    healthCheckScheduler.start();
  });

  // 优雅关闭
  process.on('SIGTERM', () => {
    logger.info('收到 SIGTERM 信号，开始优雅关闭...');
    stopAutoSync();
    server.close(() => {
      logger.info('服务器已关闭');
      process.exit(0);
    });
  });
}

module.exports = app;
