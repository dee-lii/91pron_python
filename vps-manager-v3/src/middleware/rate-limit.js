const rateLimit = require('express-rate-limit');

/**
 * 全局API限制 (适用于所有API)
 */
const globalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15分钟窗口
  max: 100,                  // 最多100次请求
  message: {
    success: false,
    error: '请求过于频繁，请15分钟后再试'
  },
  standardHeaders: true,     // 返回 RateLimit-* 头
  legacyHeaders: false,      // 禁用 X-RateLimit-* 头
});

/**
 * 认证端点严格限制 (防止暴力破解)
 */
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,                    // 15分钟内最多5次尝试
  skipSuccessfulRequests: true, // 成功的请求不计数
  message: {
    success: false,
    error: '登录尝试次数过多，请15分钟后再试'
  }
});

/**
 * VPS操作限制 (防止批量操作滥用)
 */
const vpsOperationLimiter = rateLimit({
  windowMs: 60 * 1000,      // 1分钟窗口
  max: 30,                   // 最多30次操作
  message: {
    success: false,
    error: '操作过于频繁，请稍后再试'
  }
});

module.exports = {
  globalLimiter,
  authLimiter,
  vpsOperationLimiter
};
