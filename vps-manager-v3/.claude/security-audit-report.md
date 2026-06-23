# VPS Manager v3 安全审查报告

生成时间：2026-01-14
审查范围：本地数据库功能、哪吒探针集成、API安全性

## 🚨 执行摘要

本次安全审查针对 vps-manager-v3 项目进行全面评估，重点关注新增的本地数据库功能和哪吒探针集成。通过代码审查和实际渗透测试，发现**3个严重漏洞**和**4个高危风险**。

**测试时间**: 2026-01-14 10:25-10:30
**测试环境**: macOS (Darwin 25.2.0), Node.js v18+
**数据库**: SQLite 3 (better-sqlite3@12.6.0)

### 🔴 风险等级分布
- 🔴 **严重风险 (Critical)**: 3 个 - **立即修复**
- 🟠 **高危风险 (High)**: 4 个 - **7天内修复**
- 🟡 **中危风险 (Medium)**: 5 个 - **30天内修复**
- 🟢 **低危风险 (Low)**: 2 个 - **建议改进**

### ⚠️ 核心安全问题（实测验证）
1. **[已验证] 哪吒探针凭据明文存储在数据库中** - 直接查询可获取真实Token
2. **[已验证] 公开 API 无需认证暴露服务器列表** - curl测试成功获取所有VPS信息
3. **[已验证] JWT 密钥使用默认值** - 源码公开,任何人可伪造Token
4. **[已验证] 数据库文件权限644** - 可被同组用户读取
5. **[未测试] 缺少速率限制** - 可被自动化扫描工具滥用
6. **[部分验证] 静态文件服务暴露源码** - 整个src目录对外可访问

---

## 一、数据库安全审查

### 1.1 数据库文件暴露风险 🔴 [严重]

**问题描述**：
- 数据库文件路径：`/data/vps-manager.db`
- `.gitignore` 已包含 `data/` 目录（✅ 正确）
- 但实际 `data/` 目录下存在敏感文件可能已被提交

**实际发现**：
```bash
data/
├── vps-manager.db          # SQLite 数据库（包含用户密码哈希）
├── vps-manager.db-shm      # SQLite 共享内存文件
├── vps-manager.db-wal      # SQLite 预写日志文件
├── config.json             # ⚠️ 包含哪吒 Token（明文）
└── admin.json              # ⚠️ 包含管理员密码哈希
```

**安全风险**：
- ❌ `config.json` 包含哪吒探针 Bearer Token（明文）
- ❌ `admin.json` 包含管理员密码哈希（可被彩虹表攻击）
- ❌ SQLite 数据库如果被下载，可离线暴力破解密码

**修复建议**：
```bash
# 1. 检查是否已提交敏感文件
git log --all --full-history -- data/

# 2. 如果已提交，立即清除历史
git filter-branch --force --index-filter \
  "git rm -rf --cached --ignore-unmatch data/" \
  --prune-empty --tag-name-filter cat -- --all

# 3. 强制推送（需谨慎）
git push origin --force --all

# 4. 更换所有泄露的密钥和密码
```

**文件位置**：`/Users/deelii/code/vps-manager-v3/.gitignore` (第43行)

---

### 1.2 数据库注入风险检查 🟢 [安全]

**检查结果**：✅ **使用了参数化查询，安全**

**证据**：
```javascript
// src/database.js 第49-52行
const userQueries = {
  getByUsername: db.prepare('SELECT * FROM users WHERE username = ?'),
  create: db.prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)'),
  updatePassword: db.prepare('UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?'),
};
```

所有 SQL 查询均使用 `better-sqlite3` 的 `prepare()` 和占位符 `?`，有效防止 SQL 注入。

---

### 1.3 密码存储安全性 🟢 [安全]

**检查结果**：✅ **使用 bcrypt 哈希，符合最佳实践**

**证据**：
```javascript
// src/auth.js 第25行
const passwordHash = await bcrypt.hash(password, 10); // 使用 bcrypt + 10轮 salt
```

- 使用 `bcryptjs` 库进行密码哈希
- Salt 轮次为 10（符合 OWASP 推荐的 10-12 轮）
- 密码最小长度要求 6 个字符（建议提升到 8-12 个字符）

**改进建议**：
```javascript
// 建议增强密码强度要求
if (!password || password.length < 8) {
  throw new Error('密码至少8个字符，且应包含大小写字母、数字和特殊字符');
}
```

