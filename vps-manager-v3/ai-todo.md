# 项目待办事项 (To-Do List)

## 🎯 核心目标
将 VPS Manager v3.0 打造为一个模块化、高可维护、功能完善的现代化 VPS 管理平台。

## 🚀 正在进行
- [x] **Fix: Nezha auto-sync ByteString error & unsupported cycle log**
  - [x] Normalize cycle strings in `/src/calculator.js` & `/src/js/utils.js`
  - [x] Add non-ASCII token validation in `/src/services/nezha-sync.js`
  - [x] Verify fixes with test script

- [ ] **UI：使用 Tailwind 更新静态页面**
  - [x] 引入 Tailwind CDN
  - [x] 更新 `index.html` 样式
  - [ ] 验证页面显示与功能

## 📋 待办事项池

### 1. 代码重构与优化 (Refactoring)
- [ ] **重构：提取业务逻辑到 Service 层**
  - [ ] 创建 `src/services/` 目录
  - [ ] 提取 VPS CRUD 逻辑到 `vps.service.js`
  - [ ] 提取标签管理逻辑到 `tag.service.js`
  - [ ] 提取用户认证逻辑到 `auth.service.js`
- [ ] **优化：统一错误处理机制**
  - [ ] 创建全局错误处理中间件
  - [ ] 定义标准 API 错误响应格式
  - [ ] 替换所有 `try-catch` 块中的重复错误响应
- [x] **优化：统一日志系统** (已完成)
  - [x] 引入 `winston` 或 `pino` 日志库
  - [x] 替换所有 `console.log` 和 `console.error`
  - [ ] 实现请求日志记录中间件

### 2. 功能增强 (Enhancements)
- [ ] **增强：哪吒探针深度集成**
  - [ ] 支持更多探针数据的同步（如 CPU、内存使用率）
  - [ ] 实现探针状态变化的实时推送 (WebSocket/SSE)
- [ ] **增强：多用户支持准备**
  - [ ] 数据库模型支持多用户 (owner_id)
  - [ ] API 鉴权逻辑升级
- [ ] **增强：数据导入导出优化**
  - [ ] 支持 CSV 格式导入导出
  - [ ] 导入时的重复数据检测与处理

### 3. 测试与质量保证 (Testing)
- [ ] **测试：添加单元测试**
  - [ ] 配置 Jest 测试框架
  - [ ] 为核心计算逻辑 (`calculator.js`, `performance-calculator.js`) 添加测试
- [x] **测试：添加 API 集成测试**
  - [x] 使用 Supertest 测试关键 API 端点

### 4. 文档 (Documentation)
- [x] **文档：生成 API 文档**
  - [x] 集成 Swagger/OpenAPI
  - [x] 自动生成 `/api-docs` 页面

## ✅ 已完成
- [x] 拆分 server.js 路由到独立模块
- [x] 初始化项目结构
- [x] 实现基础 VPS 增删改查
- [x] 实现成本计算与分析
- [x] 集成哪吒探针基础同步
- [x] 实现 Telegram 通知系统
- [x] 安全：添加输入校验层 (zod)
