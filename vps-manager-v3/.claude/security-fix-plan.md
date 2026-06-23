# VPS Manager v3 - 安全漏洞修复执行计划

**创建时间**: 2026-01-14
**预计总耗时**: 2-3小时
**修复优先级**: P0 (紧急) → P1 (高) → P2 (中)

---

## 📋 修复概览

| 阶段 | 任务数 | 预计耗时 | 状态 |
|------|--------|----------|------|
| **阶段1: 紧急修复 (P0)** | 3个 | 45分钟 | ⏳ 待开始 |
| **阶段2: 高优先级 (P1)** | 4个 | 60分钟 | ⏳ 待开始 |
| **阶段3: 中优先级 (P2)** | 3个 | 30分钟 | ⏳ 待开始 |
| **阶段4: 验证测试** | 1个 | 15分钟 | ⏳ 待开始 |

**总计**: 11个任务，约2.5小时

---

# 🚨 阶段1: �急修复 (P0) - 必须立即完成

## 第1步: 撤销泄露的哪吒Token 🔴

**风险**: 严重 - 攻击者可完全控制哪吒面板
**耗时**: 15分钟
**依赖**: 需要哪吒面板访问权限

### 操作步骤:

#### 1.1 确认泄露的Token信息
```bash
# 在项目根目录执行
cd /Users/deelii/code/vps-manager-v3

# 查看当前泄露的Token
sqlite3 data/vps-manager.db "SELECT key, value FROM config WHERE key='nezha';" | grep token

# 输出示例:
# token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### 1.2 撤销Token并生成新Token

**方式A: 哪吒面板操作 (推荐)**
```
1. 访问: https://tz.nm.sd (您的哪吒面板)
2. 登录管理员账号
3. 进入 "设置" -> "API Token"
4. 找到当前Token并点击 "撤销"
5. 点击 "生成新Token"
6. 复制新Token备用
```

**方式B: 修改哪吒用户密码 (如果无法访问面板)**
```
1. 重置哪吒管理员密码
2. 重新登录后，旧Token自动失效
3. 生成新的API Token
```

#### 1.3 配置环境变量存储新Token

```bash
# 创建 .env 文件 (如果不存在)
touch .env

# 添加环境变量 (替换为您的新Token)
cat >> .env << 'EOF'
# 哪吒探针配置
NEZHA_API_URL=https://tz.nm.sd
NEZHA_TOKEN=<您的新Token>
EOF

# 设置文件权限 (仅所有者可读写)
chmod 600 .env
```

#### 1.4 修改代码读取环境变量

创建文件: `src/config/nezha.js`
```javascript
/**
 * 哪吒配置管理 - 优先从环境变量读取
 */
function getNezhaConfig() {
  // 优先从环境变量读取
  if (process.env.NEZHA_API_URL && process.env.NEZHA_TOKEN) {
    return {
      apiUrl: process.env.NEZHA_API_URL,
      token: process.env.NEZHA_TOKEN,
      autoSync: process.env.NEZHA_AUTO_SYNC === 'true',
      syncInterval: parseInt(process.env.NEZHA_SYNC_INTERVAL || '3600')
    };
  }

  // 降级到数据库读取 (用于迁移期)
  const { ConfigDB } = require('../database');
  const dbConfig = ConfigDB.get('nezha');

  if (!dbConfig || !dbConfig.token) {
    console.warn('⚠️  哪吒配置未设置，请配置环境变量 NEZHA_API_URL 和 NEZHA_TOKEN');
    return {
      apiUrl: '',
      token: '',
      autoSync: false,
      syncInterval: 3600
    };
  }

  return dbConfig;
}

module.exports = { getNezhaConfig };
```

修改 `src/server.js` 第350行:
```javascript
// 原代码 (第350-355行):
// let nezhaConfig = ConfigDB.get('nezha') || { ... };

// 新代码:
const { getNezhaConfig } = require('./config/nezha');
let nezhaConfig = getNezhaConfig();
```

#### 1.5 从数据库中删除旧Token

```bash
# 清除数据库中的哪吒配置 (已迁移到环境变量)
sqlite3 data/vps-manager.db "DELETE FROM config WHERE key='nezha';"

# 验证删除成功
sqlite3 data/vps-manager.db "SELECT * FROM config WHERE key='nezha';"
# 应该无输出
```

#### 1.6 验证修复

```bash
# 安装 dotenv 库 (如果使用 .env 文件)
npm install dotenv