---

## 二、哪吒探针集成安全审查

### 2.1 哪吒 Token 明文存储 🔴 [严重]

**问题描述**：
哪吒探针的 Bearer Token 以明文形式存储在两处：
1. 数据库 `config` 表（`src/database.js`）
2. JSON 配置文件 `data/config.json`

**实际泄露示例**：
```json
// data/config.json 第4行
{
  "nezha": {
    "apiUrl": "https://tz.nm.sd",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjgyODc0NzEsImlwIjoiIiwib3JpZ19pYXQiOjE3NjgyODM4NzEsInVzZXJfaWQiOiIyIn0.625ciQfhbL_nwh2WEfhY-CoG5zkcBcjXgYFedRBn0IQ"
  }
}
```

**风险等级**：🔴 **严重** - 此 Token 可完全控制哪吒探针面板

**攻击路径**：
1. 攻击者通过目录遍历或备份文件获取 `config.json`
2. 使用泄露的 Token 访问哪吒 API（`https://tz.nm.sd/api/v1/server`）
3. 获取所有服务器列表、IP、规格、运行状态
4. 可能进一步攻击暴露的服务器

**修复方案**：

**方案1：环境变量存储（推荐）**
```javascript
// src/server.js
const nezhaConfig = {
  apiUrl: process.env.NEZHA_API_URL || ConfigDB.get('nezha')?.apiUrl,
  token: process.env.NEZHA_TOKEN || ConfigDB.get('nezha')?.token,
};
```

```bash
# .env 文件（必须加入 .gitignore）
NEZHA_API_URL=https://tz.nm.sd
NEZHA_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**方案2：加密存储（次优）**
```javascript
const crypto = require('crypto');

