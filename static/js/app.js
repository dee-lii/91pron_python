/**
 * 91视频爬虫管理器 - 前端逻辑
 */

// ==================== 全局状态 ====================
let currentSite = '91pinse';
let siteConfigs = {};
let currentTasks = [];
let activeLogTaskId = null;
let logEventSource = null;

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadTasks();
    bindEvents();
});

// ==================== 加载配置 ====================
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        siteConfigs = await response.json();
        updateUI();
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

// ==================== 加载任务 ====================
async function loadTasks() {
    try {
        const response = await fetch('/api/tasks');
        currentTasks = await response.json();
        renderTasks();
    } catch (error) {
        console.error('加载任务失败:', error);
    }
}

// ==================== 绑定事件 ====================
function bindEvents() {
    // 网站选择
    document.querySelectorAll('.site-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.site-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSite = btn.dataset.site;
            updateUI();
        });
    });

    // 创建任务
    document.getElementById('create-task-btn').addEventListener('click', createTask);

    // 关闭日志
    document.getElementById('close-log-btn').addEventListener('click', closeLogPanel);
}

// ==================== 更新 UI ====================
function updateUI() {
    const config = siteConfigs[currentSite];
    if (!config) return;

    // 更新下载目录（显示网站子目录）
    const downloadDirInput = document.getElementById('download-dir');
    // 提取基础目录（去掉末尾的网站名子目录）
    let baseDir = downloadDirInput.value;
    // 移除末尾的 /网站名
    baseDir = baseDir.replace(/\/(91pinse|91porn|truvaze|xhotlist)$/, '');
    // 如果没有基础目录，使用默认值
    if (!baseDir || baseDir === '.') {
        baseDir = './downloads';
    }
    downloadDirInput.value = `${baseDir}/${currentSite}`;

    // 更新分类/标签显示
    const categorySection = document.getElementById('category-section');
    const tagSection = document.getElementById('tag-section');
    const durationSection = document.getElementById('duration-section');

    // 隐藏所有可选区域
    categorySection.style.display = 'none';
    tagSection.style.display = 'none';
    durationSection.style.display = 'none';

    // 根据网站显示对应区域
    if (currentSite === '91pinse') {
        categorySection.style.display = 'block';
        renderCategories(config.categories || []);
    } else if (currentSite === 'xhotlist') {
        tagSection.style.display = 'block';
        durationSection.style.display = 'block';
        renderTags(config.tags || []);
        renderDurationOptions(config.duration_options || {});
    }

    // 更新排序选项
    renderSortOptions(config.sort_options || {});

    // 更新时间选项
    renderTimeOptions(config.time_options || {});
}

// ==================== 渲染分类标签 ====================
function renderCategories(categories) {
    const container = document.getElementById('category-tags');
    container.innerHTML = categories.map(cat =>
        `<span class="category-tag" data-value="${cat}">${cat}</span>`
    ).join('');

    // 绑定点击事件
    container.querySelectorAll('.category-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            tag.classList.toggle('active');
        });
    });
}

// ==================== 渲染标签 ====================
function renderTags(tags) {
    const container = document.getElementById('tag-tags');
    const tagNames = {
        'anime': '动漫', 'jk': '女高中生', 'kyonyu': '丰胸', 'lolita': '少女系',
        'shaved': '光滑风格', 'beautiful-girl': '美少女', 'personal-filming': '私人拍摄',
        'hamedori': '自摄', 'sm': 'SM题材', 'small-breasts': '小胸', 'masturbation': '自我表达',
        'fellatio': '口部艺术', 'female-pervert': '大胆女性', 'outdoor': '户外场景',
        'shirouto': '业余', 'gay': '男同', 'big-sister': '姐姐', 'orgy': '群体场景',
        'uncensored': '未修饰', 'cosplay': '角色扮演', 'married-woman': '已婚女性',
        'gal': '时尚女孩', 'incest': '家庭主题', 'titjob': '胸部表演', 'voyeur': '隐藏拍摄',
        'cum-swallowing': '吞咽主题', 'massage': '按摩', 'anal': '背面主题',
        'bukkake': '泼洒艺术', 'facial': '面部艺术', 'creampie': '内部主题',
        'female-teacher': '女教师', 'molestation': '骚扰主题', 'handjob': '手部表演',
    };

    container.innerHTML = tags.map(tag =>
        `<span class="category-tag" data-value="${tag}">${tagNames[tag] || tag}</span>`
    ).join('');

    // 绑定点击事件（单选）
    container.querySelectorAll('.category-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            container.querySelectorAll('.category-tag').forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
        });
    });
}