# 在 src/server.js 最顶部添加:
# require('dotenv').config();

# 启动服务器
npm start

# 验证日志中没有 Token 泄露
```

### ✅ 完成标准:
- [x] 旧Token已撤销
- [x] 新Token已配置到 .env 文件
- [x] 代码已修改为读取环境变量
- [x] 数据库中的Token已删除
- [x] 服务器可正常启动并连接哪吒

---

## 第2步: 删除公开API端点 🔴

**风险**: 严重 - 泄露所有VPS信息
**耗时**: 10分钟
**依赖**: 无

### 操作步骤:

#### 2.1 备份当前代码

```bash
# 创建备份分支
git checkout -b backup-before-remove-public-api
git add .
git commit -m "备份：删除公开API前的代码"
git checkout main
```

#### 2.2 删除公开API端点

编辑 `src/server.js`，删除以下代码段:

**删除位置1**: 第147-193行 - `/api/public/servers`
```javascript
// ❌ 删除这整个端点
app.get('/api/public/servers', (req, res) => {
  // ... 147-193行全部删除
});
```

**删除位置2**: 第195-220行 - `/api/public/stats`
```javascript
// ❌ 删除这整个端点
app.get('/api/public/stats', (req, res) => {
  // ... 195-220行全部删除
});
```

**删除位置3**: 第222-247行 - `/api/public/rankings`
```javascript
// ❌ 删除这整个端点
app.get('/api/public/rankings', (req, res) => {
  // ... 222-247行全部删除
});
```

#### 2.3 (可选) 为已登录用户保留统计API

如果需要保留这些API供前端使用，添加认证:

```javascript
// ✅ 修改后的安全版本 (添加 authMiddleware)
app.get('/api/servers', authMiddleware, (req, res) => {
  const vpsList = VpsDB.getAll();
  res.json({ success: true, data: vpsList });
});

app.get('/api/stats', authMiddleware, (req, res) => {
  const vpsList = VpsDB.getAll();

  const stats = {
    totalServers: vpsList.length,
    onlineServers: vpsList.filter(v => v.nezha?.online).length,
    expiringServers: vpsList.filter(v => {
      if (!v.cycle) return false;
      try {
        const totalDays = getDaysByCycle(v.cycle);
        const usedDays = calculateUsedDays(v.purchaseDate);
        return (totalDays - usedDays) <= 30;
      } catch (e) {
        return false;
      }
    }).length
  };

  res.json({ success: true, data: stats });
});
```

#### 2.4 修改前端调用 (如果存在)

检查 `src/index.html` 中是否有调用公开API:

```bash
# 搜索公开API调用
grep -n "api/public" src/index.html

# 如果有结果，修改为:
# /api/public/servers  → /api/servers
# /api/public/stats    → /api/stats
# 并确保前端在调用前已登录并携带 Authorization 头
```

#### 2.5 验证修复

```bash
# 启动服务器
npm start

# 在另一个终端测试
curl http://localhost:3000/api/public/servers
# 期望结果: 404 Not Found 或 Cannot GET /api/public/servers

curl http://localhost:3000/api/public/stats
# 期望结果: 404 Not Found

