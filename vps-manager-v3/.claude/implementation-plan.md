# VPS Manager v3 - 架构设计与技术选型

生成时间：2026-01-12

## 一、项目概述

### 1.1 核心需求
基于原项目 `/Users/deelii/code/syjzjs/vps-剩余价值计算/` 的基础上，开发多 VPS 批量管理系统，实现三大核心功能：

1. **多 VPS 批量管理面板**
   - 支持添加、编辑、删除多个 VPS 记录
   - 使用 localStorage 本地存储数据
   - 支持数据导出/导入（JSON 格式）

2. **成本趋势可视化**
   - 显示每个 VPS 的剩余价值变化趋势
   - 显示总成本和总剩余价值统计
   - 使用轻量级图表库实现

3. **续费决策助手**
   - 对比不同续费周期的成本效益
   - 计算最优续费时机
   - 提供续费建议

### 1.2 设计理念继承
延续原项目的核心理念：
- ✅ **极简设计**：单页面应用，无复杂路由
- ✅ **无数据库**：纯前端存储（localStorage）
- ✅ **Docker 部署**：一键启动，环境隔离
- ✅ **复用逻辑**：继承原项目的计算核心和汇率功能

### 1.3 技术边界
- **前端优先**：90% 的逻辑在浏览器完成
- **后端辅助**：仅提供汇率 API 和静态文件服务
- **离线可用**：数据本地存储，断网可继续操作
- **轻量部署**：Docker 镜像 < 100MB

---

## 二、原项目分析总结

### 2.1 可复用组件清单

#### **核心计算逻辑**（`calculator.js`）
```javascript
✅ calculateRemainingValue(totalCost, totalDays, usedDays)
   - 计算剩余价值、已使用价值、使用率、日均消耗
   - 完善的参数验证
   - 浮点数精度处理（toFixed(2)）

✅ getDaysByCycle(cycle)
   - 支持 monthly/yearly/biennial/triennial
   - 返回对应天数：30/365/730/1095

✅ calculateUsedDays(purchaseDate)
   - 根据购买日期计算已使用天数
   - 日期合法性验证

✅ validateInputs(totalCost, totalDays, usedDays)
   - 统一的参数验证逻辑
```

#### **汇率功能**（`server.js`）
```javascript
✅ fetchExchangeRate(from, to)
   - 多 API 源支持（exchangerate-api.com, open.er-api.com, api.frankfurter.app）
   - 汇率缓存（1小时）
   - 降级缓存机制（API 失败时使用过期缓存）
   - 支持货币：USD, CNY, EUR, GBP, JPY, KRW

✅ GET /api/exchange-rate
   - 返回格式：{ base, target, rate, timestamp, source, fromCache }
```

#### **SVG 徽章生成**（可选复用）
```javascript
✅ GET /api/badge.svg
   - 动态显示剩余价值
   - 使用率进度条可视化
   - 支持自定义货币符号
```

### 2.2 技术栈特点
| 技术 | 版本 | 理由 |
|------|------|------|
| **Node.js** | 18.x LTS | 稳定、长期支持 |
| **Express** | ^4.18.2 | 轻量、成熟 |
| **原生 HTML/CSS/JS** | ES6+ | 无构建工具，简化部署 |
| **Docker** | Alpine Linux | 最小化镜像（~50MB） |
| **测试框架** | Jest | 覆盖率目标：90%+ |

### 2.3 关键设计模式
1. **无状态 API**：后端不存储任何业务数据
2. **前端驱动**：HTML 自包含（CSS/JS 内联）
3. **渐进增强**：核心功能不依赖后端（可离线使用汇率缓存）
4. **健康检查**：Docker HEALTHCHECK 确保服务可用

---

## 三、新项目架构设计

