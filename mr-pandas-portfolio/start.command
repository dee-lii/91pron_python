#!/bin/bash

# Mr. Panda's Portfolio - 一键启动脚本
# 双击此文件即可在浏览器中打开网站

cd "$(dirname "$0")"

echo "🐼 正在启动 Mr. Panda's Portfolio..."
echo "📍 项目路径: $(pwd)"
echo ""
echo "🌐 服务器将在 http://localhost:8000 启动"
echo "浏览器会自动打开网站"
echo ""
echo "⚠️  关闭此窗口将停止服务器"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 延迟 2 秒后自动在浏览器中打开
(sleep 2 && open http://localhost:8000) &

# 启动 Python 服务器
python3 -m http.server 8000