# 测试需要认证的API (应该返回401)
curl http://localhost:3000/api/servers
# 期望结果: {"success":false,"error":"未登录"}
```

### ✅ 完成标准:
- [x] 公开API端点已删除
- [x] 测试确认无法访问 `/api/public/*`
- [x] 前端调用已修改为认证API
- [x] 服务器正常运行

---

## 第3步: 强制JWT密钥环境变量 🔴

**风险**: 严重 - 任何人可伪造管理员Token
**耗时**: 20分钟
**依赖**: 无

### 操作步骤:

#### 3.1 生成强随机JWT密钥

```bash
# 方式1: 使用 OpenSSL (推荐)
openssl rand -hex 64

# 方式2: 使用 Node.js
node -e "console.log(require('crypto').randomBytes(64).toString('hex'))"

# 输出示例:
# a1b2c3d4e5f6....(128个十六进制字符)

# 复制生成的密钥备用
```

#### 3.2 配置环境变量

```bash
# 添加到 .env 文件
cat >> .env << 'EOF'

# JWT 配置
JWT_SECRET=<粘贴刚才生成的64字节密钥>
JWT_EXPIRY=1h
EOF

# 验证 .env 文件内容
cat .env
```

#### 3.3 修改认证代码

编辑 `src/auth.js`:

**修改位置1**: 第5-6行
```javascript
// ❌ 原代码:
// const JWT_SECRET = process.env.JWT_SECRET || 'vps-manager-secret-key-change-in-production';
// const TOKEN_EXPIRY = '3d';

// ✅ 新代码:
const JWT_SECRET = process.env.JWT_SECRET;
const TOKEN_EXPIRY = process.env.JWT_EXPIRY || '1h';

// 严格验证 JWT_SECRET
if (!JWT_SECRET) {
  console.error('🔴 致命错误: 未设置 JWT_SECRET 环境变量');
  console.error('📝 请执行: openssl rand -hex 64 > .env');
  console.error('   然后在 .env 文件中添加: JWT_SECRET=<生成的密钥>');
  process.exit(1); // 强制退出，拒绝启动
}

if (JWT_SECRET.length < 32) {
  console.error('🔴 致命错误: JWT_SECRET 长度不足32字符');
  console.error('   当前长度:', JWT_SECRET.length);
  console.error('   推荐长度: 64字节 (128个十六进制字符)');
  process.exit(1);
}

console.log('✅ JWT配置已验证 (密钥长度:', JWT_SECRET.length, '字符)');
```

#### 3.4 撤销所有现有Token

```bash
# 现有用户需要重新登录

# 可选: 在数据库中记录Token撤销时间
sqlite3 data/vps-manager.db "UPDATE users SET updated_at = CURRENT_TIMESTAMP;"
```

#### 3.5 配置 dotenv 加载

编辑 `src/server.js`，在**最顶部**添加:

```javascript
// 必须在所有 require 之前加载环境变量
require('dotenv').config();

// 然后才是其他导入
const express = require('express');
// ...
```

安装依赖:
```bash
npm install dotenv --save
```

#### 3.6 验证修复

```bash
# 测试1: 不设置环境变量，应该拒绝启动
unset JWT_SECRET
npm start
# 期望输出: 🔴 致命错误: 未设置 JWT_SECRET 环境变量

# 测试2: 使用正确的环境变量
source .env  # 或使用 dotenv
npm start
# 期望输出: ✅ JWT配置已验证

# 测试3: 验证旧Token失效
# 使用旧密钥生成的Token应该无法访问API
curl -H "Authorization: Bearer <旧Token>" http://localhost:3000/api/vps
# 期望结果: {"success":false,"error":"登录已过期"}
```

### ✅ 完成标准:
- [x] 生成并配置了64字节随机JWT密钥
- [x] 代码已修改为强制要求环境变量
- [x] 密钥长度不足时拒绝启动
- [x] 所有旧Token已失效
- [x] 新登录可正常生成Token

---

# 🟠 阶段2: 高优先级修复 (P1) - 7天内完成

## 第4步: 添加速率限制 🟠

**风险**: 高 - 可被自动化扫描工具滥用
**耗时**: 20分钟
**依赖**: 无

### 操作步骤:

#### 4.1 安装依赖

```bash
npm install express-rate-limit --save
```

#### 4.2 创建速率限制配置文件

创建 `src/middleware/rate-limit.js`:

```javascript
const rateLimit = require('express-rate-limit');

// 全局API限制 (适用于所有API)
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

// 认证端点严格限制 (防止暴力破解)
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,                    // 15分钟内最多5次尝试
  skipSuccessfulRequests: true, // 成功的请求不计数
  message: {
    success: false,
    error: '登录尝试次数过多，请15分钟后再试'
  }
});

// VPS操作限制 (防止批量操作滥用)
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
```

#### 4.3 应用速率限制

编辑 `src/server.js`，在中间件配置部分添加:

```javascript
const express = require('express');
const path = require('path');
const { globalLimiter, authLimiter, vpsOperationLimiter } = require('./middleware/rate-limit');

const app = express();

// 中间件配置
app.use(express.json({ limit: '1mb' })); // 限制请求体大小

// 全局速率限制 (应用到所有API)
app.use('/api/', globalLimiter);

// ... 其他中间件

// 认证端点使用严格限制
app.get('/api/auth/status', (req, res) => { /* ... */ });
app.post('/api/auth/init', authLimiter, async (req, res) => { /* ... */ });
app.post('/api/auth/login', authLimiter, async (req, res) => { /* ... */ });