### 3.1 系统架构图
```
┌─────────────────────────────────────────────────────────────┐
│                      浏览器客户端                            │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │              单页面应用（index.html）                    │ │
│ │ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐ │ │
│ │ │ VPS 管理面板 │ │ 趋势可视化  │ │ 续费决策助手        │ │ │
│ │ │ - 列表展示   │ │ - 图表展示  │ │ - 对比计算          │ │ │
│ │ │ - 增删改查   │ │ - 统计汇总  │ │ - 建议生成          │ │ │
│ │ └─────────────┘ └─────────────┘ └─────────────────────┘ │ │
│ │                         ↓                                │ │
│ │ ┌───────────────────────────────────────────────────────┐│ │
│ │ │         核心逻辑层（calculator-client.js）            ││ │
│ │ │  - 复用原项目计算函数                                 ││ │
│ │ │  - 批量计算增强                                       ││ │
│ │ │  - 趋势数据生成                                       ││ │
│ │ └───────────────────────────────────────────────────────┘│ │
│ │                         ↓                                │ │
│ │ ┌───────────────────────────────────────────────────────┐│ │
│ │ │         数据管理层（storage.js）                      ││ │
│ │ │  - localStorage 封装                                  ││ │
│ │ │  - 导出/导入（JSON）                                  ││ │
│ │ │  - 数据验证                                           ││ │
│ │ └───────────────────────────────────────────────────────┘│ │
│ │                         ↓                                │ │
│ │ ┌───────────────────────────────────────────────────────┐│ │
│ │ │         图表渲染层（chart.js - Chart.js 库）          ││ │
│ │ │  - 剩余价值趋势图（折线图）                           ││ │
│ │ │  - 成本分布图（饼图）                                 ││ │
│ │ │  - 使用率对比（柱状图）                               ││ │
│ │ └───────────────────────────────────────────────────────┘│ │
│ └─────────────────────────────────────────────────────────┘ │
│                         ↓ HTTP/HTTPS                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                   Express 后端服务                           │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │            API 路由（继承原项目）                        │ │
│ │  GET  /api/health         - 健康检查                    │ │
│ │  GET  /api/exchange-rate  - 汇率查询（带缓存）          │ │
│ │  GET  /api/badge.svg      - SVG 徽章生成（可选）        │ │
│ │  GET  /                   - 返回 index.html              │ │
│ └─────────────────────────────────────────────────────────┘ │
│                         ↓                                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │         汇率服务（复用原项目）                           │ │
│ │  - 多 API 源                                             │ │
│ │  - 内存缓存（1小时）                                     │ │
│ │  - 降级策略                                              │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Docker 容器                                │
│  - Node.js 18 Alpine                                         │
│  - 端口：3000                                                │
│  - 健康检查：/api/health                                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据流设计

#### **3.2.1 VPS 数据结构**
```javascript
// 单个 VPS 记录
{
  id: "uuid-v4",                    // 唯一标识
  name: "Vultr Tokyo",              // VPS 名称
  provider: "Vultr",                // 服务商
  totalCost: 120,                   // 总成本（原始货币）
  currency: "USD",                  // 货币类型
  cycle: "yearly",                  // 付款周期
  purchaseDate: "2025-01-01",       // 购买日期
  notes: "用于博客部署",            // 备注
  createdAt: "2025-01-01T00:00:00Z", // 创建时间
  updatedAt: "2025-01-01T00:00:00Z"  // 更新时间
}

// 全局数据结构
{
  version: "3.0.0",                 // 数据格式版本
  vpsList: [VPS, VPS, ...],         // VPS 列表
  settings: {
    defaultCurrency: "CNY",         // 默认显示货币
    autoRefresh: true,              // 自动刷新汇率
    theme: "light"                  // 主题（light/dark）
  },
  lastSync: "2025-01-12T12:00:00Z"  // 最后同步时间
}
```

#### **3.2.2 计算数据流**
```javascript
// 输入：VPS 记录
const vps = {
  totalCost: 120,
  currency: "USD",
  cycle: "yearly",
  purchaseDate: "2025-01-01"
};

// 步骤 1：计算基础数据
const totalDays = getDaysByCycle(vps.cycle);        // 365
const usedDays = calculateUsedDays(vps.purchaseDate); // 11（假设今天 2025-01-12）

// 步骤 2：执行核心计算
const result = calculateRemainingValue(
  vps.totalCost,   // 120
  totalDays,       // 365
  usedDays         // 11
);
// 输出：{ remainingValue: 116.37, usedValue: 3.63, remainingDays: 354, usageRate: 3.01, dailyRate: 0.33 }

