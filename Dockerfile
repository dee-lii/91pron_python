FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 yt-dlp（用于 m3u8 视频下载）
RUN pip install --no-cache-dir yt-dlp

# 复制项目文件
COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# 创建下载目录
RUN mkdir -p /downloads

# 暴露端口
EXPOSE 8080

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["python3", "web_app.py"]
