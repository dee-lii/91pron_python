## 项目上下文摘要（前端应用开发）
生成时间：2026-01-12

### 1. 相似实现分析
- **无现有前端文件**：这是一个新功能，需要从零创建
- **后端计算逻辑**：src/calculator.js 提供了核心计算函数，需要在前端重新实现
- **后端 API**：src/server.js 提供汇率查询接口 `/api/exchange-rate`

### 2. 项目约定
- **命名约定**：驼峰命名（camelCase）用于变量和函数，中文注释
- **文件组织**：src/ 目录存放源代码
- **代码风格**：使用中文注释，函数有完整的 JSDoc

### 3. 可复用组件清单
- `src/calculator.js` 中的核心函数：
  - `calculateRemainingValue(totalCost, totalDays, usedDays)` - 计算剩余价值
  - `getDaysByCycle(cycle)` - 根据周期获取天数
  - `calculateUsedDays(purchaseDate)` - 计算已使用天数
  - `validateInputs()` - 输入验证
  - `isValidNumber()` - 数字验证

### 4. 技术选型
- **后端框架**：Express.js
- **前端要求**：单页面应用（内联 CSS/JS）
- **图表库**：Chart.js v4（从 CDN 加载）
- **存储方案**：localStorage
- **渐变色**：#667eea → #764ba2（紫色系）

### 5. 依赖和集成点
- **外部依赖**：Chart.js（CDN）
- **后端 API**：
  - `GET /api/exchange-rate?from=USD&to=CNY` - 获取汇率
- **数据存储**：浏览器 localStorage
- **配置来源**：无需配置文件

### 6. 技术选型理由
- **单页面应用**：简化部署，所有资源内联
- **Chart.js**：成熟的图表库，功能强大，文档完善
- **localStorage**：客户端存储，无需后端数据库

### 7. 关键风险点
- **数据持久化**：localStorage 可能被清除，需要导出/导入功能
- **汇率 API 失败**：需要错误处理和降级方案
- **浏览器兼容性**：需要考虑现代浏览器支持
- **数据验证**：前端需要完整的输入验证逻辑