// 步骤 3：汇率转换（如需要）
const exchangeRate = await fetchExchangeRate(vps.currency, "CNY"); // 7.2
const remainingValueCNY = result.remainingValue * exchangeRate.rate; // 838.87
```

#### **3.2.3 趋势数据生成**
```javascript
// 生成未来 12 个月的剩余价值趋势
function generateTrend(vps) {
  const totalDays = getDaysByCycle(vps.cycle);
  const dailyRate = vps.totalCost / totalDays;
  const purchaseDate = new Date(vps.purchaseDate);

  const trend = [];
  for (let month = 0; month <= 12; month++) {
    const targetDate = new Date(purchaseDate);
    targetDate.setMonth(targetDate.getMonth() + month);

    const usedDays = Math.floor((targetDate - purchaseDate) / (1000 * 60 * 60 * 24));
    const remainingDays = Math.max(0, totalDays - usedDays);
    const remainingValue = dailyRate * remainingDays;

    trend.push({
      date: targetDate.toISOString().split('T')[0],
      remainingValue: parseFloat(remainingValue.toFixed(2)),
      usageRate: parseFloat(((usedDays / totalDays) * 100).toFixed(2))
    });
  }

  return trend;
}
```

---

## 四、技术选型

### 4.1 前端图表库选型

| 库名 | 体积 | 优势 | 劣势 | 决策 |
|------|------|------|------|------|
| **Chart.js** | 50KB (min+gzip) | ✅ 轻量简洁<br>✅ API 简单<br>✅ 响应式<br>✅ 无依赖 | ❌ 自定义能力弱 | ⭐ **推荐** |
| **ECharts** | 300KB+ | ✅ 功能强大<br>✅ 可视化丰富 | ❌ 体积大<br>❌ 过度设计 | ❌ 不适合 |
| **ApexCharts** | 150KB | ✅ 现代化<br>✅ 动画流畅 | ❌ 体积偏大 | ❌ 不适合 |
| **Plotly.js** | 500KB+ | ✅ 科学图表 | ❌ 体积过大 | ❌ 不适合 |

**最终选择**：**Chart.js v4.x**
- **理由**：轻量级、API 简洁、满足基础可视化需求、与原项目极简理念一致
- **CDN 引入**：`<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>`

### 4.2 前端技术栈
| 技术 | 选型 | 理由 |
|------|------|------|
| **HTML** | HTML5 | 原生标准，无需构建 |
| **CSS** | 内联样式 + CSS 变量 | 单文件自包含，支持主题切换 |
| **JavaScript** | 原生 ES6+ | 避免打包工具，现代浏览器支持 |
| **图表库** | Chart.js v4 | 轻量级（50KB），功能足够 |
| **UUID 生成** | crypto.randomUUID() | 浏览器原生 API（无需引入库） |
| **日期处理** | Date 原生 API | 需求简单，无需 moment.js/dayjs |

### 4.3 后端技术栈（继承原项目）
| 技术 | 版本 | 说明 |
|------|------|------|
| **Node.js** | 18.x LTS | 与原项目保持一致 |
| **Express** | ^4.18.2 | 继承原项目 |
| **测试框架** | Jest ^29.7.0 | 继承原项目 |

### 4.4 存储方案
| 方案 | 选型 | 理由 |
|------|------|------|
| **主存储** | localStorage | ✅ 5MB 容量<br>✅ 无需服务器<br>✅ 简单可靠 |
| **导出格式** | JSON | ✅ 通用标准<br>✅ 可读性强 |
| **备份策略** | 手动导出 | ✅ 用户控制<br>✅ 隐私安全 |

---

## 五、目录结构规划

```
vps-manager-v3/
├── .claude/
│   ├── implementation-plan.md          # 本文档
│   ├── context-summary-vps-manager.md  # 上下文摘要
│   ├── operations-log.md               # 操作日志
│   └── verification-report.md          # 验证报告
│
├── src/
│   ├── server.js                       # Express 服务器（复用原项目）
│   │   ├── GET  /                      # 返回 index.html
│   │   ├── GET  /api/health            # 健康检查
│   │   ├── GET  /api/exchange-rate     # 汇率 API
│   │   └── GET  /api/badge.svg         # SVG 徽章（可选）
│   │
│   ├── calculator.js                   # 计算核心（复用原项目）
│   │   ├── calculateRemainingValue()   # 核心计算
│   │   ├── getDaysByCycle()            # 周期转天数
│   │   ├── calculateUsedDays()         # 计算已使用天数
│   │   └── validateInputs()            # 参数验证
│   │
│   └── index.html                      # 前端单页面应用（自包含）
│       ├── <style>                     # 内联 CSS
│       │   ├── 全局样式
│       │   ├── VPS 列表样式
│       │   ├── 图表容器样式
│       │   └── 响应式布局
│       │
│       └── <script>                    # 内联 JavaScript
│           ├── calculator-client.js    # 计算逻辑（从 calculator.js 提取）
│           ├── storage.js              # localStorage 封装
│           ├── vps-manager.js          # VPS 管理逻辑
│           ├── trend-chart.js          # 趋势图渲染（Chart.js）
│           ├── renewal-advisor.js      # 续费决策逻辑
│           └── app.js                  # 主应用入口
│
├── tests/
│   ├── calculator.test.js              # 计算逻辑测试（继承原项目）
│   ├── api.test.js                     # API 测试（继承原项目）
│   ├── storage.test.js                 # 存储逻辑测试（新增）
│   └── vps-manager.test.js             # 管理功能测试（新增）
│
├── Dockerfile                          # Docker 镜像构建（继承原项目）
├── .dockerignore                       # Docker 忽略文件
├── docker-compose.yml                  # 容器编排（可选）
├── package.json                        # 依赖管理
├── package-lock.json                   # 依赖锁定
└── README.md                           # 项目说明

