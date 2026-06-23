@echo off
chcp 65001 >nul
title Mr. Panda's Portfolio - 本地服务器

echo 🐼 正在启动 Mr. Panda's Portfolio...
echo 📍 项目路径: %~dp0
echo.
echo 🌐 服务器将在 http://localhost:8000 启动
echo 浏览器会自动打开网站
echo.
echo ⚠️  关闭此窗口将停止服务器
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

cd /d "%~dp0"

:: 延迟 2 秒后自动在浏览器中打开
start "" /B cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: 启动 Python 服务器
python -m http.server 8000

pause