// VPS操作端点
app.post('/api/vps', authMiddleware, vpsOperationLimiter, (req, res) => { /* ... */ });
app.put('/api/vps/:id', authMiddleware, vpsOperationLimiter, (req, res) => { /* ... */ });
app.delete('/api/vps/:id', authMiddleware, vpsOperationLimiter, (req, res) => { /* ... */ });
```

#### 4.4 验证速率限制

```bash
# 启动服务器
npm start

# 测试全局限制 (快速发送请求)
for i in {1..10}; do curl http://localhost:3000/api/health; done

# 测试认证限制 (模拟暴力破解)
for i in {1..10}; do
  curl -X POST http://localhost:3000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"fake","password":"fake"}'
done
# 第6次应该返回: "登录尝试次数过多"

# 检查响应头
curl -I http://localhost:3000/api/health
# 应该包含: RateLimit-Limit, RateLimit-Remaining
```

### ✅ 完成标准:
- [x] 已安装 express-rate-limit
- [x] 全局API限制已应用
- [x] 认证端点有严格限制
- [x] 响应头包含速率限制信息
- [x] 超限时正确返回错误

---

## 第5步: 实现登录失败限制 🟠

**风险**: 高 - 可被暴力破解
**耗时**: 15分钟
**依赖**: 第4步(速率限制)

### 操作步骤:

#### 5.1 创建登录尝试跟踪

编辑 `src/auth.js`，添加失败追踪:

```javascript
// 在文件顶部添加
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
    console.warn(`⚠️  IP ${ip} 登录失败${record.count}次，已锁定30分钟`);
  }

  loginAttempts.set(ip, record);

  // 自动清理：30分钟后删除记录
  setTimeout(() => {
    loginAttempts.delete(ip);
  }, 30 * 60 * 1000);
}

/**
 * 清除登录失败记录 (登录成功时调用)
 */
function clearLoginFailures(ip) {
  loginAttempts.delete(ip);
}

// 导出新函数
module.exports = {
  // ... 原有导出
  isIPLocked,
  recordLoginFailure,
  clearLoginFailures
};
```

#### 5.2 修改登录端点

编辑 `src/server.js`，修改登录端点:

```javascript
const {
  isInitialized,
  initialize,
  login,
  isIPLocked,           // 新增
  recordLoginFailure,   // 新增
  clearLoginFailures,   // 新增
  // ...
} = require('./auth');

app.post('/api/auth/login', authLimiter, async (req, res) => {
  const clientIP = req.ip || req.connection.remoteAddress;

  // 检查IP是否被锁定
  if (isIPLocked(clientIP)) {
    return res.status(429).json({
      success: false,
      error: '登录失败次数过多，账号已锁定30分钟'
    });
  }

  try {
    const { username, password } = req.body;
    const result = await login(username, password);

    // 登录成功，清除失败记录
    clearLoginFailures(clientIP);

    res.json({ success: true, data: result });
  } catch (error) {
    // 记录失败尝试
    recordLoginFailure(clientIP);

    const record = loginAttempts.get(clientIP);
    const remainingAttempts = 5 - (record?.count || 0);

    res.status(401).json({
      success: false,
      error: error.message,
      remainingAttempts: Math.max(0, remainingAttempts)
    });
  }
});
```

#### 5.3 添加解锁管理API (可选)

```javascript
// 管理员可手动解锁IP
app.post('/api/admin/unlock-ip', authMiddleware, (req, res) => {
  const { ip } = req.body;

  if (loginAttempts.has(ip)) {
    loginAttempts.delete(ip);
    res.json({ success: true, message: `IP ${ip} 已解锁` });
  } else {
    res.status(404).json({ success: false, error: 'IP 不存在锁定记录' });
  }
});
```

#### 5.4 验证登录限制

```bash
# 测试: 快速尝试5次错误登录
for i in {1..6}; do
  echo "尝试 $i:"
  curl -X POST http://localhost:3000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"wrong"}' \
    | jq .
  sleep 1
done

# 第5次后应该返回:
# {"success":false,"error":"登录失败次数过多，账号已锁定30分钟"}