```

---

## 六、核心模块职责划分

### 6.1 后端模块（src/server.js）
**继承原项目，微调增强**

```javascript
// 职责
1. 静态文件服务：返回 index.html
2. 汇率 API：GET /api/exchange-rate（原项目逻辑）
3. 健康检查：GET /api/health（原项目逻辑）
4. SVG 徽章：GET /api/badge.svg（可选）

// 新增功能
- 无（后端保持极简，所有业务逻辑在前端）
```

### 6.2 计算核心（src/calculator.js）
**完全复用原项目**

```javascript
// 导出函数（与原项目一致）
module.exports = {
  calculateRemainingValue,  // 核心计算
  validateInputs,           // 参数验证
  isValidNumber,            // 数字验证
  getDaysByCycle,           // 周期转天数
  calculateUsedDays         // 计算已使用天数
};

// 新增功能
- 无（保持稳定性，不修改核心逻辑）
```

### 6.3 前端核心模块（index.html 内嵌脚本）

#### **6.3.1 calculator-client.js**
```javascript
// 职责：计算逻辑（从 calculator.js 提取并适配浏览器）
class Calculator {
  // 复用原项目函数
  calculateRemainingValue(totalCost, totalDays, usedDays) { /*...*/ }
  getDaysByCycle(cycle) { /*...*/ }
  calculateUsedDays(purchaseDate) { /*...*/ }
  validateInputs(totalCost, totalDays, usedDays) { /*...*/ }

  // 新增：批量计算
  calculateBatch(vpsList) {
    return vpsList.map(vps => {
      const totalDays = this.getDaysByCycle(vps.cycle);
      const usedDays = this.calculateUsedDays(vps.purchaseDate);
      return {
        ...vps,
        ...this.calculateRemainingValue(vps.totalCost, totalDays, usedDays)
      };
    });
  }

  // 新增：生成趋势数据
  generateTrend(vps, months = 12) { /*...*/ }
}
```

#### **6.3.2 storage.js**
```javascript
// 职责：localStorage 数据管理
class StorageManager {
  constructor() {
    this.storageKey = 'vps-manager-v3';
    this.version = '3.0.0';
  }

  // 加载数据
  load() {
    const data = localStorage.getItem(this.storageKey);
    return data ? JSON.parse(data) : this.getDefaultData();
  }

  // 保存数据
  save(data) {
    data.version = this.version;
    data.lastSync = new Date().toISOString();
    localStorage.setItem(this.storageKey, JSON.stringify(data));
  }

  // 导出 JSON
  export() {
    const data = this.load();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vps-manager-backup-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // 导入 JSON
  import(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result);
          this.validate(data);
          this.save(data);
          resolve(data);
        } catch (error) {
          reject(error);
        }
      };
      reader.onerror = reject;
      reader.readAsText(file);
    });
  }

  // 数据验证
  validate(data) {
    if (!data.version || !data.vpsList || !Array.isArray(data.vpsList)) {
      throw new Error('无效的数据格式');
    }
  }

  // 默认数据
  getDefaultData() {
    return {
      version: this.version,
      vpsList: [],
      settings: {
        defaultCurrency: 'CNY',
        autoRefresh: true,
        theme: 'light'
      },
      lastSync: new Date().toISOString()
    };
  }
}
```

#### **6.3.3 vps-manager.js**
```javascript
// 职责：VPS 增删改查逻辑
class VPSManager {
  constructor(storage, calculator) {
    this.storage = storage;
    this.calculator = calculator;
  }

