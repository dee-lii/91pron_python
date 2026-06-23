#!/usr/bin/env python3
"""
91视频爬虫管理器 - 网页版
提供 Web 界面管理多个视频网站的爬取和下载任务

使用方法:
    # 安装依赖
    pip install flask

    # 启动服务
    python3 web_app.py

    # 访问 http://localhost:5000
"""

import json
import os
import signal
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request, Response

# 导入爬虫模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# ==================== 配置 ====================
MAX_WORKERS = 3  # 最大并发任务数
DATA_DIR = os.environ.get("DATA_DIR", ".")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")

# ==================== 网站配置 ====================
SITE_CONFIGS = {
    "91pinse": {
        "name": "91PinSe",
        "url": "https://91pinse.com",
        "description": "91PinSe 视频网站",
        "categories": [
            "熟女", "巨乳", "阿姨", "内射", "高颜值", "少妇", "学生", "黑人",
            "绿帽", "3p", "偷情", "母狗", "人妻", "眼镜", "露脸", "黑丝",
            "大奶", "自慰", "电话", "女大", "双飞", "强推", "对白", "极品",
            "技师", "高潮", "足交", "肛交", "换妻", "调教", "口爆", "cos",
            "单男", "体育生", "后入", "打桩", "喷水", "骚话",
        ],
        "sort_options": {
            "latest": "最近更新",
            "hot": "热门视频",
            "score": "综合排序",
            "view": "播放最多",
            "like": "最多点赞",
        },
        "time_options": {
            "all": "全部时间",
            "today": "今天",
            "week": "本周",
            "month": "本月",
        },
        "module": "spider_91pinse",
        "class": "PinSe91Spider",
    },
    "91porn": {
        "name": "91Porn",
        "url": "https://91porn.com",
        "description": "91Porn 视频网站",
        "categories": [],  # 该网站无分类，主要是热门视频
        "sort_options": {},
        "time_options": {},
        "module": "spider_91porn",
        "class": "Porn91Spider",
    },
    "truvaze": {
        "name": "Truvaze",
        "url": "https://truvaze.com",
        "description": "Truvaze 视频网站",
        "categories": [],  # 该网站使用标签筛选
        "sort_options": {
            "favorite": "最多收藏",
            "views": "播放最多",
            "duration": "时长最长",
            "latest": "最新",
            "default": "默认",
        },
        "time_options": {
            "daily": "今日",
            "weekly": "本周",
            "monthly": "本月",
            "all": "全部",
        },
        "module": "spider_truvaze",
        "class": "TruvazeSpider",
    },
    "xhotlist": {
        "name": "XHotList",
        "url": "https://top.xhotlist.com",
        "description": "X(Twitter)热门成人短视频",
        "categories": [],  # 使用标签系统
        "tags": [
            "anime", "jk", "kyonyu", "lolita", "shaved", "beautiful-girl",
            "personal-filming", "hamedori", "sm", "small-breasts", "masturbation",
            "fellatio", "female-pervert", "outdoor", "shirouto", "gay",
            "big-sister", "orgy", "uncensored", "cosplay", "married-woman",
            "gal", "incest", "titjob", "voyeur", "cum-swallowing", "massage",
            "anal", "bukkake", "facial", "creampie", "female-teacher",
            "molestation", "handjob",
        ],
        "sort_options": {
            "default": "播放最多",
            "new": "最新",
            "duration": "时长最长",
            "old": "最早",
        },
        "time_options": {
            "all": "全部",
            "day": "今日热门",
            "week": "本周热门",
            "month": "本月热门",
            "total": "总热门",
        },
        "duration_options": {
            "all": "全部时长",
            "short": "5分钟内",
            "medium": "5-30分钟",
            "long": "30分钟以上",
        },
        "module": "spider_xhotlist",
        "class": "XHotListSpider",
    },
}