# 测试成功登录会清除记录
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<正确密码>"}'
```

### ✅ 完成标准:
- [x] 登录失败5次后锁定30分钟
- [x] 锁定期内拒绝登录尝试
- [x] 成功登录清除失败记录
- [x] 返回剩余尝试次数提示
- [x] 控制台记录异常登录行为

---

## 第6步: 修复数据库文件权限 🟠

**风险**: 中-高 - 同组用户可读取数据库
**耗时**: 5分钟
**依赖**: 无

### 操作步骤:

#### 6.1 修改数据库初始化代码

编辑 `src/database.js`，在数据库创建后添加权限设置:

```javascript
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = path.join(__dirname, '..', 'data', 'vps-manager.db');

// 确保 data 目录存在
const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

// 创建数据库
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// ✅ 新增: 设置数据库文件权限为 600 (仅所有者可读写)
try {
  fs.chmodSync(DB_PATH, 0o600);

  // 同时设置 WAL 和 SHM 文件的权限
  const walPath = DB_PATH + '-wal';
  const shmPath = DB_PATH + '-shm';

  if (fs.existsSync(walPath)) {
    fs.chmodSync(walPath, 0o600);
  }
  if (fs.existsSync(shmPath)) {
    fs.chmodSync(shmPath, 0o600);
  }

  console.log('✅ 数据库文件权限已设置为 600');
} catch (error) {
  console.warn('⚠️  无法设置数据库文件权限:', error.message);
}

// ... 其余代码不变
```

#### 6.2 手动修复现有文件权限

```bash
# 修改数据库文件权限
chmod 600 data/vps-manager.db
chmod 600 data/vps-manager.db-wal
chmod 600 data/vps-manager.db-shm

# 修改 .env 文件权限
chmod 600 .env

# 修改整个 data 目录权限
chmod 700 data/

# 验证权限
ls -la data/
# 应该显示:
# -rw------- vps-manager.db
# -rw------- vps-manager.db-wal
# -rw------- vps-manager.db-shm
```

#### 6.3 添加权限检查脚本

创建 `scripts/check-permissions.sh`:

```bash
#!/bin/bash

echo "🔍 检查文件权限..."

# 检查数据库文件
for file in data/vps-manager.db data/vps-manager.db-wal data/vps-manager.db-shm data/.env; do
  if [ -f "$file" ]; then
    perm=$(stat -f "%Sp" "$file" 2>/dev/null || stat -c "%A" "$file" 2>/dev/null)
    if [[ "$perm" == "-rw-------" ]]; then
      echo "✅ $file: $perm (安全)"
    else
      echo "❌ $file: $perm (不安全，应为 -rw-------)"
    fi
  fi
done

# 检查 .env 文件
if [ -f ".env" ]; then
  perm=$(stat -f "%Sp" ".env" 2>/dev/null || stat -c "%A" ".env" 2>/dev/null)
  if [[ "$perm" == "-rw-------" ]]; then
    echo "✅ .env: $perm (安全)"
  else
    echo "❌ .env: $perm (不安全，应为 -rw-------)"
  fi
fi
```

```bash
# 设置脚本为可执行
chmod +x scripts/check-permissions.sh

# 运行检查
./scripts/check-permissions.sh
```

### ✅ 完成标准:
- [x] 数据库文件权限为 600
- [x] .env 文件权限为 600
- [x] data 目录权限为 700
- [x] 代码自动设置新文件权限
- [x] 权限检查脚本可正常运行

---

## 第7步: 配置CORS和安全响应头 🟠

**风险**: 中 - 跨域攻击和信息泄露
**耗时**: 20分钟
**依赖**: 无

### 操作步骤:

#### 7.1 安装依赖

```bash
npm install helmet cors --save
```

#### 7.2 配置 helmet (安全响应头)

编辑 `src/server.js`:

```javascript
const helmet = require('helmet');
const cors = require('cors');

