/**
 * 全局错误处理中间件
 * 统一处理所有未捕获的错误，返回一致的错误响应格式
 */

/**
 * 自定义应用错误类
 */
class AppError extends Error {
  constructor(message, statusCode = 500, code = 'INTERNAL_ERROR') {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.isOperational = true; // 标记为可预期的操作错误

    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * 常用错误工厂函数
 */
const Errors = {
  badRequest: (message = '请求参数无效') => new AppError(message, 400, 'BAD_REQUEST'),
  unauthorized: (message = '未授权访问') => new AppError(message, 401, 'UNAUTHORIZED'),
  forbidden: (message = '禁止访问') => new AppError(message, 403, 'FORBIDDEN'),
  notFound: (message = '资源不存在') => new AppError(message, 404, 'NOT_FOUND'),
  conflict: (message = '资源冲突') => new AppError(message, 409, 'CONFLICT'),
  tooManyRequests: (message = '请求过于频繁') => new AppError(message, 429, 'TOO_MANY_REQUESTS'),
  internal: (message = '服务器内部错误') => new AppError(message, 500, 'INTERNAL_ERROR'),
};

/**
 * 异步路由包装器 - 自动捕获 async 函数中的错误
 * @param {Function} fn - async 路由处理函数
 * @returns {Function} 包装后的路由处理函数
 */
function asyncHandler(fn) {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

/**
 * 404 处理中间件 - 处理未匹配的路由
 */
function notFoundHandler(req, res, next) {
  const error = Errors.notFound(`路由不存在: ${req.method} ${req.originalUrl}`);
  next(error);
}

/**
 * 全局错误处理中间件
 * 必须放在所有路由之后
 */
function errorHandler(err, req, res, next) {
  // 设置默认值
  let statusCode = err.statusCode || 500;
  let message = err.message || '服务器内部错误';
  let code = err.code || 'INTERNAL_ERROR';

  // 处理特定类型的错误
  
  // JSON 解析错误
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    statusCode = 400;
    message = 'JSON 格式无效';
    code = 'INVALID_JSON';
  }

  // JWT 错误
  if (err.name === 'JsonWebTokenError') {
    statusCode = 401;
    message = '无效的认证令牌';
    code = 'INVALID_TOKEN';
  }

  if (err.name === 'TokenExpiredError') {
    statusCode = 401;
    message = '认证令牌已过期';
    code = 'TOKEN_EXPIRED';
  }

  // SQLite 错误
  if (err.code === 'SQLITE_CONSTRAINT') {
    statusCode = 409;
    message = '数据约束冲突';
    code = 'DB_CONSTRAINT_ERROR';
  }

  // 非操作性错误（程序 bug）在生产环境隐藏详情
  const isProduction = process.env.NODE_ENV === 'production';
  const isOperational = err.isOperational === true;

  if (!isOperational && isProduction) {
    message = '服务器内部错误';
    code = 'INTERNAL_ERROR';
  }

  // 记录错误日志
  if (statusCode >= 500) {
    console.error('=== 服务器错误 ===');
    console.error(`时间: ${new Date().toISOString()}`);
    console.error(`路由: ${req.method} ${req.originalUrl}`);
    console.error(`错误: ${err.message}`);
    console.error(`堆栈: ${err.stack}`);
    console.error('==================');
  } else if (process.env.NODE_ENV === 'development') {
    console.warn(`[${statusCode}] ${req.method} ${req.originalUrl} - ${message}`);
  }

  // 构建响应
  const response = {
    success: false,
    error: message,
    code: code,
  };

  // 开发环境添加额外调试信息
  if (!isProduction) {
    response.stack = err.stack;
    response.path = req.originalUrl;
    response.method = req.method;
  }

  res.status(statusCode).json(response);
}

module.exports = {
  AppError,
  Errors,
  asyncHandler,
  notFoundHandler,
  errorHandler,
};