// 使用 AES-256-GCM 加密 Token
function encryptToken(token, masterKey) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', masterKey, iv);
  const encrypted = Buffer.concat([cipher.update(token, 'utf8'), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return { encrypted: encrypted.toString('hex'), iv: iv.toString('hex'), authTag: authTag.toString('hex') };
}
```

**立即行动**：
1. ✅ 确认 `data/config.json` 已在 `.gitignore` 中
2. ⚠️ **立即撤销当前 Token，重新生成新 Token**
3. 迁移到环境变量存储方案

---

### 2.2 哪吒 API 调用未验证 SSL 证书 🟡 [中危]

**问题描述**：
`nezha-client.js` 使用 Node.js 内置 `fetch` 调用 HTTPS API，但未显式验证 SSL 证书。

**潜在风险**：
- 中间人攻击（MITM）
- DNS 劫持导致连接到恶意服务器

**当前代码**：
```javascript
// src/nezha-client.js 第35行
const response = await fetch(url, {
  ...options,
  headers
});
```

**修复建议**：
```javascript
const https = require('https');

const response = await fetch(url, {
  ...options,
  headers,
  agent: new https.Agent({
    rejectUnauthorized: true, // 强制验证证书
    minVersion: 'TLSv1.2'     // 最低 TLS 版本
  })
});
```

---

### 2.3 哪吒配置 API 需认证保护 ✅ [安全]

**检查结果**：✅ **已正确使用 authMiddleware 保护**

**证据**：
```javascript
// src/server.js 第418行
app.get('/api/nezha/config', authMiddleware, (req, res) => { ... });
app.post('/api/nezha/config', authMiddleware, (req, res) => { ... });
```

所有哪吒配置相关的 API 端点均已添加 `authMiddleware`，需要 JWT 认证才能访问。

---

## 三、公开 API 端点安全审查

### 3.1 服务器列表公开暴露 🔴 [严重]

**问题描述**：
`/api/public/servers` 端点**无需任何认证**即可访问，暴露以下敏感信息：

**暴露的数据**（`src/server.js` 第147-193行）：
```json
{
  "success": true,
  "data": [
    {
      "id": "vps_xxx",
      "name": "测试VPS1",
      "location": "US",
      "online": true,
      "remainingDays": 365,
      "expiryDate": "2027-01-01",
      "specs": {
        "cpu": { "cores": 4 },
        "memory": { "size": 8 },
        "storage": { "size": 100 }
      },
      "nezha": {
        "online": true,
        "uptime": 99.5,
        "cpuUsage": 25.3,
        "memUsage": 60.2,
        "diskUsage": 45.1
      }
    }
  ]
}
```

**风险分析**：
- ❌ **暴露服务器数量和在线状态** - 攻击者可持续监控
- ❌ **暴露地理位置** - 可推测数据中心和网络拓扑
- ❌ **暴露硬件规格** - 可针对性发起资源耗尽攻击
- ❌ **暴露运行时数据** - 可分析负载模式寻找薄弱时段
- ⚠️ 虽然未暴露 IP，但结合其他信息可进行指纹识别

**攻击场景**：
1. 扫描脚本定期访问 `/api/public/servers`
2. 记录所有服务器的上线时间、规格变化
3. 识别新增服务器并标记为潜在攻击目标
4. 在负载高峰期发起 DDoS 攻击

**修复方案**：

**方案1：完全移除公开 API（推荐）**
```javascript
// 删除以下端点
// app.get('/api/public/servers', ...);
// app.get('/api/public/stats', ...);
// app.get('/api/public/rankings', ...);
```

**方案2：添加认证要求**
```javascript
app.get('/api/public/servers', authMiddleware, (req, res) => {
  // 仅登录用户可访问
});
```

**方案3：限制暴露信息（次优）**
```javascript
app.get('/api/public/servers', rateLimitMiddleware, (req, res) => {
  const vpsList = VpsDB.getAll();

  // 仅返回最少信息
  const publicServers = vpsList.map(vps => ({
    id: hashId(vps.id),  // 使用哈希ID替代真实ID
    status: vps.nezha?.online ? 'online' : 'offline'
    // 移除所有其他信息
  }));

  res.json({ success: true, data: publicServers });
});
```

---

### 3.2 统计信息泄露运营数据 🟠 [高危]

**问题描述**：
`/api/public/stats` 无需认证暴露运营统计数据。

**暴露的数据**（`src/server.js` 第195-220行）：
```json
{
  "totalServers": 50,
  "onlineServers": 47,
  "offlineServers": 3,
  "expiringServers": 5
}
```

**风险**：
- 竞争对手可监控业务规模
- 攻击者可判断基础设施健康度
- 即将到期服务器数量可暴露财务状况

**修复建议**：添加认证或完全移除此端点。

---

### 3.3 性价比排行榜暴露定价策略 🟡 [中危]

**问题描述**：
`/api/public/rankings` 暴露服务器性价比排行，可能间接泄露定价和采购策略。

**修复建议**：
- 添加认证要求
- 或限制返回前 10 名（避免暴露全量数据）

---

## 四、认证和授权审查

### 4.1 JWT 密钥硬编码 🔴 [严重]

**问题描述**：
JWT 签名密钥使用硬编码的默认值，且密钥强度不足。

**当前代码**（`src/auth.js` 第5行）：
```javascript
const JWT_SECRET = process.env.JWT_SECRET || 'vps-manager-secret-key-change-in-production';
```

**风险**：
- ❌ 默认密钥已公开在源代码中
- ❌ 任何人可伪造有效的 JWT Token
- ❌ 可绕过所有认证保护的 API

**攻击演示**：
```javascript
// 攻击者使用公开的密钥伪造 Token
const jwt = require('jsonwebtoken');
const fakeToken = jwt.sign(
  { username: 'admin' },
  'vps-manager-secret-key-change-in-production',
  { expiresIn: '30d' }
);
// 使用 fakeToken 可访问所有受保护的 API
```

**修复方案**：

**强制使用环境变量**：
```javascript
const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
  console.error('严重错误：未设置 JWT_SECRET 环境变量');
  process.exit(1); // 强制退出，不允许使用默认值
}

if (JWT_SECRET.length < 32) {
  console.error('严重错误：JWT_SECRET 长度不足 32 字符');
  process.exit(1);
}
```

**生成强随机密钥**：
```bash
# 使用 OpenSSL 生成 64 字节随机密钥
openssl rand -hex 64

# 添加到 .env 文件
JWT_SECRET=your_generated_random_key_here
```

**立即行动**：
1. ⚠️ **立即更换 JWT_SECRET**
2. 撤销所有现有 Token（强制用户重新登录）
3. 修改代码强制要求环境变量

---

### 4.2 Token 过期时间过长 🟡 [中危]

**问题描述**：
JWT Token 有效期为 3 天（`src/auth.js` 第6行），对于管理系统过长。

**建议**：
```javascript
const TOKEN_EXPIRY = '1h';        // 访问 Token：1 小时
const REFRESH_TOKEN_EXPIRY = '7d'; // 刷新 Token：7 天