// 在中间件配置部分添加 (express.json() 之前)
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "unpkg.com"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'"],
      fontSrc: ["'self'", "data:"],
      objectSrc: ["'none'"],
      mediaSrc: ["'self'"],
      frameSrc: ["'none'"],
    },
  },
  hsts: {
    maxAge: 31536000,        // 1年
    includeSubDomains: true,
    preload: true
  },
  noSniff: true,             // X-Content-Type-Options: nosniff
  xssFilter: true,           // X-XSS-Protection
  hidePoweredBy: true,       // 隐藏 X-Powered-By: Express
}));
```

#### 7.3 配置 CORS

```javascript
// CORS 配置
const corsOptions = {
  origin: function (origin, callback) {
    // 允许的来源列表 (从环境变量读取)
    const allowedOrigins = process.env.ALLOWED_ORIGINS
      ? process.env.ALLOWED_ORIGINS.split(',')
      : ['http://localhost:3000', 'http://127.0.0.1:3000'];

    // 开发环境允许无 origin (例如 Postman)
    if (!origin && process.env.NODE_ENV === 'development') {
      return callback(null, true);
    }

    if (allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(new Error('不允许的跨域来源'));
    }
  },
  credentials: true,           // 允许发送 Cookie
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  maxAge: 86400               // 预检请求缓存 24小时
};

app.use(cors(corsOptions));
```

#### 7.4 添加到 .env 文件

```bash
cat >> .env << 'EOF'

# CORS 配置
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
NODE_ENV=development
EOF
```

#### 7.5 验证安全响应头

```bash
# 启动服务器
npm start

# 检查响应头
curl -I http://localhost:3000/api/health

# 应该包含:
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# X-XSS-Protection: 1; mode=block
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# Content-Security-Policy: ...

# 测试 CORS
curl -H "Origin: http://evil.com" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     http://localhost:3000/api/health
# 应该被拒绝
```

### ✅ 完成标准:
- [x] helmet 已配置并应用
- [x] 响应包含安全相关头
- [x] CORS 已配置白名单
- [x] 未授权来源被拒绝
- [x] 开发环境可正常访问

---

# 🟡 阶段3: 中优先级修复 (P2) - 30天内完成

## 第8步: 统一错误处理 🟡

**风险**: 中 - 可能泄露内部信息
**耗时**: 15分钟

### 操作步骤:

创建 `src/middleware/error-handler.js`:

```javascript
/**
 * 统一错误处理中间件
 */
function errorHandler(err, req, res, next) {
  // 记录详细错误到日志
  console.error('[Error]', {
    timestamp: new Date().toISOString(),
    method: req.method,
    path: req.path,
    ip: req.ip,
    error: err.message,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
  });

  // 根据环境返回不同级别的错误信息
  if (process.env.NODE_ENV === 'development') {
    return res.status(err.status || 500).json({
      success: false,
      error: err.message,
      stack: err.stack // 仅开发环境返回堆栈
    });
  }

  // 生产环境返回通用错误消息
  res.status(err.status || 500).json({
    success: false,
    error: '服务器内部错误，请稍后重试'
  });
}

module.exports = { errorHandler };
```

在 `src/server.js` 末尾添加:

```javascript
const { errorHandler } = require('./middleware/error-handler');

// ... 所有路由定义

// 404 处理
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: '请求的资源不存在'
  });
});

// 错误处理中间件 (必须放在最后)
app.use(errorHandler);
```

---

## 第9步: 添加操作审计日志 🟡

**风险**: 低 - 缺少安全审计能力
**耗时**: 10分钟

创建 `src/utils/audit-log.js`:

```javascript
const fs = require('fs');
const path = require('path');

const AUDIT_LOG_PATH = path.join(__dirname, '..', '..', 'logs', 'audit.log');

// 确保日志目录存在
const logDir = path.dirname(AUDIT_LOG_PATH);
if (!fs.existsSync(logDir)) {
  fs.mkdirSync(logDir, { recursive: true });
}

/**
 * 记录审计日志
 */
function auditLog(action, user, details, req) {
  const log = {
    timestamp: new Date().toISOString(),
    action,
    user,
    ip: req?.ip || 'unknown',
    userAgent: req?.headers['user-agent'] || 'unknown',
    details
  };

  fs.appendFileSync(AUDIT_LOG_PATH, JSON.stringify(log) + '\n');

  // 同时输出到控制台
  console.log('[Audit]', action, 'by', user, 'from', log.ip);
}

module.exports = { auditLog };
```

在关键操作处添加审计:

```javascript
const { auditLog } = require('./utils/audit-log');

// 登录审计
app.post('/api/auth/login', authLimiter, async (req, res) => {
  // ...
  const result = await login(username, password);
  auditLog('LOGIN_SUCCESS', username, {}, req);
  // ...
});