# ==================== 任务管理 ====================
class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.tasks: Dict[dict] = {}
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.lock = threading.Lock()
        self._load_tasks()

    def _load_tasks(self):
        """从文件加载任务"""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for task in data:
                            if task.get("id"):
                                # 重置运行中的任务状态
                                if task.get("status") == "running":
                                    task["status"] = "stopped"
                                self.tasks[task["id"]] = task
                print(f"[INFO] 加载了 {len(self.tasks)} 个任务")
            except Exception as e:
                print(f"[WARN] 加载任务失败: {e}")

    def _save_tasks(self):
        """保存任务到文件"""
        try:
            tasks_list = list(self.tasks.values())
            with open(TASKS_FILE, "w") as f:
                json.dump(tasks_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 保存任务失败: {e}")

    def create_task(self, config: dict) -> dict:
        """创建新任务"""
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "site": config.get("site"),
            "category": config.get("category"),
            "tag": config.get("tag"),
            "sort": config.get("sort", "default"),
            "time_filter": config.get("time_filter", "all"),
            "duration": config.get("duration", "all"),
            "pages": config.get("pages", 3),
            "max_videos": config.get("max_videos"),
            "download": config.get("download", False),
            "download_dir": config.get("download_dir", "./downloads"),
            "proxy": config.get("proxy", ""),
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {
                "current_page": 0,
                "total_pages": 0,
                "videos_found": 0,
                "videos_downloaded": 0,
                "download_failed": 0,
            },
            "logs": [],
        }

        with self.lock:
            self.tasks[task_id] = task
            self._save_tasks()

        return task

    def start_task(self, task_id: str) -> bool:
        """启动任务"""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            if task["status"] == "running":
                return False
            task["status"] = "running"
            task["started_at"] = datetime.now().isoformat()
            self._save_tasks()

        # 提交到线程池
        self.executor.submit(self._run_task, task_id)
        return True

    def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            task["status"] = "stopping"
            self._save_tasks()
        return True

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                self._save_tasks()
                return True
        return False

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取单个任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务"""
        return list(self.tasks.values())

    def add_log(self, task_id: str, message: str):
        """添加日志"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] {message}"
                task["logs"].append(log_entry)
                # 只保留最近 100 条日志
                if len(task["logs"]) > 100:
                    task["logs"] = task["logs"][-100:]

    def update_progress(self, task_id: str, **kwargs):
        """更新进度"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task["progress"].update(kwargs)

    def _run_task(self, task_id: str):
        """运行爬虫任务"""
        task = self.tasks.get(task_id)
        if not task:
            return

        site = task["site"]
        site_config = SITE_CONFIGS.get(site)
        if not site_config:
            self.add_log(task_id, f"未知网站: {site}")
            task["status"] = "failed"
            self._save_tasks()
            return

        try:
            # 动态导入爬虫模块
            module_name = site_config["module"]
            class_name = site_config["class"]

            # 导入模块
            import importlib
            module = importlib.import_module(module_name)
            spider_class = getattr(module, class_name)

            # 构建爬虫参数
            spider_kwargs = {
                "output_file": f"{site}_videos.json",
                "download": task["download"],
                "download_dir": task["download_dir"],
                "resume": True,
            }

            # 根据网站类型添加参数
            if site == "91pinse":
                spider_kwargs["category"] = task.get("category")
                spider_kwargs["sort"] = task.get("sort", "latest")
                spider_kwargs["time_filter"] = task.get("time_filter", "all")
            elif site == "truvaze":
                spider_kwargs["sort"] = task.get("sort", "default")
                spider_kwargs["period"] = task.get("time_filter", "all")
            elif site == "xhotlist":
                spider_kwargs["tag"] = task.get("tag")
                spider_kwargs["period"] = task.get("time_filter", "all")
                spider_kwargs["sort"] = task.get("sort", "default")
                spider_kwargs["duration"] = task.get("duration", "all")

            # 设置代理
            if task.get("proxy"):
                proxy = task["proxy"]
                if proxy.startswith("socks"):
                    os.environ["ALL_PROXY"] = proxy
                else:
                    os.environ["HTTP_PROXY"] = proxy
                    os.environ["HTTPS_PROXY"] = proxy

            # 创建爬虫实例
            spider = spider_class(**spider_kwargs)

            # 自定义日志输出（实时更新进度）
            original_print = print
            def custom_print(*args, **kwargs):
                message = " ".join(str(a) for a in args)
                if message.startswith("[INFO]") or message.startswith("[ERROR]") or message.startswith("[WARN]"):
                    self.add_log(task_id, message)

                    # 从日志中解析进度信息
                    if "新增视频" in message:
                        self.update_progress(
                            task_id,
                            videos_found=len(spider.videos),
                        )
                    elif "下载完成" in message:
                        self.update_progress(
                            task_id,
                            videos_downloaded=spider.download_count,
                        )
                    elif "下载失败" in message:
                        self.update_progress(
                            task_id,
                            download_failed=spider.download_failed,
                        )

                original_print(*args, **kwargs)

            # 替换 print 函数
            import builtins
            builtins.print = custom_print

            # 运行爬虫
            self.add_log(task_id, f"开始爬取 {site_config['name']}...")
            spider.crawl(
                max_page=task.get("pages"),
                target_new=task.get("max_videos"),
            )

            # 最终更新进度
            self.update_progress(
                task_id,
                videos_found=len(spider.videos),
                videos_downloaded=spider.download_count,
                download_failed=spider.download_failed,
            )

            # 恢复原始 print
            builtins.print = original_print

            # 检查是否被停止
            if task["status"] == "stopping":
                task["status"] = "stopped"
                self.add_log(task_id, "任务已停止")
            else:
                task["status"] = "completed"
                self.add_log(task_id, "任务完成")

        except Exception as e:
            self.add_log(task_id, f"任务失败: {str(e)}")
            task["status"] = "failed"

        finally:
            task["completed_at"] = datetime.now().isoformat()
            self._save_tasks()


# 全局任务管理器
task_manager = TaskManager()


# ==================== 路由 ====================

@app.route("/")
def index():
    """主页"""
    return render_template("index.html", sites=SITE_CONFIGS)


@app.route("/api/config")
def get_config():
    """获取所有网站配置"""
    return jsonify(SITE_CONFIGS)


@app.route("/api/config/<site>")
def get_site_config(site):
    """获取单个网站配置"""
    config = SITE_CONFIGS.get(site)
    if config:
        return jsonify(config)
    return jsonify({"error": "未知网站"}), 404


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    """获取所有任务"""
    tasks = task_manager.get_all_tasks()
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """创建新任务"""
    data = request.json
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    site = data.get("site")
    if site not in SITE_CONFIGS:
        return jsonify({"error": "未知网站"}), 400

    task = task_manager.create_task(data)
    return jsonify(task), 201


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """获取单个任务"""
    task = task_manager.get_task(task_id)
    if task:
        return jsonify(task)
    return jsonify({"error": "任务不存在"}), 404


@app.route("/api/tasks/<task_id>/start", methods=["POST"])
def start_task(task_id):
    """启动任务"""
    if task_manager.start_task(task_id):
        return jsonify({"message": "任务已启动"})
    return jsonify({"error": "无法启动任务"}), 400


@app.route("/api/tasks/<task_id>/stop", methods=["POST"])
def stop_task(task_id):
    """停止任务"""
    if task_manager.stop_task(task_id):
        return jsonify({"message": "正在停止任务"})
    return jsonify({"error": "无法停止任务"}), 400


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """删除任务"""
    if task_manager.delete_task(task_id):
        return jsonify({"message": "任务已删除"})
    return jsonify({"error": "无法删除任务"}), 400


@app.route("/api/tasks/<task_id>/logs")
def get_task_logs(task_id):
    """获取任务日志（SSE）"""
    def generate():
        last_count = 0
        while True:
            task = task_manager.get_task(task_id)
            if not task:
                break

            logs = task.get("logs", [])
            if len(logs) > last_count:
                for log in logs[last_count:]:
                    yield f"data: {json.dumps({'log': log})}\n\n"
                last_count = len(logs)

            # 检查任务是否结束
            if task.get("status") in ["completed", "failed", "stopped"]:
                yield f"data: {json.dumps({'status': task['status']})}\n\n"
                break

            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/tasks/<task_id>/status")
def get_task_status(task_id):
    """获取任务状态（SSE）"""
    def generate():
        while True:
            task = task_manager.get_task(task_id)
            if not task:
                break

            yield f"data: {json.dumps(task, ensure_ascii=False)}\n\n"

            # 检查任务是否结束
            if task.get("status") in ["completed", "failed", "stopped"]:
                break

            time.sleep(1)

    return Response(generate(), mimetype="text/event-stream")


# ==================== 主程序 ====================

def main():
    """启动 Web 服务"""
    print("=" * 60)
    print("  91视频爬虫管理器 - 网页版")
    print("=" * 60)
    print(f"\n  访问地址: http://localhost:8080")
    print(f"  最大并发任务: {MAX_WORKERS}")
    print(f"\n  按 Ctrl+C 停止服务")
    print("=" * 60)

    # 处理中断信号
    def signal_handler(sig, frame):
        print("\n[INFO] 正在停止服务...")
        task_manager.executor.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动 Flask
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
