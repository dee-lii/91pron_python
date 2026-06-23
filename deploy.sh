#!/bin/bash
# 91视频爬虫管理器 - VPS 部署脚本
# 用法: bash deploy.sh

set -e

echo "=========================================="
echo "  91视频爬虫管理器 - 自动部署"
echo "=========================================="

# 更新系统
echo "[1/6] 更新系统..."
apt-get update -y
apt-get upgrade -y

# 安装依赖
echo "[2/6] 安装系统依赖..."
apt-get install -y python3 python3-pip python3-venv ffmpeg

# 创建项目目录
echo "[3/6] 创建项目目录..."
mkdir -p /opt/spider-web
cd /opt/spider-web

# 创建虚拟环境
echo "[4/6] 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 安装 Python 依赖
echo "[5/6] 安装 Python 依赖..."
pip install flask requests beautifulsoup4 lxml pysocks yt-dlp

echo "[6/6] 部署完成！"
echo ""
echo "=========================================="
echo "  下一步操作："
echo "=========================================="
echo ""
echo "  1. 将项目文件上传到 /opt/spider-web/"
echo ""
echo "  2. 启动服务："
echo "     cd /opt/spider-web"
echo "     source venv/bin/activate"
echo "     nohup python3 web_app.py > /tmp/spider-web.log 2>&1 &"
echo ""
echo "  3. 访问: http://163.47.132.218:8080"
echo ""
echo "  4. 设置开机自启（可选）："
echo "     创建 /etc/systemd/system/spider-web.service"
echo ""
echo "=========================================="