// ==================== 渲染排序选项 ====================
function renderSortOptions(options) {
    const select = document.getElementById('sort-select');
    select.innerHTML = Object.entries(options).map(([value, label]) =>
        `<option value="${value}">${label}</option>`
    ).join('');
}

// ==================== 渲染时间选项 ====================
function renderTimeOptions(options) {
    const select = document.getElementById('time-select');
    select.innerHTML = Object.entries(options).map(([value, label]) =>
        `<option value="${value}">${label}</option>`
    ).join('');
}

// ==================== 渲染时长选项 ====================
function renderDurationOptions(options) {
    const select = document.getElementById('duration-select');
    select.innerHTML = Object.entries(options).map(([value, label]) =>
        `<option value="${value}">${label}</option>`
    ).join('');
}

// ==================== 创建任务 ====================
async function createTask() {
    const config = buildTaskConfig();

    // 验证
    if (currentSite === '91pinse' && !config.category) {
        alert('请选择或输入分类关键词');
        return;
    }

    if (currentSite === 'xhotlist' && !config.tag) {
        alert('请选择标签');
        return;
    }

    try {
        // 创建任务
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });

        if (!response.ok) {
            const error = await response.json();
            alert(error.error || '创建任务失败');
            return;
        }

        const task = await response.json();

        // 启动任务
        await fetch(`/api/tasks/${task.id}/start`, { method: 'POST' });

        // 刷新任务列表
        await loadTasks();

        // 打开日志面板
        openLogPanel(task.id);

    } catch (error) {
        console.error('创建任务失败:', error);
        alert('创建任务失败');
    }
}

// ==================== 构建任务配置 ====================
function buildTaskConfig() {
    const config = {
        site: currentSite,
        pages: parseInt(document.getElementById('pages-input').value) || 3,
        download: document.getElementById('download-checkbox').checked,
        download_dir: document.getElementById('download-dir').value || './downloads',
        proxy: document.getElementById('proxy-input').value || '',
    };

    // 最大视频数
    const maxVideos = parseInt(document.getElementById('max-videos-input').value);
    if (maxVideos > 0) {
        config.max_videos = maxVideos;
    }

    // 根据网站类型添加特定配置
    if (currentSite === '91pinse') {
        // 获取选中的分类
        const activeCategories = [];
        document.querySelectorAll('#category-tags .category-tag.active').forEach(tag => {
            activeCategories.push(tag.dataset.value);
        });
        const customCategory = document.getElementById('custom-category').value.trim();

        config.category = customCategory || activeCategories[0] || '';
        config.sort = document.getElementById('sort-select').value;
        config.time_filter = document.getElementById('time-select').value;

    } else if (currentSite === 'truvaze') {
        config.sort = document.getElementById('sort-select').value;
        config.time_filter = document.getElementById('time-select').value;

    } else if (currentSite === 'xhotlist') {
        const activeTag = document.querySelector('#tag-tags .category-tag.active');
        config.tag = activeTag ? activeTag.dataset.value : '';
        config.sort = document.getElementById('sort-select').value;
        config.time_filter = document.getElementById('time-select').value;
        config.duration = document.getElementById('duration-select').value;
    }

    return config;
}

// ==================== 渲染任务列表 ====================
function renderTasks() {
    const container = document.getElementById('tasks-list');

    if (currentTasks.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无任务</div>';
        return;
    }

    container.innerHTML = currentTasks.map(task => {
        const siteConfig = siteConfigs[task.site] || {};
        const progress = task.progress || {};

        // 计算进度百分比
        let progressPercent = 0;
        if (task.status === 'completed') {
            progressPercent = 100;
        } else if (progress.total_pages > 0) {
            progressPercent = (progress.current_page / progress.total_pages) * 100;
        }

        // 构建筛选条件描述
        const filters = [];
        if (task.category) filters.push(`分类: ${task.category}`);
        if (task.tag) filters.push(`标签: ${task.tag}`);
        if (task.sort && task.sort !== 'default' && task.sort !== 'latest') {
            filters.push(`排序: ${task.sort}`);
        }

        return `
            <div class="task-card" data-task-id="${task.id}">
                <div class="task-header">
                    <span class="task-site ${task.site}">${siteConfig.name || task.site}</span>
                    <span class="task-status ${task.status}">${getStatusText(task.status)}</span>
                </div>
                <div class="task-info">
                    <span>📋 ${filters.join(' | ') || '默认'}</span>
                    <span>📄 ${task.pages}页</span>
                    ${task.download ? '<span>⬇️ 下载</span>' : ''}
                </div>
                <div class="task-progress">
                    <div class="progress-text">
                        视频: ${progress.videos_found || 0} 个
                        ${task.download ? `| 下载: ${progress.videos_downloaded || 0} 个` : ''}
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progressPercent}%"></div>
                    </div>
                </div>
                <div class="task-actions">
                    ${getTaskActions(task)}
                </div>
            </div>
        `;
    }).join('');

    // 绑定任务操作事件
    bindTaskActions();
}