  // 获取所有 VPS
  getAll() {
    return this.storage.load().vpsList;
  }

  // 添加 VPS
  add(vps) {
    const data = this.storage.load();
    const newVPS = {
      id: crypto.randomUUID(),
      ...vps,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    data.vpsList.push(newVPS);
    this.storage.save(data);
    return newVPS;
  }

  // 更新 VPS
  update(id, updates) {
    const data = this.storage.load();
    const index = data.vpsList.findIndex(v => v.id === id);
    if (index === -1) throw new Error('VPS 不存在');

    data.vpsList[index] = {
      ...data.vpsList[index],
      ...updates,
      updatedAt: new Date().toISOString()
    };
    this.storage.save(data);
    return data.vpsList[index];
  }

  // 删除 VPS
  delete(id) {
    const data = this.storage.load();
    data.vpsList = data.vpsList.filter(v => v.id !== id);
    this.storage.save(data);
  }

  // 批量计算
  calculateAll() {
    const vpsList = this.getAll();
    return this.calculator.calculateBatch(vpsList);
  }
}
```

#### **6.3.4 trend-chart.js**
```javascript
// 职责：Chart.js 图表渲染
class TrendChart {
  constructor(canvasId) {
    this.ctx = document.getElementById(canvasId).getContext('2d');
    this.chart = null;
  }

  // 渲染剩余价值趋势图
  renderTrend(vpsList, calculator) {
    const datasets = vpsList.map(vps => {
      const trend = calculator.generateTrend(vps);
      return {
        label: vps.name,
        data: trend.map(t => t.remainingValue),
        borderColor: this.getRandomColor(),
        tension: 0.1
      };
    });

    const labels = calculator.generateTrend(vpsList[0] || {}).map(t => t.date);

    if (this.chart) this.chart.destroy();

    this.chart = new Chart(this.ctx, {
      type: 'line',
      data: {
        labels,
        datasets
      },
      options: {
        responsive: true,
        plugins: {
          title: {
            display: true,
            text: 'VPS 剩余价值趋势（未来 12 个月）'
          }
        }
      }
    });
  }

  // 生成随机颜色
  getRandomColor() {
    const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF'];
    return colors[Math.floor(Math.random() * colors.length)];
  }
}
```

#### **6.3.5 renewal-advisor.js**
```javascript
// 职责：续费决策逻辑
class RenewalAdvisor {
  constructor(calculator) {
    this.calculator = calculator;
  }

  // 对比不同续费周期
  compare(vps, currentExchangeRate) {
    const cycles = ['monthly', 'yearly', 'biennial', 'triennial'];

    const comparisons = cycles.map(cycle => {
      const totalDays = this.calculator.getDaysByCycle(cycle);
      const usedDays = this.calculator.calculateUsedDays(vps.purchaseDate);
      const result = this.calculator.calculateRemainingValue(
        vps.totalCost,
        totalDays,
        usedDays
      );

      return {
        cycle,
        totalDays,
        dailyRate: result.dailyRate,
        totalCostCNY: vps.totalCost * currentExchangeRate,
        costPerDay: (vps.totalCost * currentExchangeRate) / totalDays
      };
    });

    // 找出最优方案（日均成本最低）
    const optimal = comparisons.reduce((min, current) =>
      current.costPerDay < min.costPerDay ? current : min
    );

    return { comparisons, optimal };
  }

  // 生成续费建议
  suggest(vps, currentResult) {
    const usageRate = currentResult.usageRate;

    if (usageRate < 30) {
      return {
        action: '继续观察',
        reason: '使用率低于 30%，剩余价值充足',
        recommendedCycle: null
      };
    } else if (usageRate < 70) {
      return {
        action: '开始规划',
        reason: '使用率 30%-70%，可考虑提前锁定优惠',
        recommendedCycle: 'yearly'
      };
    } else {
      return {
        action: '立即续费',
        reason: '使用率超过 70%，建议尽快续费',
        recommendedCycle: 'yearly'
      };
    }
  }
}
```

#### **6.3.6 app.js**
```javascript
// 职责：主应用入口，协调各模块
class App {
  constructor() {
    this.storage = new StorageManager();
    this.calculator = new Calculator();
    this.vpsManager = new VPSManager(this.storage, this.calculator);
    this.trendChart = new TrendChart('trend-canvas');
    this.renewalAdvisor = new RenewalAdvisor(this.calculator);

    this.init();
  }

