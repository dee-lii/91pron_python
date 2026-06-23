# VPS Manager v3.0 - 全生命周期管理平台

一个功能强大的 VPS 管理工具，提供批量管理、趋势可视化和续费决策支持。

## 功能特性

### 📊 多 VPS 批量管理
- VPS 列表卡片式展示
- 添加/编辑/删除 VPS
- 支持字段：名称、服务商、价格、货币、周期、购买日期、备注
- 数据导出/导入（JSON 格式）
- 多种排序方式：剩余价值、使用率、购买日期、服务商
- 实时计算剩余价值、剩余天数、使用率

### 📈 成本趋势可视化
- 统计卡片：VPS 总数、总投入、剩余价值、平均使用率
- 饼图：已消耗 vs 剩余价值
- 柱状图：多个 VPS 对比
- 折线图：单个 VPS 价值衰减趋势

### 🤔 续费决策助手
- 智能分析续费 vs 重购的性价比
- 支持多货币转换
- 支持折扣计算
- 显示节省金额和日均成本对比

## 快速开始

### 安装依赖
```bash
npm install
```

### 启动服务
```bash
npm start
```

### 访问应用
打开浏览器访问 http://localhost:3000/index.html

## 技术栈

- **前端**：HTML5 + CSS3 + Vanilla JavaScript
- **图表库**：Chart.js v4
- **后端**：Express.js
- **数据存储**：localStorage + JSON 导出/导入

## 项目结构

```
vps-manager-v3/
├── src/
│   ├── index.html        # 前端单页面应用
│   ├── calculator.js     # 核心计算模块
│   └── server.js         # Express 服务器
├── .claude/              # 开发文档
│   ├── context-summary-frontend-app.md
│   ├── operations-log.md
│   └── verification-report.md
├── package.json
└── README.md
```

## 使用指南

### 1. 添加 VPS
1. 点击右上角"添加 VPS"按钮
2. 填写 VPS 信息（名称、服务商、价格等）
3. 点击"保存"

### 2. 查看趋势
1. 切换到"趋势可视化"标签
2. 查看统计数据和图表
3. 在下拉菜单选择 VPS 查看价值衰减趋势

### 3. 续费决策
1. 切换到"续费决策"标签
2. 填写当前 VPS 信息和续费信息
3. 输入折扣（可选）
4. 点击"计算决策"查看建议

### 4. 数据管理
- **导出**：点击"导出数据"按钮，下载 JSON 文件
- **导入**：点击"导入数据"，选择 JSON 文件

## API 接口

### 获取汇率
```
GET /api/exchange-rate?from=USD&to=CNY
```

**响应示例**：
```json
{
  "from": "USD",
  "to": "CNY",
  "rate": 7.2345,
  "timestamp": "2026-01-12T09:20:00.000Z"
}
```

## 浏览器支持

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 开发团队

由 Claude Code 开发 ⚡

## 许可证

MIT License