// ==================== 获取状态文本 ====================
function getStatusText(status) {
    const statusMap = {
        'created': '已创建',
        'running': '运行中',
        'completed': '已完成',
        'failed': '失败',
        'stopped': '已停止',
        'stopping': '停止中',
    };
    return statusMap[status] || status;
}

// ==================== 获取任务操作按钮 ====================
function getTaskActions(task) {
    let actions = '';

    if (task.status === 'created') {
        actions += `<button class="btn btn-small start-btn" data-id="${task.id}">▶ 启动</button>`;
    }

    if (task.status === 'running') {
        actions += `<button class="btn btn-small stop-btn" data-id="${task.id}">⏹ 停止</button>`;
    }

    actions += `<button class="btn btn-small log-btn" data-id="${task.id}">📝 日志</button>`;
    actions += `<button class="btn btn-small delete-btn" data-id="${task.id}">🗑 删除</button>`;

    return actions;
}

// ==================== 绑定任务操作事件 ====================
function bindTaskActions() {
    // 启动按钮
    document.querySelectorAll('.start-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const taskId = btn.dataset.id;
            await startTask(taskId);
        });
    });

    // 停止按钮
    document.querySelectorAll('.stop-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const taskId = btn.dataset.id;
            await stopTask(taskId);
        });
    });

    // 日志按钮
    document.querySelectorAll('.log-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const taskId = btn.dataset.id;
            openLogPanel(taskId);
        });
    });

    // 删除按钮
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const taskId = btn.dataset.id;
            if (confirm('确定要删除这个任务吗？')) {
                await deleteTask(taskId);
            }
        });
    });
}

// ==================== 启动任务 ====================
async function startTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/start`, { method: 'POST' });
        await loadTasks();
    } catch (error) {
        console.error('启动任务失败:', error);
    }
}

// ==================== 停止任务 ====================
async function stopTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/stop`, { method: 'POST' });
        await loadTasks();
    } catch (error) {
        console.error('停止任务失败:', error);
    }
}

// ==================== 删除任务 ====================
async function deleteTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        await loadTasks();
    } catch (error) {
        console.error('删除任务失败:', error);
    }
}

// ==================== 日志面板 ====================
function openLogPanel(taskId) {
    activeLogTaskId = taskId;
    const panel = document.getElementById('log-panel');
    const content = document.getElementById('log-content');

    panel.style.display = 'block';
    content.innerHTML = '<div class="log-entry">正在连接日志...</div>';

    // 关闭之前的连接
    if (logEventSource) {
        logEventSource.close();
    }

    // 建立 SSE 连接
    logEventSource = new EventSource(`/api/tasks/${taskId}/logs`);

    logEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.log) {
            const entry = document.createElement('div');
            entry.className = 'log-entry';

            // 根据内容设置样式
            if (data.log.includes('[ERROR]')) {
                entry.className += ' error';
            } else if (data.log.includes('完成')) {
                entry.className += ' success';
            }

            entry.textContent = data.log;
            content.appendChild(entry);

            // 自动滚动到底部
            content.scrollTop = content.scrollHeight;
        }

        if (data.status) {
            const entry = document.createElement('div');
            entry.className = 'log-entry success';
            entry.textContent = `任务状态: ${getStatusText(data.status)}`;
            content.appendChild(entry);

            logEventSource.close();
            loadTasks(); // 刷新任务列表
        }
    };

    logEventSource.onerror = () => {
        const entry = document.createElement('div');
        entry.className = 'log-entry error';
        entry.textContent = '日志连接断开';
        content.appendChild(entry);
        logEventSource.close();
    };
}

function closeLogPanel() {
    const panel = document.getElementById('log-panel');
    panel.style.display = 'none';

    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }

    activeLogTaskId = null;
}

// ==================== 定时刷新 ====================
setInterval(async () => {
    // 如果有运行中的任务，自动刷新
    const hasRunningTasks = currentTasks.some(t => t.status === 'running' || t.status === 'stopping');
    if (hasRunningTasks) {
        await loadTasks();
    }
}, 3000);