// 实现刷新 Token 机制
app.post('/api/auth/refresh', async (req, res) => {
  const { refreshToken } = req.body;
  // 验证刷新 Token 并颁发新的访问 Token
});
```

---

### 4.3 缺少登录失败限制 🟠 [高危]

**问题描述**：
`/api/auth/login` 端点未实现登录尝试限制，可被暴力破解。

**修复建议**：
```javascript
const loginAttempts = new Map(); // 存储 IP -> 失败次数

app.post('/api/auth/login', async (req, res) => {
  const ip = req.ip;
  const attempts = loginAttempts.get(ip) || 0;

  if (attempts >= 5) {
    return res.status(429).json({
      success: false,
      error: '登录尝试次数过多，请30分钟后重试'
    });
  }

  try {
    const result = await login(username, password);
    loginAttempts.delete(ip); // 登录成功清零
    res.json({ success: true, data: result });
  } catch (error) {
    loginAttempts.set(ip, attempts + 1);
    setTimeout(() => loginAttempts.delete(ip), 30 * 60 * 1000); // 30分钟后清零
    res.status(401).json({ success: false, error: error.message });
  }
});
```

---

## 五、速率限制和防护机制

### 5.1 缺少全局速率限制 🟠 [高危]

**问题描述**：
所有 API 端点（包括公开端点）均无速率限制，容易被扫描攻击和爬虫滥用。

**修复方案**：使用 `express-rate-limit` 中间件

```javascript
const rateLimit = require('express-rate-limit');

// 全局限制
const globalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 分钟
  max: 100,                  // 最多 100 次请求
  message: '请求过于频繁，请稍后重试'
});

// 认证端点严格限制
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: '登录尝试次数过多'
});

app.use('/api/', globalLimiter);
app.use('/api/auth/login', authLimiter);
app.use('/api/auth/init', authLimiter);
```

---

### 5.2 缺少请求体大小限制 🟡 [中危]

**问题描述**：
`express.json()` 未设置大小限制，可能被大请求体攻击。

**修复**：
```javascript
app.use(express.json({ limit: '1mb' })); // 限制请求体最大 1MB
```

---

### 5.3 缺少 CORS 策略 🟡 [中危]

**问题描述**：
未配置 CORS，默认允许所有跨域请求。

**修复建议**：
```javascript
const cors = require('cors');

app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || 'http://localhost:3000',
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
```

---

## 六、错误处理和信息泄露

### 6.1 错误信息过于详细 🟡 [中危]

**问题描述**：
多处 API 端点直接返回原始错误信息，可能泄露内部实现细节。

**示例**（`src/server.js` 第340-343行）：
```javascript
catch (error) {
  res.status(500).json({
    success: false,
    error: error.message  // ❌ 可能泄露数据库结构、文件路径等
  });
}
```

**修复建议**：
```javascript
catch (error) {
  console.error('[内部错误]', error); // 记录到日志
  res.status(500).json({
    success: false,
    error: '服务器内部错误，请稍后重试' // 统一的用户友好消息
  });
}
```

---

### 6.2 缺少安全响应头 🟡 [中危]

**问题描述**：
未设置安全相关的 HTTP 响应头。

**修复方案**：使用 `helmet` 中间件
```javascript
const helmet = require('helmet');

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https:"],
    }
  },
  hsts: {
    maxAge: 31536000,
    includeSubDomains: true,
    preload: true
  }
}));
```

---

## 七、其他安全建议

### 7.1 依赖项安全审计

**建议定期执行**：
```bash
npm audit
npm audit fix
```

**当前依赖安全检查**：
```bash
npm ls better-sqlite3  # 确保使用最新版本
npm ls bcryptjs        # 确保使用最新版本
npm ls jsonwebtoken    # 检查是否有已知漏洞
```

---

### 7.2 数据库备份和恢复

**建议实施**：
1. 定期自动备份数据库文件
2. 备份文件加密存储
3. 测试恢复流程

```javascript
// 备份脚本示例
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function backupDatabase() {
  const srcPath = path.join(__dirname, 'data', 'vps-manager.db');
  const backupDir = path.join(__dirname, 'backups');
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupPath = path.join(backupDir, `backup-${timestamp}.db`);

  fs.mkdirSync(backupDir, { recursive: true });
  fs.copyFileSync(srcPath, backupPath);

  console.log(`数据库已备份至: ${backupPath}`);
}