// VPS操作审计
app.delete('/api/vps/:id', authMiddleware, (req, res) => {
  // ...
  VpsDB.delete(id);
  auditLog('DELETE_VPS', req.user.username, { vpsId: id, vpsName: existing.name }, req);
  // ...
});
```

---

## 第10步: 实现数据库备份 🟡

**风险**: 低 - 数据丢失风险
**耗时**: 5分钟

创建 `scripts/backup-database.sh`:

```bash
#!/bin/bash

BACKUP_DIR="./backups"
DB_PATH="./data/vps-manager.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP.db"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份数据库
echo "📦 开始备份数据库..."
cp "$DB_PATH" "$BACKUP_PATH"

# 压缩备份
gzip "$BACKUP_PATH"

echo "✅ 备份完成: ${BACKUP_PATH}.gz"

# 清理 7 天前的备份
find "$BACKUP_DIR" -name "backup_*.db.gz" -mtime +7 -delete
echo "🧹 已清理7天前的旧备份"
```

```bash
chmod +x scripts/backup-database.sh

# 添加到 crontab (每天凌晨2点备份)
crontab -e
# 添加: 0 2 * * * cd /path/to/vps-manager-v3 && ./scripts/backup-database.sh
```

---

# ✅ 阶段4: 验证测试

## 第11步: 综合安全验证 🔍

**耗时**: 15分钟

### 验证清单:

创建 `scripts/security-test.sh`:

```bash
#!/bin/bash

echo "🔐 开始安全验证测试..."
echo "================================"

# 测试1: 公开API应该不存在
echo "📝 测试1: 公开API已删除"
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/public/servers)
if [ "$response" == "404" ]; then
  echo "✅ 通过: 公开API已删除"
else
  echo "❌ 失败: 公开API仍可访问 (HTTP $response)"
fi

