const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { UserDB } = require('./database');
const logger = require('./lib/logger');

// JWT 配置 - 强制要求从环境变量读取
const JWT_SECRET = process.env.JWT_SECRET;
const TOKEN_EXPIRY = process.env.JWT_EXPIRY || '1h';

// 严格验证 JWT_SECRET
if (!JWT_SECRET) {
  logger.error('🔴 致命错误: 未设置 JWT_SECRET 环境变量');
  logger.error('📝 请执行以下步骤:');
  logger.error('   1. 生成密钥: openssl rand -hex 64');
  logger.error('   2. 创建 .env 文件并添加: JWT_SECRET=<生成的密钥>');
  logger.error('   3. 或设置环境变量: export JWT_SECRET=<生成的密钥>');
  process.exit(1); // 强制退出，拒绝启动
}

if (JWT_SECRET.length < 32) {
  logger.error('🔴 致命错误: JWT_SECRET 长度不足32字符');
  logger.error('   当前长度:', JWT_SECRET.length, '字符');
  logger.error('   推荐长度: 128字符 (64字节十六进制)');
  logger.error('   生成方法: openssl rand -hex 64');
  process.exit(1);
}

logger.info(`✅ JWT配置已验证 (密钥长度: ${JWT_SECRET.length} 字符, 有效期: ${TOKEN_EXPIRY} )`);

// 登录失败追踪
const loginAttempts = new Map(); // IP -> { count, lockedUntil }

/**
 * 检查IP是否被锁定
 */
function isIPLocked(ip) {
  const record = loginAttempts.get(ip);
  if (!record) return false;

  if (record.lockedUntil && Date.now() < record.lockedUntil) {
    return true; // 仍在锁定期
  }

  // 锁定期已过，清除记录
  if (record.lockedUntil && Date.now() >= record.lockedUntil) {
    loginAttempts.delete(ip);
    return false;
  }

  return false;
}

/**
 * 记录登录失败
 */
function recordLoginFailure(ip) {
  const record = loginAttempts.get(ip) || { count: 0, lockedUntil: null };
  record.count += 1;

  // 5次失败后锁定30分钟
  if (record.count >= 5) {
    record.lockedUntil = Date.now() + 30 * 60 * 1000; // 30分钟
    logger.warn(`⚠️  IP ${ip} 登录失败${record.count}次，已锁定30分钟`);
  }

  loginAttempts.set(ip, record);

  // 自动清理：30分钟后删除记录
  setTimeout(() => {
    loginAttempts.delete(ip);
  }, 30 * 60 * 1000);

  return record.count;
}

/**
 * 清除登录失败记录 (登录成功时调用)
 */
function clearLoginFailures(ip) {
  loginAttempts.delete(ip);
}


function isInitialized() {
  return UserDB.isInitialized();
}

async function initialize(username, password) {
  if (isInitialized()) {
    throw new Error('管理员已初始化');
  }
  
  if (!username || username.length < 3) {
    throw new Error('用户名至少3个字符');
  }
  
  if (!password || password.length < 6) {
    throw new Error('密码至少6个字符');
  }
  
  const passwordHash = await bcrypt.hash(password, 10);
  UserDB.create(username, passwordHash);
  return { username };
}

async function login(username, password) {
  const admin = UserDB.getByUsername(username);
  
  if (!admin) {
    throw new Error('用户名或密码错误');
  }
  
  const valid = await bcrypt.compare(password, admin.passwordHash);
  if (!valid) {
    throw new Error('用户名或密码错误');
  }
  
  const token = jwt.sign(
    { username: admin.username },
    JWT_SECRET,
    { expiresIn: TOKEN_EXPIRY }
  );
  
  return { token, username: admin.username };
}

function verifyToken(token) {
  try {
    return jwt.verify(token, JWT_SECRET);
  } catch (e) {
    return null;
  }
}

function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ success: false, error: '未登录' });
  }
  
  const token = authHeader.slice(7);
  const decoded = verifyToken(token);
  
  if (!decoded) {
    return res.status(401).json({ success: false, error: '登录已过期' });
  }
  
  req.user = decoded;
  next();
}

async function changePassword(username, oldPassword, newPassword) {
  if (!UserDB.isInitialized()) {
    throw new Error('管理员未初始化');
  }

  const user = UserDB.getByUsername(username);
  if (!user) {
    throw new Error('管理员不存在');
  }

  const valid = await bcrypt.compare(oldPassword, user.passwordHash);
  if (!valid) {
    throw new Error('原密码错误');
  }

  if (!newPassword || newPassword.length < 6) {
    throw new Error('新密码至少6个字符');
  }

  const newHash = await bcrypt.hash(newPassword, 10);
  UserDB.updatePassword(user.username, newHash);

  return { success: true };
}

module.exports = {
  isInitialized,
  initialize,
  login,
  verifyToken,
  authMiddleware,
  changePassword,
  isIPLocked,
  recordLoginFailure,
  clearLoginFailures
};