  init() {
    this.renderVPSList();
    this.renderTrendChart();
    this.bindEvents();
  }

  renderVPSList() {
    const vpsList = this.vpsManager.calculateAll();
    // 渲染 HTML 列表
  }

  renderTrendChart() {
    const vpsList = this.vpsManager.getAll();
    this.trendChart.renderTrend(vpsList, this.calculator);
  }

  bindEvents() {
    // 绑定按钮事件
    document.getElementById('add-vps').addEventListener('click', () => this.addVPS());
    document.getElementById('export').addEventListener('click', () => this.storage.export());
    // ...
  }

  async addVPS() {
    // 显示表单，收集数据，调用 vpsManager.add()
  }
}

// 启动应用
document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
```

---

## 七、关键技术决策

### 7.1 为什么选择单页面应用？
| 理由 | 说明 |
|------|------|
| **简化部署** | 无需构建工具，一个 HTML 文件包含所有逻辑 |
| **离线可用** | 数据存储在 localStorage，断网可继续使用 |
| **快速加载** | 无多页面跳转，所有功能即时响应 |
| **继承理念** | 与原项目保持一致 |

### 7.2 为什么使用 localStorage 而非数据库？
| 理由 | 说明 |
|------|------|
| **无状态后端** | 后端仅提供汇率 API，无需管理数据 |
| **隐私安全** | 数据存储在用户本地，无服务器泄露风险 |
| **简化部署** | 无需配置数据库，一键 Docker 启动 |
| **容量充足** | 5MB 存储可容纳数千条 VPS 记录 |

### 7.3 为什么选择 Chart.js？
| 对比项 | Chart.js | ECharts | ApexCharts |
|--------|----------|---------|------------|
| **体积** | 50KB ✅ | 300KB ❌ | 150KB ⚠️ |
| **学习曲线** | 简单 ✅ | 中等 ⚠️ | 中等 ⚠️ |
| **功能** | 满足需求 ✅ | 过度设计 ❌ | 满足需求 ✅ |
| **依赖** | 无 ✅ | 无 ✅ | 无 ✅ |
| **响应式** | 原生支持 ✅ | 支持 ✅ | 支持 ✅ |

**决策**：Chart.js 体积最小，API 最简洁，完全满足需求。

### 7.4 为什么复用原项目计算逻辑？
| 理由 | 说明 |
|------|------|
| **稳定可靠** | 原项目已通过单元测试，覆盖率 90%+ |
| **避免重复** | 无需重新实现和测试 |
| **保持一致** | 计算结果与原项目完全一致 |
| **降低风险** | 减少新 bug 引入可能性 |

---

## 八、风险评估与缓解措施

### 8.1 技术风险

| 风险项 | 风险描述 | 影响 | 缓解措施 |
|--------|----------|------|----------|
| **localStorage 清除** | 用户清除浏览器缓存导致数据丢失 | 高 | ✅ 提供导出/导入功能<br>✅ 定期提醒备份<br>✅ 首页显示备份状态 |
| **浏览器兼容性** | crypto.randomUUID() 不支持老浏览器 | 中 | ✅ 降级方案：Math.random() 生成 UUID<br>✅ 检测并提示升级浏览器 |
| **汇率 API 失败** | 所有汇率 API 源不可用 | 低 | ✅ 继承原项目降级缓存<br>✅ 允许手动输入汇率 |
| **图表渲染性能** | 大量 VPS 导致图表卡顿 | 低 | ✅ 限制图表显示数量（最多 10 个）<br>✅ 提供筛选功能 |

### 8.2 用户体验风险

| 风险项 | 缓解措施 |
|--------|----------|
| **首次使用困惑** | ✅ 提供示例数据<br>✅ 添加操作引导 |
| **数据迁移困难** | ✅ 支持从原项目导入（手动输入）<br>✅ 提供迁移脚本 |
| **移动端体验差** | ✅ 响应式设计<br>✅ 触摸优化 |

---

## 九、开发时间线（预估）

| 阶段 | 任务 | 预估时间 | 依赖 |
|------|------|----------|------|
| **1. 项目初始化** | 创建目录、复制原项目核心文件 | 30 分钟 | - |
| **2. 后端适配** | 修改 server.js，添加静态文件服务 | 30 分钟 | 阶段 1 |
| **3. 前端框架** | 实现 storage.js, calculator-client.js | 1 小时 | 阶段 1 |
| **4. VPS 管理** | 实现 vps-manager.js，增删改查 UI | 2 小时 | 阶段 3 |
| **5. 趋势可视化** | 集成 Chart.js，实现 trend-chart.js | 1.5 小时 | 阶段 4 |
| **6. 续费助手** | 实现 renewal-advisor.js，对比 UI | 1 小时 | 阶段 4 |
| **7. 导入导出** | 实现 JSON 导出/导入功能 | 30 分钟 | 阶段 3 |
| **8. 样式优化** | 响应式布局、主题切换 | 1 小时 | 阶段 4-6 |
| **9. 测试编写** | 单元测试、集成测试 | 1.5 小时 | 阶段 2-7 |
| **10. Docker 化** | 编写 Dockerfile，测试部署 | 30 分钟 | 阶段 9 |
| **11. 文档编写** | README、操作手册 | 30 分钟 | 阶段 10 |
| **总计** | | **~10.5 小时** | |

---

## 十、验证清单

### 10.1 功能验证
- [ ] **VPS 管理**
  - [ ] 添加 VPS 记录
  - [ ] 编辑 VPS 记录
  - [ ] 删除 VPS 记录
  - [ ] 批量计算剩余价值
  - [ ] 显示列表并排序

- [ ] **趋势可视化**
  - [ ] 折线图显示剩余价值趋势
  - [ ] 支持多 VPS 对比
  - [ ] 显示总成本和总剩余价值
  - [ ] 图表响应式调整

- [ ] **续费决策**
  - [ ] 对比不同续费周期
  - [ ] 计算最优方案
  - [ ] 生成续费建议

- [ ] **数据管理**
  - [ ] localStorage 读写正常
  - [ ] 导出 JSON 文件
  - [ ] 导入 JSON 文件
  - [ ] 数据验证

### 10.2 技术验证
- [ ] 后端服务启动成功
- [ ] 汇率 API 正常工作
- [ ] 健康检查通过
- [ ] 前端页面加载正常
- [ ] 所有测试通过（覆盖率 ≥ 85%）
- [ ] Docker 镜像构建成功
- [ ] 容器运行稳定

### 10.3 用户体验验证
- [ ] 移动端适配正常
- [ ] 操作流程流畅
- [ ] 错误提示清晰
- [ ] 首次使用引导完善

---

## 十一、后续优化方向（可选）

### 11.1 功能增强
- [ ] **多设备同步**：使用 WebDAV/S3 同步 localStorage
- [ ] **高级筛选**：按服务商、成本范围、到期时间筛选
- [ ] **提醒功能**：浏览器通知提醒续费
- [ ] **成本预测**：基于历史汇率预测未来成本

### 11.2 性能优化
- [ ] **虚拟滚动**：优化大量 VPS 列表渲染
- [ ] **懒加载图表**：仅加载可见图表
- [ ] **PWA 支持**：离线访问和桌面安装

### 11.3 用户体验
- [ ] **深色模式**：自动跟随系统主题
- [ ] **多语言**：支持英文界面
- [ ] **快捷键**：Ctrl+N 添加 VPS，Ctrl+E 导出等

---

## 十二、交付物清单

### 12.1 代码文件
- [ ] `src/server.js`（Express 服务器）
- [ ] `src/calculator.js`（计算核心）
- [ ] `src/index.html`（前端单页面应用）

### 12.2 测试文件
- [ ] `tests/calculator.test.js`（计算逻辑测试）
- [ ] `tests/api.test.js`（API 测试）
- [ ] `tests/storage.test.js`（存储测试）
- [ ] `tests/vps-manager.test.js`（管理功能测试）

### 12.3 配置文件
- [ ] `package.json`（依赖管理）
- [ ] `Dockerfile`（镜像构建）
- [ ] `.dockerignore`（忽略文件）
- [ ] `docker-compose.yml`（容器编排）

### 12.4 文档
- [ ] `README.md`（使用说明）
- [ ] `.claude/implementation-plan.md`（本文档）
- [ ] `.claude/operations-log.md`（操作日志）
- [ ] `.claude/verification-report.md`（验证报告）

---

## 十三、附录

### 13.1 原项目核心函数复用清单

#### **calculator.js（完全复用）**
```javascript
✅ calculateRemainingValue(totalCost, totalDays, usedDays)
✅ validateInputs(totalCost, totalDays, usedDays)
✅ isValidNumber(value)
✅ getDaysByCycle(cycle)
✅ calculateUsedDays(purchaseDate)
```

#### **server.js（部分复用）**
```javascript
✅ fetchExchangeRate(from, to)                    // 汇率获取
✅ GET /api/exchange-rate                         // 汇率 API
✅ GET /api/health                                 // 健康检查
✅ exchangeRateCache                               // 汇率缓存
✅ EXCHANGE_RATE_APIS                              // API 源配置
```

### 13.2 技术栈对比

| 项目 | Node.js | Express | 前端框架 | 图表库 | 存储 | 测试 |
|------|---------|---------|----------|--------|------|------|
| **原项目** | 18.x | 4.18.2 | 原生 HTML | 无 | 无（纯计算） | Jest |
| **新项目** | 18.x ✅ | 4.18.2 ✅ | 原生 HTML ✅ | Chart.js ⭐ | localStorage ⭐ | Jest ✅ |

### 13.3 数据格式示例

#### **localStorage 数据示例**
```json
{
  "version": "3.0.0",
  "vpsList": [
    {
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "name": "Vultr Tokyo",
      "provider": "Vultr",
      "totalCost": 120,
      "currency": "USD",
      "cycle": "yearly",
      "purchaseDate": "2025-01-01",
      "notes": "用于博客部署",
      "createdAt": "2025-01-01T00:00:00.000Z",
      "updatedAt": "2025-01-01T00:00:00.000Z"
    }
  ],
  "settings": {
    "defaultCurrency": "CNY",
    "autoRefresh": true,
    "theme": "light"
  },
  "lastSync": "2025-01-12T12:00:00.000Z"
}
```

#### **计算结果示例**
```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "Vultr Tokyo",
  "remainingValue": 116.37,
  "usedValue": 3.63,
  "remainingDays": 354,
  "usageRate": 3.01,
  "dailyRate": 0.33,
  "remainingValueCNY": 838.27
}
```

### 13.4 参考资料

**官方文档**：
- [Chart.js 官方文档](https://www.chartjs.org/docs/latest/)
- [Express.js 官方文档](https://expressjs.com/)
- [Jest 测试框架](https://jestjs.io/)
- [localStorage API](https://developer.mozilla.org/zh-CN/docs/Web/API/Window/localStorage)

**最佳实践**：
- [Chart.js 示例库](https://www.chartjs.org/samples/)
- [localStorage 安全指南](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
- [Docker 单页应用部署](https://docs.docker.com/samples/nginx/)

---

## 十四、总结

本设计方案基于原项目 `/Users/deelii/code/syjzjs/vps-剩余价值计算/` 的成功经验，在保持技术栈一致性和设计理念继承的基础上，通过以下策略实现新功能：

### 14.1 核心策略
1. **最大化复用**：calculator.js 和汇率功能完全复用，减少开发和测试成本
2. **轻量级前端**：选择 Chart.js（50KB）而非 ECharts（300KB+），保持极简理念
3. **前端驱动**：90% 逻辑在浏览器完成，后端仅提供汇率 API
4. **离线优先**：localStorage 存储 + 导出/导入，无需服务器依赖

### 14.2 技术亮点
- ✅ 复用原项目稳定可靠的计算核心
- ✅ 继承汇率多源和降级缓存机制
- ✅ 使用轻量级图表库（Chart.js）
- ✅ 单页面应用（自包含 HTML）
- ✅ Docker 一键部署（Alpine Linux）

### 14.3 预期成果
- **开发周期**：~10.5 小时
- **镜像体积**：< 100MB
- **测试覆盖率**：≥ 85%
- **支持的 VPS 数量**：数千条（localStorage 5MB 限制）

本方案已就绪，可直接进入开发阶段。