# 测试2: 未认证访问应该被拒绝
echo -e "\n📝 测试2: 认证保护"
response=$(curl -s http://localhost:3000/api/vps | jq -r '.error')
if [[ "$response" == "未登录" ]]; then
  echo "✅ 通过: 需要认证的API正确拒绝未登录请求"
else
  echo "❌ 失败: 认证保护无效"
fi

# 测试3: 速率限制
echo -e "\n📝 测试3: 速率限制"
for i in {1..8}; do
  curl -s http://localhost:3000/api/health > /dev/null
done
response=$(curl -s http://localhost:3000/api/health | jq -r '.error // empty')
if [[ "$response" == *"过于频繁"* ]]; then
  echo "✅ 通过: 速率限制正常工作"
else
  echo "⚠️  警告: 速率限制可能未生效"
fi

# 测试4: 环境变量检查
echo -e "\n📝 测试4: 环境变量配置"
if [ -z "$JWT_SECRET" ]; then
  echo "❌ 失败: JWT_SECRET 未设置"
else
  echo "✅ 通过: JWT_SECRET 已设置 (长度: ${#JWT_SECRET})"
fi

if [ -z "$NEZHA_TOKEN" ]; then
  echo "⚠️  警告: NEZHA_TOKEN 未设置"
else
  echo "✅ 通过: NEZHA_TOKEN 已设置"
fi

# 测试5: 文件权限检查
echo -e "\n📝 测试5: 文件权限"
db_perm=$(stat -f "%Sp" data/vps-manager.db 2>/dev/null || stat -c "%A" data/vps-manager.db 2>/dev/null)
if [[ "$db_perm" == "-rw-------" ]]; then
  echo "✅ 通过: 数据库文件权限正确 (600)"
else
  echo "❌ 失败: 数据库文件权限不正确 ($db_perm)"
fi

# 测试6: 数据库中不应包含哪吒Token
echo -e "\n📝 测试6: 敏感数据检查"
nezha_in_db=$(sqlite3 data/vps-manager.db "SELECT COUNT(*) FROM config WHERE key='nezha';")
if [ "$nezha_in_db" == "0" ]; then
  echo "✅ 通过: 数据库中无哪吒凭据"
else
  echo "❌ 失败: 数据库中仍存在哪吒凭据"
fi

echo -e "\n================================"
echo "🎯 安全验证完成"
```

```bash
chmod +x scripts/security-test.sh

# 运行测试
source .env  # 加载环境变量
npm start &  # 后台启动服务器
sleep 3      # 等待启动
./scripts/security-test.sh
pkill -f "node src/server.js"  # 停止服务器
```

### 最终检查清单:

```markdown
## 🎯 修复完成检查清单

### P0 - 紧急修复
- [ ] 哪吒Token已撤销并重新生成
- [ ] 新Token存储在环境变量中
- [ ] 数据库中的Token已删除
- [ ] 公开API端点已删除 (或添加认证)
- [ ] JWT密钥已更换为64字节随机密钥
- [ ] 代码强制要求JWT_SECRET环境变量
- [ ] 所有旧Token已失效

### P1 - 高优先级
- [ ] 全局速率限制已应用
- [ ] 认证端点有严格限制
- [ ] 登录失败5次锁定30分钟
- [ ] 数据库文件权限为600
- [ ] .env文件权限为600
- [ ] CORS已配置白名单
- [ ] Helmet安全响应头已启用

### P2 - 中优先级
- [ ] 统一错误处理已实现
- [ ] 操作审计日志已添加
- [ ] 数据库备份脚本已创建

### 验证测试
- [ ] 公开API测试失败 (404)
- [ ] 未认证请求被拒绝
- [ ] 速率限制正常工作
- [ ] 环境变量正确配置
- [ ] 文件权限正确
- [ ] 数据库无敏感信息

### 文档和工具
- [ ] .env.example 已创建
- [ ] 安全检查脚本可运行
- [ ] README 已更新安全配置说明
```

---

## 📚 附录

### A. .env.example 模板

创建 `.env.example`:

```bash
# VPS Manager v3 - 环境变量配置模板
# 复制此文件为 .env 并填入实际值

# 服务器配置
PORT=3000
NODE_ENV=production

# JWT 配置 (必须)
# 生成方法: openssl rand -hex 64
JWT_SECRET=<请生成64字节随机密钥>
JWT_EXPIRY=1h

# 哪吒探针配置 (可选)
NEZHA_API_URL=https://your-nezha-domain.com
NEZHA_TOKEN=<您的哪吒Bearer Token>
NEZHA_AUTO_SYNC=true
NEZHA_SYNC_INTERVAL=3600

# CORS 配置
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# 数据库加密密钥 (可选，未来使用)
# DB_ENCRYPTION_KEY=<32字节密钥>
```

### B. 快速修复脚本

创建 `scripts/quick-fix.sh`:

```bash
#!/bin/bash

echo "🚀 开始快速修复..."

# 1. 生成 JWT 密钥
echo "📝 生成 JWT 密钥..."
JWT_SECRET=$(openssl rand -hex 64)
echo "JWT_SECRET=$JWT_SECRET" >> .env

# 2. 修复文件权限
echo "🔒 修复文件权限..."
chmod 600 data/*.db* 2>/dev/null
chmod 600 .env
chmod 700 data/

# 3. 清除数据库中的哪吒配置
echo "🗑️  清除数据库中的敏感配置..."
sqlite3 data/vps-manager.db "DELETE FROM config WHERE key='nezha';"

# 4. 安装必要依赖
echo "📦 安装安全依赖..."
npm install dotenv express-rate-limit helmet cors

echo "✅ 快速修复完成！"
echo "⚠️  请手动完成以下步骤:"
echo "1. 撤销哪吒面板中的旧Token"
echo "2. 在 .env 中添加 NEZHA_API_URL 和 NEZHA_TOKEN"
echo "3. 删除 src/server.js 中的公开API端点"
```

---

## 🎓 修复后的使用指南

### 首次部署:

```bash
# 1. 克隆代码
git clone <repo>
cd vps-manager-v3

# 2. 安装依赖
npm install

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值

# 4. 初始化数据库
npm start  # 首次启动会自动创建数据库

# 5. 运行安全检查
./scripts/security-test.sh
```

### 生产环境部署:

```bash
# 使用 PM2 管理进程
npm install -g pm2

# 启动服务
pm2 start src/server.js --name vps-manager

# 设置开机自启
pm2 startup
pm2 save

# 查看日志
pm2 logs vps-manager
```

---

**修复计划创建完毕！**
**建议执行顺序**: 阶段1 → 阶段2 → 阶段3 → 验证测试

需要我帮您开始执行某个具体步骤吗？