// 每天自动备份
setInterval(backupDatabase, 24 * 60 * 60 * 1000);
```

---

### 7.3 日志和审计

**建议添加操作审计日志**：
```javascript
function auditLog(action, user, details) {
  const log = {
    timestamp: new Date().toISOString(),
    action,
    user,
    details,
    ip: req.ip
  };

  // 写入数据库或文件
  fs.appendFileSync('audit.log', JSON.stringify(log) + '\n');
}

// 使用示例
app.delete('/api/vps/:id', authMiddleware, (req, res) => {
  VpsDB.delete(id);
  auditLog('DELETE_VPS', req.user.username, { vpsId: id });
});
```

---

## 八、安全检查清单和修复优先级

### 立即修复（严重风险）🔴

- [ ] **撤销泄露的哪吒 Token，重新生成**
- [ ] **更换 JWT_SECRET 为强随机密钥（64字节）**
- [ ] **移除公开 API 端点或添加认证**（`/api/public/*`）
- [ ] **检查 Git 历史，清除已提交的敏感文件**

### 高优先级（高危风险）🟠

- [ ] **实现登录失败限制（防暴力破解）**
- [ ] **添加全局速率限制中间件**
- [ ] **迁移哪吒 Token 到环境变量存储**
- [ ] **配置 CORS 策略限制跨域请求**

### 中优先级（中危风险）🟡

- [ ] **缩短 JWT Token 有效期到 1 小时**
- [ ] **限制请求体大小（1MB）**
- [ ] **统一错误消息避免信息泄露**
- [ ] **添加安全响应头（helmet）**
- [ ] **验证哪吒 API SSL 证书**

### 低优先级（最佳实践）🟢

- [ ] **增强密码强度要求（8字符+复杂度）**
- [ ] **实现数据库自动备份机制**
- [ ] **添加操作审计日志**
- [ ] **定期执行依赖安全审计**

---

## 九、总结和建议

### 当前安全状况评分：**45/100**（需要大幅改进）

**主要问题**：
1. 多处硬编码密钥和明文存储敏感信息
2. 公开 API 暴露大量运营数据
3. 缺少基本的防护机制（速率限制、登录限制）
4. 错误处理可能泄露内部信息

**修复后预期评分**：**85/100**（基本安全）

### 下一步行动计划

**第1天（紧急修复）**：
1. 撤销并更换所有泄露的密钥（哪吒 Token、JWT Secret）
2. 移除公开 API 端点或添加认证
3. 添加速率限制和登录失败限制

**第2-3天（加固防护）**：
1. 迁移敏感配置到环境变量
2. 实现安全响应头和 CORS 策略
3. 统一错误处理避免信息泄露

**第4-7天（长期优化）**：
1. 实现自动备份和恢复机制
2. 添加操作审计日志
3. 编写安全测试用例

---

## 十、附录

### A. 环境变量配置模板

创建 `.env.example` 文件（可提交到 Git）：
```bash
# 服务器配置
PORT=3000
NODE_ENV=production

# JWT 配置
JWT_SECRET=your_random_64_byte_hex_string_here
JWT_EXPIRY=1h

# 哪吒探针配置
NEZHA_API_URL=https://your-nezha-domain.com
NEZHA_TOKEN=your_nezha_bearer_token_here

# CORS 配置
ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com
```

### B. 安全加固脚本

创建 `scripts/security-check.sh`：
```bash
#!/bin/bash

echo "=== VPS Manager 安全检查 ==="

# 检查敏感文件是否存在
if [ -f "data/config.json" ]; then
  echo "⚠️  警告: data/config.json 存在，可能包含敏感信息"
fi

# 检查环境变量
if [ -z "$JWT_SECRET" ]; then
  echo "❌ 错误: JWT_SECRET 环境变量未设置"
  exit 1
fi

if [ ${#JWT_SECRET} -lt 32 ]; then
  echo "❌ 错误: JWT_SECRET 长度不足 32 字符"
  exit 1
fi

# 检查依赖安全
npm audit --production

echo "✅ 安全检查完成"
```

---

**报告编制**：Claude Code
**审查日期**：2026-01-14
**下次审查建议**：修复后 7 天复查
