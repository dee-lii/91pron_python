    // ==================== 应用逻辑 ====================

    function showPage(pageId) {
      ['init-page', 'login-page', 'public-page', 'admin-page'].forEach(id => {
        document.getElementById(id).style.display = id === pageId ? (id.includes('page') && !id.includes('admin') && !id.includes('public') ? 'flex' : 'block') : 'none';
      });
      if (pageId === 'init-page' || pageId === 'login-page') {
        document.getElementById(pageId).style.display = 'flex';
      }
    }

    async function checkAuthAndRoute() {
      const hash = window.location.hash || '#/';
      
      try {
        const statusRes = await ApiService.authStatus();
        const statusData = await statusRes.json();
        
        if (!statusData.data.initialized) {
          showPage('init-page');
          return;
        }
        
        if (hash === '#/login') {
          showPage('login-page');
          return;
        }
        
        if (hash.startsWith('#/admin')) {
          const token = getToken();
          if (!token) {
            window.location.hash = '#/login';
            return;
          }
          
          const meRes = await ApiService.authMe();
          if (!meRes.ok) {
            clearToken();
            window.location.hash = '#/login';
            return;
          }
          
          const meData = await meRes.json();
          document.getElementById('current-user').textContent = `👤 ${meData.data.username}`;
          showPage('admin-page');
          await initAdminPage();
          
          const tabMatch = hash.match(/#\/admin\/(\w+)/);
          if (tabMatch && tabMatch[1]) {
            switchTab(tabMatch[1], false);
          }
          return;
        }
        
        showPage('public-page');
        loadPublicData();
        
      } catch (error) {
        console.error('Auth check failed:', error);
        showPage('public-page');
        loadPublicData();
      }
    }

    async function handleInit(event) {
      event.preventDefault();
      const username = document.getElementById('init-username').value;
      const password = document.getElementById('init-password').value;
      const confirm = document.getElementById('init-password-confirm').value;
      const errorDiv = document.getElementById('init-error');
      
      if (password !== confirm) {
        errorDiv.textContent = '两次输入的密码不一致';
        return;
      }
      
      try {
        const res = await ApiService.authInit({ username, password });
        
        const data = await res.json();
        if (!data.success) {
          errorDiv.textContent = data.error;
          return;
        }
        
        window.location.hash = '#/login';
      } catch (error) {
        errorDiv.textContent = '初始化失败: ' + error.message;
      }
    }

    async function handleLogin(event) {
      event.preventDefault();
      const username = document.getElementById('login-username').value;
      const password = document.getElementById('login-password').value;
      const errorDiv = document.getElementById('login-error');
      
      try {
        const res = await ApiService.authLogin({ username, password });
        
        const data = await res.json();
        if (!data.success) {
          errorDiv.textContent = data.error;
          return;
        }
        
        setToken(data.data.token);
        window.location.hash = '#/admin';
      } catch (error) {
        errorDiv.textContent = '登录失败: ' + error.message;
      }
    }

    function handleLogout() {
      clearToken();
      window.location.hash = '#/';
    }

    function goToLogin() {
      window.location.hash = '#/login';
    }

    async function handleChangePassword(event) {
      event.preventDefault();
      const oldPassword = document.getElementById('old-password').value;
      const newPassword = document.getElementById('new-password').value;
      const confirm = document.getElementById('new-password-confirm').value;
      const errorDiv = document.getElementById('password-error');
      const successDiv = document.getElementById('password-success');
      
      errorDiv.textContent = '';
      successDiv.textContent = '';
      
      if (newPassword !== confirm) {
        errorDiv.textContent = '两次输入的新密码不一致';
        return;
      }
      
      try {
        const res = await ApiService.changePassword({ oldPassword, newPassword });
        
        const data = await res.json();
        if (!data.success) {
          errorDiv.textContent = data.error;
          return;
        }
        
        successDiv.textContent = '密码修改成功！';
        document.getElementById('old-password').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('new-password-confirm').value = '';
      } catch (error) {
        errorDiv.textContent = '修改失败: ' + error.message;
      }
    }

    async function loadPublicData() {
      try {
        const [statsRes, serversRes, rankingsRes] = await Promise.all([
          ApiService.publicStats(),
          ApiService.publicServers(),
          ApiService.publicRankings()
        ]);
        
        const [statsData, serversData, rankingsData] = await Promise.all([
          statsRes.json(),
          serversRes.json(),
          rankingsRes.json()
        ]);
        

        if (statsData.success) {
          const stats = statsData.data;
          document.getElementById('public-stats').innerHTML = `
            <div class="stat-card"><div class="stat-value">${stats.totalServers || 0}</div><div class="stat-label">服务器总数</div></div>
            <div class="stat-card"><div class="stat-value" style="color: var(--success);">${stats.onlineServers || 0}</div><div class="stat-label">在线</div></div>
            <div class="stat-card"><div class="stat-value" style="color: var(--danger);">${stats.offlineServers || 0}</div><div class="stat-label">离线</div></div>
            <div class="stat-card"><div class="stat-value" style="color: var(--warning);">${stats.expiringServers || 0}</div><div class="stat-label">即将到期</div></div>
          `;
        }
        
        if (serversData.success) {
          const servers = serversData.data;
          if (servers.length === 0) {
            document.getElementById('public-server-list').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📦</div><div class="empty-state-title">暂无服务器</div></div>';
          } else {
            document.getElementById('public-server-list').innerHTML = servers.map(s => `
              <div class="vps-card">
                <div class="vps-card-header">
                  <div>
                    <div class="vps-name">${s.name}</div>
                    <div class="vps-provider">${s.location || '未知位置'}</div>
                  </div>
                  <span class="badge ${s.online ? 'badge-success' : 'badge-danger'}">${s.online ? '在线' : '离线'}</span>
                </div>
                <div class="vps-info">
                  <div class="vps-info-item"><span class="vps-info-label">剩余天数</span><span class="vps-info-value">${(s.remainingDays === null || s.remainingDays === undefined) ? '-' : (s.remainingDays <= 0 ? '已过期' : s.remainingDays + ' 天')}</span></div>
                  <div class="vps-info-item"><span class="vps-info-label">到期日期</span><span class="vps-info-value">${s.expiryDate || '-'}</span></div>
                  ${s.specs ? `<div class="vps-info-item"><span class="vps-info-label">配置</span><span class="vps-info-value">${s.specs.cpu?.cores || '-'}核 / ${s.specs.memory?.size || '-'}G / ${s.specs.storage?.size || '-'}G</span></div>` : ''}
                  ${s.nezha ? `<div class="vps-info-item"><span class="vps-info-label">负载</span><span class="vps-info-value">CPU ${Number.isFinite(Number(s.nezha.cpuUsage)) ? Number(s.nezha.cpuUsage).toFixed(1) : '-'}% / 内存 ${s.nezha.memUsage || '-'}%</span></div>` : ''}
                </div>
                <div class="vps-progress">
                  <div class="progress-label"><span>使用进度</span><span>${(s.usageRate === null || s.usageRate === undefined) ? '-' : (s.usageRate > 100 ? '已过期' : s.usageRate + '%')}</span></div>
                  <div class="progress-bar"><div class="progress-fill" style="width: ${Math.min(s.usageRate || 0, 100)}%"></div></div>
                </div>
              </div>
            `).join('');
          }
        }
        
        if (rankingsData.success && rankingsData.data.length > 0) {
          document.getElementById('public-rankings').innerHTML = `
            <table style="width: 100%; border-collapse: separate; border-spacing: 0 8px;">
              <thead>
                <tr>
                  <th style="padding: 12px; text-align: left; color: var(--text-light); font-weight: 600; font-size: 13px; text-transform: uppercase;">排名</th>
                  <th style="padding: 12px; text-align: left; color: var(--text-light); font-weight: 600; font-size: 13px; text-transform: uppercase;">名称</th>
                  <th style="padding: 12px; text-align: left; color: var(--text-light); font-weight: 600; font-size: 13px; text-transform: uppercase;">位置</th>
                  <th style="padding: 12px; text-align: center; color: var(--text-light); font-weight: 600; font-size: 13px; text-transform: uppercase;">综合评分</th>
                </tr>
              </thead>
              <tbody>
                ${rankingsData.data.map(r => `
                  <tr style="background: rgba(255,255,255,0.5); transition: all 0.2s;">
                    <td style="padding: 16px; border-radius: 8px 0 0 8px;">${r.rank === 1 ? '🥇' : r.rank === 2 ? '🥈' : r.rank === 3 ? '🥉' : r.rank}</td>
                    <td style="padding: 16px; font-weight: 600;">${r.name}</td>
                    <td style="padding: 16px;">${r.location || '-'}</td>
                    <td style="padding: 16px; text-align: center; border-radius: 0 8px 8px 0;"><span class="badge badge-primary">${Number.isFinite(Number(r.overallScore)) ? Number(r.overallScore).toFixed(1) : '-'}</span></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          `;
        } else {
          document.getElementById('public-rankings').innerHTML = '<div class="empty-state"><div class="empty-state-title" style="font-size: 16px;">暂无排行数据</div></div>';
        }
        
      } catch (error) {
        console.error('Load public data failed:', error);
      }
    }

    async function initAdminPage() {
      await loadVpsList();
      renderVpsList();
      loadCPUModels();
      loadNezhaConfig();
    }

    window.addEventListener('hashchange', checkAuthAndRoute);
    window.addEventListener('load', checkAuthAndRoute);

    // ==================== 数据管理 ====================

    let vpsList = [];
    let currentEditId = null;
    let charts = {}; // 存储图表实例

    /**
     * 加载 VPS 列表（从后端 API）
     */
    async function loadVpsList() {
      try {
        const response = await ApiService.getVpsList();
        if (response.ok) {
          const data = await response.json();
          if (data.success) {
            vpsList = data.data || [];
          }
        }
      } catch (e) {
        console.error('加载 VPS 列表失败:', e);
        vpsList = [];
      }
    }

    /**
     * 保存 VPS 列表（到后端 API）
     */
    async function saveVpsList() {
      try {
        const response = await ApiService.saveVpsList(vpsList);
        if (!response.ok) {
          const data = await response.json();
          console.error('保存 VPS 列表失败:', data.error);
        }
      } catch (e) {
        console.error('保存 VPS 列表失败:', e);
      }
    }

    /**
     * 渲染 VPS 列表
     */
    function renderVpsList() {
      const container = document.getElementById('vps-list');

      if (vpsList.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📦</div>
            <div class="empty-state-title">还没有 VPS</div>
            <div class="empty-state-description">点击右上角"添加 VPS"按钮开始管理您的服务器</div>
          </div>
        `;
        return;
      }

      container.innerHTML = vpsList.map(vps => {
        const totalDays = getDaysByCycle(vps.cycle);
        const usedDays = calculateUsedDays(vps.purchaseDate);
        
        const needsPriceInfo = !vps.price || vps.price <= 0;
        
        let result, statusBadge;
        if (needsPriceInfo) {
          result = { remainingValue: '-', remainingDays: '-', usageRate: 0 };
          statusBadge = '<span class="badge badge-warning">需补充价格</span>';
        } else {
          result = calculateRemainingValue(vps.price, totalDays, usedDays);
          if (result.usageRate < 30) {
            statusBadge = '<span class="badge badge-success">新购</span>';
          } else if (result.usageRate < 70) {
            statusBadge = '<span class="badge badge-primary">使用中</span>';
          } else {
            statusBadge = '<span class="badge badge-danger">即将到期</span>';
          }
        }

        const nezhaInfo = vps.nezha ? `
          <div class="vps-info-item">
            <span class="vps-info-label">状态</span>
            <span class="vps-info-value">${vps.nezha.online ? '🟢 在线' : '🔴 离线'}</span>
          </div>
          ${vps.location ? `<div class="vps-info-item"><span class="vps-info-label">位置</span><span class="vps-info-value">${vps.location}</span></div>` : ''}
          ${vps.ip ? `<div class="vps-info-item"><span class="vps-info-label">IP</span><span class="vps-info-value">${vps.ip}</span></div>` : ''}
        ` : '';

        return `
          <div class="vps-card">
            <div class="vps-card-header">
              <div>
                <div class="vps-name">${vps.name}</div>
                <div class="vps-provider">${vps.provider}</div>
              </div>
              <div class="vps-actions">
                <button class="btn btn-icon" onclick="editVps('${vps.id}')" title="编辑">✏️</button>
                <button class="btn btn-icon" onclick="deleteVps('${vps.id}')" title="删除">🗑️</button>
              </div>
            </div>

            <div class="vps-info">
              <div class="vps-info-item">
                <span class="vps-info-label">购买价格</span>
                <span class="vps-info-value">${needsPriceInfo ? '待补充' : vps.currency + ' ' + vps.price}</span>
              </div>
              <div class="vps-info-item">
                <span class="vps-info-label">付款周期</span>
                <span class="vps-info-value">${getCycleName(vps.cycle)}</span>
              </div>
              <div class="vps-info-item">
                <span class="vps-info-label">剩余价值</span>
                <span class="vps-info-value">${needsPriceInfo ? '-' : (result.remainingValue < 0 ? '已过期' : vps.currency + ' ' + result.remainingValue)}</span>
              </div>
              <div class="vps-info-item">
                <span class="vps-info-label">剩余天数</span>
                <span class="vps-info-value">${needsPriceInfo ? '-' : (result.remainingDays < 0 ? '已过期' : result.remainingDays + ' 天')}</span>
              </div>
              ${nezhaInfo}
            </div>

            <div class="vps-progress">
              <div class="progress-label">
                <span>使用进度 ${statusBadge}</span>
                <span>${needsPriceInfo ? '-' : (result.usageRate > 100 ? '已过期' : result.usageRate + '%')}</span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill" style="width: ${Math.min(result.usageRate, 100)}%"></div>
              </div>
            </div>

            ${vps.notes ? `<div style="margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--border-color); font-size: 13px; color: var(--text-light); line-height: 1.5;">📝 ${vps.notes}</div>` : ''}
          </div>
        `;
      }).join('');

      updateTrendVpsSelect();
    }

    function updateTrendVpsSelect() {
      const select = document.getElementById('trend-vps-select');
      if (!select) return;
      select.innerHTML = '<option value="">请选择一个 VPS</option>' +
        vpsList.map(vps => `<option value="${vps.id}">${vps.name}</option>`).join('');
    }

    function updateTrendChart() {
      const select = document.getElementById('trend-vps-select');
      const vpsId = select?.value;
      const canvas = document.getElementById('lineChart');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');

      if (!vpsId) {
        if (charts.line) {
          charts.line.destroy();
          charts.line = null;
        }
        return;
      }

      const vps = vpsList.find(v => v.id === vpsId);
      if (!vps) return;

      const totalDays = getDaysByCycle(vps.cycle);
      const currentUsedDays = calculateUsedDays(vps.purchaseDate);
      const currencySymbol = { CNY: '¥', USD: '$', EUR: '€', GBP: '£', JPY: '¥' }[vps.currency] || vps.currency;

      const points = 30;
      const step = Math.max(1, Math.ceil(totalDays / points));
      const labels = [];
      const values = [];

      for (let i = 0; i <= totalDays; i += step) {
        const result = calculateRemainingValue(vps.price, totalDays, i);
        labels.push(`第 ${i} 天`);
        values.push(result.remainingValue);
      }

      if (charts.line) {
        charts.line.destroy();
      }

      charts.line = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '剩余价值',
            data: values,
            borderColor: 'rgba(102, 126, 234, 1)',
            backgroundColor: 'rgba(102, 126, 234, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.4
          }, {
            label: '当前位置',
            data: labels.map((_, i) => {
              const dayNum = i * step;
              return Math.abs(dayNum - currentUsedDays) <= step / 2 ? 
                calculateRemainingValue(vps.price, totalDays, currentUsedDays).remainingValue : null;
            }),
            borderColor: 'rgba(245, 101, 101, 1)',
            backgroundColor: 'rgba(245, 101, 101, 1)',
            pointRadius: labels.map((_, i) => {
              const dayNum = i * step;
              return Math.abs(dayNum - currentUsedDays) <= step / 2 ? 8 : 0;
            }),
            pointStyle: 'circle',
            showLine: false
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function(context) {
                  if (context.datasetIndex === 1) {
                    return `当前: ${currencySymbol}${context.parsed.y.toFixed(2)}`;
                  }
                  return `剩余价值: ${currencySymbol}${context.parsed.y.toFixed(2)}`;
                }
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                callback: function(value) { return currencySymbol + value; }
              }
            }
          }
        }
      });
    }

    function sortVps(sortBy) {
      vpsList.sort((a, b) => {
        if (sortBy === 'remainingValue') {
          const aResult = calculateRemainingValue(a.price, getDaysByCycle(a.cycle), calculateUsedDays(a.purchaseDate));
          const bResult = calculateRemainingValue(b.price, getDaysByCycle(b.cycle), calculateUsedDays(b.purchaseDate));
          return bResult.remainingValue - aResult.remainingValue;
        } else if (sortBy === 'usageRate') {
          const aResult = calculateRemainingValue(a.price, getDaysByCycle(a.cycle), calculateUsedDays(a.purchaseDate));
          const bResult = calculateRemainingValue(b.price, getDaysByCycle(b.cycle), calculateUsedDays(b.purchaseDate));
          return bResult.usageRate - aResult.usageRate;
        } else if (sortBy === 'purchaseDate') {
          return new Date(b.purchaseDate) - new Date(a.purchaseDate);
        } else if (sortBy === 'provider') {
          return a.provider.localeCompare(b.provider);
        }
        return 0;
      });
      renderVpsList();
    }

    /**
     * 打开添加 VPS 模态框
     */
    function openAddVpsModal() {
      currentEditId = null;
      document.getElementById('modal-title').textContent = '添加 VPS';
      document.getElementById('vps-name').value = '';
      document.getElementById('vps-provider').value = '';
      document.getElementById('vps-price').value = '';
      document.getElementById('vps-currency').value = 'CNY';
      document.getElementById('vps-cycle').value = 'yearly';
      document.getElementById('vps-purchase-date').value = new Date().toISOString().split('T')[0];
      document.getElementById('vps-notes').value = '';

      // 清空 specs 字段
      document.getElementById('vps-cpu-model').value = '';
      document.getElementById('vps-cpu-cores').value = '';
      document.getElementById('vps-memory-size').value = '';
      document.getElementById('vps-memory-type').value = '';
      document.getElementById('vps-storage-size').value = '';
      document.getElementById('vps-storage-type').value = '';
      document.getElementById('vps-network-bandwidth').value = '';
      document.getElementById('vps-network-traffic').value = '';

      document.getElementById('vps-modal').classList.add('active');

      // 加载 CPU 型号列表
      loadCPUModels();
    }

    /**
     * 编辑 VPS
     */
    function editVps(id) {
      const vps = vpsList.find(v => v.id === id);
      if (!vps) return;

      currentEditId = id;
      document.getElementById('modal-title').textContent = '编辑 VPS';
      document.getElementById('vps-name').value = vps.name || '';
      document.getElementById('vps-provider').value = vps.provider || '';
      document.getElementById('vps-price').value = vps.price || '';
      document.getElementById('vps-currency').value = vps.currency || 'CNY';
      document.getElementById('vps-cycle').value = vps.cycle || 'monthly';
      document.getElementById('vps-purchase-date').value = vps.purchaseDate || '';
      document.getElementById('vps-notes').value = vps.notes || '';

      // 填充 specs 字段
      if (vps.specs) {
        document.getElementById('vps-cpu-model').value = vps.specs.cpu?.model || '';
        document.getElementById('vps-cpu-cores').value = vps.specs.cpu?.cores || '';
        document.getElementById('vps-memory-size').value = vps.specs.memory?.size || '';
        document.getElementById('vps-memory-type').value = vps.specs.memory?.type || '';
        document.getElementById('vps-storage-size').value = vps.specs.storage?.size || '';
        document.getElementById('vps-storage-type').value = vps.specs.storage?.type || '';
        document.getElementById('vps-network-bandwidth').value = vps.specs.network?.bandwidth || '';
        document.getElementById('vps-network-traffic').value = vps.specs.network?.traffic || '';
      } else {
        document.getElementById('vps-cpu-model').value = '';
        document.getElementById('vps-cpu-cores').value = '';
        document.getElementById('vps-memory-size').value = '';
        document.getElementById('vps-memory-type').value = '';
        document.getElementById('vps-storage-size').value = '';
        document.getElementById('vps-storage-type').value = '';
        document.getElementById('vps-network-bandwidth').value = '';
        document.getElementById('vps-network-traffic').value = '';
      }

      document.getElementById('vps-modal').classList.add('active');

      // 加载 CPU 型号列表
      loadCPUModels();
    }

    /**
     * 删除 VPS
     */
    async function deleteVps(id) {
      if (!confirm('确定要删除这个 VPS 吗？')) return;

      vpsList = vpsList.filter(v => v.id !== id);
      await saveVpsList();
      renderVpsList();
    }

    /**
     * 保存 VPS
     */
    async function saveVps() {
      const name = document.getElementById('vps-name').value.trim();
      const provider = document.getElementById('vps-provider').value.trim();
      const price = parseFloat(document.getElementById('vps-price').value);
      const currency = document.getElementById('vps-currency').value;
      const cycle = document.getElementById('vps-cycle').value;
      const purchaseDate = document.getElementById('vps-purchase-date').value;
      const notes = document.getElementById('vps-notes').value.trim();

      // 验证
      if (!name || !provider || !price || !purchaseDate) {
        showToast('请填写所有必填项', 'warning');
        return;
      }

      if (price <= 0) {
        showToast('价格必须大于 0', 'warning');
        return;
      }

      // 收集 specs 数据（可选）
      const cpuModel = document.getElementById('vps-cpu-model').value.trim();
      const cpuCores = parseInt(document.getElementById('vps-cpu-cores').value);
      const memorySize = parseFloat(document.getElementById('vps-memory-size').value);
      const memoryType = document.getElementById('vps-memory-type').value;
      const storageSize = parseInt(document.getElementById('vps-storage-size').value);
      const storageType = document.getElementById('vps-storage-type').value;
      const networkBandwidth = parseInt(document.getElementById('vps-network-bandwidth').value);
      const networkTraffic = parseInt(document.getElementById('vps-network-traffic').value);

      const vpsData = {
        id: currentEditId || Date.now().toString(),
        name,
        provider,
        price,
        currency,
        cycle,
        purchaseDate,
        notes
      };

      // 如果填写了 specs，添加到数据中
      if (cpuModel || cpuCores || memorySize || storageSize || networkBandwidth) {
        vpsData.specs = {};

        if (cpuModel || cpuCores) {
          vpsData.specs.cpu = {};
          if (cpuModel) vpsData.specs.cpu.model = cpuModel;
          if (cpuCores) vpsData.specs.cpu.cores = cpuCores;
        }

        if (memorySize) {
          vpsData.specs.memory = { size: memorySize };
          if (memoryType) vpsData.specs.memory.type = memoryType;
        }

        if (storageSize) {
          vpsData.specs.storage = { size: storageSize };
          if (storageType) vpsData.specs.storage.type = storageType;
        }

        if (networkBandwidth || networkTraffic) {
          vpsData.specs.network = {};
          if (networkBandwidth) vpsData.specs.network.bandwidth = networkBandwidth;
          if (networkTraffic) vpsData.specs.network.traffic = networkTraffic;
        }
      }

      // 保留现有的 nezha 数据（如果有）
      if (currentEditId) {
        const existing = vpsList.find(v => v.id === currentEditId);
        if (existing && existing.nezha) {
          vpsData.nezha = existing.nezha;
        }
      }

      if (currentEditId) {
        const index = vpsList.findIndex(v => v.id === currentEditId);
        vpsList[index] = vpsData;
      } else {
        vpsList.push(vpsData);
      }

      await saveVpsList();
      closeVpsModal();
      renderVpsList();
    }

    /**
     * 关闭 VPS 模态框
     */
    function closeVpsModal() {
      document.getElementById('vps-modal').classList.remove('active');
    }

    /**
     * 导出数据
     */
    function exportData() {
      const dataStr = JSON.stringify(vpsList, null, 2);
      const dataBlob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `vps-data-${new Date().toISOString().split('T')[0]}.json`;
      link.click();
      URL.revokeObjectURL(url);
    }

    /**
     * 导入数据
     */
    function importData() {
      document.getElementById('import-modal').classList.add('active');
    }

    /**
     * 确认导入
     */
    function confirmImport() {
      const fileInput = document.getElementById('import-file');
      const file = fileInput.files[0];

      if (!file) {
        showToast('请选择文件', 'warning');
        return;
      }

      const reader = new FileReader();
      reader.onload = async function(e) {
        try {
          const data = JSON.parse(e.target.result);
          if (!Array.isArray(data)) {
            throw new Error('数据格式不正确');
          }

          if (confirm(`将导入 ${data.length} 个 VPS，是否覆盖现有数据？\n\n注意：非人民币价格将自动转换为人民币。`)) {
            // 转换外币为人民币
            const convertedData = await convertCurrenciesToCNY(data);
            vpsList = convertedData;
            await saveVpsList();
            renderVpsList();
            closeImportModal();
            showToast('导入成功！', 'success');
          }
        } catch (error) {
          showToast('导入失败：' + error.message, 'error');
        }
      };
      reader.readAsText(file);
    }

    /**
     * 将 VPS 列表中的外币转换为人民币
     */
    async function convertCurrenciesToCNY(vpsList) {
      const exchangeRates = {};
      const result = [];
      
      for (const vps of vpsList) {
        if (!vps.currency || vps.currency === 'CNY' || !vps.price) {
          result.push(vps);
          continue;
        }
        
        try {
          // 缓存汇率避免重复请求
          if (!exchangeRates[vps.currency]) {
            exchangeRates[vps.currency] = await fetchExchangeRate(vps.currency, 'CNY');
          }
          
          const rate = exchangeRates[vps.currency];
          const convertedPrice = Math.round(vps.price * rate * 100) / 100;
          
          result.push({
            ...vps,
            price: convertedPrice,
            currency: 'CNY',
            notes: vps.notes ? 
              `${vps.notes} (原价: ${vps.currency} ${vps.price})` : 
              `原价: ${vps.currency} ${vps.price}`
          });
        } catch (error) {
          console.error(`转换 ${vps.name} 的货币失败:`, error);
          // 转换失败保持原值
          result.push(vps);
        }
      }
      
      return result;
    }

    /**
     * 关闭导入模态框
     */
    function closeImportModal() {
      document.getElementById('import-modal').classList.remove('active');
      document.getElementById('import-file').value = '';
    }

    // ==================== 标签页切换 ====================

    function switchTab(tabName, updateHash = true) {
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelector(`.tab-btn[onclick*="${tabName}"]`)?.classList.add('active');

      document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
      document.getElementById(tabName)?.classList.add('active');

      if (updateHash) {
        window.location.hash = '#/admin/' + tabName;
      }

      if (tabName === 'ranking') {
        loadRankings('overall');
      }

      if (tabName === 'nezha') {
        loadNezhaConfig();
      }
    }

    function handleHashChange() {
      const hash = window.location.hash.slice(1);
      const validTabs = ['management', 'ranking', 'nezha', 'decision'];
      if (validTabs.includes(hash)) {
        switchTab(hash, false);
      }
    }

    window.addEventListener('hashchange', handleHashChange);

    // ==================== 性价比排行榜 ====================

    let currentRankingDimension = 'overall';

    /**
     * 加载性价比排行榜
     */
    async function loadRankings(sortBy = 'overall') {
      currentRankingDimension = sortBy;

      // 更新按钮状态
      document.querySelectorAll('#ranking .sort-controls .btn').forEach(btn => {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
        if (btn.textContent.includes(sortBy === 'overall' ? '综合' : sortBy === 'cpu' ? 'CPU' : sortBy === 'memory' ? '内存' : sortBy === 'storage' ? '存储' : '网络')) {
          btn.classList.remove('btn-secondary');
          btn.classList.add('btn-primary');
        }
      });

      // 检查是否有配置specs的VPS
      const vpsWithSpecs = vpsList.filter(vps => vps.specs && vps.specs.cpu);

      if (vpsWithSpecs.length === 0) {
        document.getElementById('ranking-list').innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📊</div>
            <div class="empty-state-title">暂无硬件配置数据</div>
            <div class="empty-state-description">请在 VPS 编辑页面添加硬件配置信息，或使用哪吒探针同步</div>
          </div>
        `;
        document.getElementById('ranking-report').innerHTML = '';
        return;
      }

      try {
        const response = await ApiService.getPerformanceRankings(vpsWithSpecs, sortBy);

        if (!response.ok) throw new Error('获取排行榜失败');

        const data = await response.json();
        if (!data.success) throw new Error(data.error || '获取排行榜失败');

        renderRankings(data.data, sortBy);
        loadPerformanceReport();
      } catch (error) {
        console.error('加载排行榜失败:', error);
        document.getElementById('ranking-list').innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">❌</div>
            <div class="empty-state-title">加载失败</div>
            <div class="empty-state-description">${error.message}</div>
          </div>
        `;
      }
    }

    /**
     * 渲染排行榜
     */
    function renderRankings(rankings, sortBy) {
      const dimensionNames = {
        overall: '综合性价比',
        cpu: 'CPU 性价比',
        memory: '内存性价比',
        storage: '存储性价比',
        network: '网络性价比'
      };


      const html = `
        <div style="margin-bottom: 24px; font-size: 14px; color: var(--text-light); display: flex; justify-content: space-between; align-items: center;">
          <span>按 <strong style="color: var(--primary-from);">${dimensionNames[sortBy]}</strong> 排序，共 ${rankings.length} 台服务器</span>
          <span style="font-size: 12px; background: rgba(255,255,255,0.5); padding: 4px 8px; border-radius: 4px;">🏆 数据来源: 哪吒探针</span>
        </div>
        ${rankings.map((vps, index) => {
          const medal = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `${index + 1}.`;
          const score = vps.scores[sortBy];
          const dailyPrice = vps.dailyPrice.toFixed(2);

          return `
            <div class="vps-card" style="margin-bottom: 20px;">
              <div class="vps-card-header">
                <div>
                  <div class="vps-name">${medal} ${vps.name}</div>
                  <div class="vps-provider">日价格: ${vps.currency || 'CNY'} ${dailyPrice}</div>
                </div>
                <div style="text-align: right;">
                  <div style="font-size: 28px; font-weight: 800; background: linear-gradient(135deg, var(--primary-from), var(--primary-to)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${score.toFixed(2)}</div>
                  <div style="font-size: 12px; color: var(--text-light); text-transform: uppercase; font-weight: 600;">得分</div>
                </div>
              </div>

              ${vps.specs ? `
                <div class="vps-info">
                  ${vps.specs.cpu ? `
                    <div class="vps-info-item">
                      <span class="vps-info-label">CPU</span>
                      <span class="vps-info-value">${vps.specs.cpu.model || '未知'} (${vps.specs.cpu.cores}核)</span>
                    </div>
                  ` : ''}
                  ${vps.specs.memory ? `
                    <div class="vps-info-item">
                      <span class="vps-info-label">内存</span>
                      <span class="vps-info-value">${vps.specs.memory.size}GB ${vps.specs.memory.type || ''}</span>
                    </div>
                  ` : ''}
                  ${vps.specs.storage ? `
                    <div class="vps-info-item">
                      <span class="vps-info-label">存储</span>
                      <span class="vps-info-value">${vps.specs.storage.size}GB ${vps.specs.storage.type || ''}</span>
                    </div>
                  ` : ''}
                  ${vps.specs.network ? `
                    <div class="vps-info-item">
                      <span class="vps-info-label">网络</span>
                      <span class="vps-info-value">${vps.specs.network.bandwidth}Mbps / ${vps.specs.network.traffic}GB</span>
                    </div>
                  ` : ''}
                </div>
              ` : ''}

              <div style="margin-top: 16px; display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; font-size: 12px; background: var(--bg-body); padding: 12px; border-radius: var(--radius-md);">
                <div style="text-align: center;">
                  <div style="color: var(--text-light); margin-bottom: 4px;">综合</div>
                  <div style="font-weight: 700; color: var(--text-main);">${vps.scores.overall.toFixed(1)}</div>
                </div>
                <div style="text-align: center; border-left: 1px solid var(--border-color);">
                  <div style="color: var(--text-light); margin-bottom: 4px;">CPU</div>
                  <div style="font-weight: 700; color: var(--text-main);">${vps.scores.cpu.toFixed(1)}</div>
                </div>
                <div style="text-align: center; border-left: 1px solid var(--border-color);">
                  <div style="color: var(--text-light); margin-bottom: 4px;">内存</div>
                  <div style="font-weight: 700; color: var(--text-main);">${vps.scores.memory.toFixed(1)}</div>
                </div>
                <div style="text-align: center; border-left: 1px solid var(--border-color);">
                  <div style="color: var(--text-light); margin-bottom: 4px;">存储</div>
                  <div style="font-weight: 700; color: var(--text-main);">${vps.scores.storage.toFixed(1)}</div>
                </div>
                <div style="text-align: center; border-left: 1px solid var(--border-color);">
                  <div style="color: var(--text-light); margin-bottom: 4px;">网络</div>
                  <div style="font-weight: 700; color: var(--text-main);">${vps.scores.network.toFixed(1)}</div>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      `;

      document.getElementById('ranking-list').innerHTML = html;
    }

    /**
     * 加载性价比统计报告
     */
    async function loadPerformanceReport() {
      const vpsWithSpecs = vpsList.filter(vps => vps.specs && vps.specs.cpu);

      if (vpsWithSpecs.length === 0) {
        document.getElementById('ranking-report').innerHTML = '';
        return;
      }

      try {
        const response = await ApiService.getPerformanceReport(vpsWithSpecs);

        if (!response.ok) throw new Error('获取报告失败');

        const data = await response.json();
        if (!data.success) throw new Error(data.error || '获取报告失败');

        const report = data.data;
        const html = `
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-value">${report.total}</div>
              <div class="stat-label">服务器总数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${report.summary.avgScore.toFixed(1)}</div>
              <div class="stat-label">平均综合得分</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${report.summary.avgDailyPrice.toFixed(2)}</div>
              <div class="stat-label">平均日价格</div>
            </div>
          </div>

          <div style="margin-top: 24px; background: rgba(255,255,255,0.6); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 24px;">
            <h3 style="font-size: 18px; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
              <span>🏆</span> 各维度最佳
            </h3>
            <div style="display: grid; gap: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: white; border-radius: var(--radius-md); border-left: 4px solid var(--primary-from);">
                <span class="vps-info-label" style="font-weight: 600;">综合性价比</span>
                <span class="vps-info-value" style="font-size: 15px;">${report.summary.best.overall.name} (${report.summary.best.overall.score.toFixed(2)})</span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: white; border-radius: var(--radius-md); border-left: 4px solid #3b82f6;">
                <span class="vps-info-label" style="font-weight: 600;">CPU 性价比</span>
                <span class="vps-info-value" style="font-size: 15px;">${report.summary.best.cpu.name} (${report.summary.best.cpu.score.toFixed(2)})</span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: white; border-radius: var(--radius-md); border-left: 4px solid #10b981;">
                <span class="vps-info-label" style="font-weight: 600;">内存性价比</span>
                <span class="vps-info-value" style="font-size: 15px;">${report.summary.best.memory.name} (${report.summary.best.memory.score.toFixed(2)})</span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: white; border-radius: var(--radius-md); border-left: 4px solid #f59e0b;">
                <span class="vps-info-label" style="font-weight: 600;">存储性价比</span>
                <span class="vps-info-value" style="font-size: 15px;">${report.summary.best.storage.name} (${report.summary.best.storage.score.toFixed(2)})</span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: white; border-radius: var(--radius-md); border-left: 4px solid #8b5cf6;">
                <span class="vps-info-label" style="font-weight: 600;">网络性价比</span>
                <span class="vps-info-value" style="font-size: 15px;">${report.summary.best.network.name} (${report.summary.best.network.score.toFixed(2)})</span>
              </div>
            </div>
          </div>
        `;

        document.getElementById('ranking-report').innerHTML = html;
      } catch (error) {
        console.error('加载报告失败:', error);
      }
    }

    // ==================== 哪吒探针集成 ====================

    /**
     * 加载 CPU 型号列表
     */
    async function loadCPUModels() {
      try {
        const response = await ApiService.getCpuModels();
        if (!response.ok) return;

        const data = await response.json();
        if (data.success && data.data) {
          const datalist = document.getElementById('cpu-models-list');
          datalist.innerHTML = data.data.map(model => `<option value="${model}">`).join('');
        }
      } catch (error) {
        console.error('加载 CPU 型号失败:', error);
      }
    }

    /**
     * 加载哪吒配置
     */
    async function loadNezhaConfig() {
      try {
        const response = await ApiService.getNezhaConfig();
        if (!response.ok) throw new Error('获取配置失败');

        const data = await response.json();
        if (data.success && data.data) {
          document.getElementById('nezha-api-url').value = data.data.apiUrl || '';
          document.getElementById('nezha-token').value = data.data.token || '';
          document.getElementById('nezha-auto-sync').checked = data.data.autoSync || false;
        }
      } catch (error) {
        console.error('加载哪吒配置失败:', error);
      }
    }

    /**
     * 保存哪吒配置
     */
    async function saveNezhaConfig() {
      const apiUrl = document.getElementById('nezha-api-url').value.trim();
      const token = document.getElementById('nezha-token').value.trim();
      const autoSync = document.getElementById('nezha-auto-sync').checked;

      if (!apiUrl || !token) {
        showToast('请填写 API 地址和 Token', 'warning');
        return;
      }

      try {
        const response = await ApiService.saveNezhaConfig({ apiUrl, token, autoSync });

        if (!response.ok) throw new Error('保存配置失败');

        const data = await response.json();
        if (data.success) {
          showToast('配置保存成功！', 'success');
        } else {
          throw new Error(data.error || '保存失败');
        }
      } catch (error) {
        showToast('保存失败：' + error.message, 'error');
      }
    }

    /**
     * 测试哪吒连接
     */
    async function testNezhaConnection() {
      const apiUrl = document.getElementById('nezha-api-url').value.trim();
      const token = document.getElementById('nezha-token').value.trim();

      if (!apiUrl || !token) {
        showToast('请先填写 API 地址和 Token', 'warning');
        return;
      }

      const resultDiv = document.getElementById('nezha-test-result');
      resultDiv.innerHTML = '<div style="display: flex; align-items: center; gap: 8px; color: var(--text-light);"><div class="loading"></div> 正在测试连接...</div>';

      try {
        const response = await ApiService.testNezha({ apiUrl, token });

        if (!response.ok) throw new Error('测试失败');

        const data = await response.json();
        if (data.success) {
          resultDiv.innerHTML = `
            <div class="decision-result">
              <div class="decision-title">✅ 连接成功！</div>
              <p style="margin-top: 8px; color: var(--text-light);">${data.data.message}</p>
            </div>
          `;
        } else {
          throw new Error(data.error || '连接失败');
        }
      } catch (error) {
        resultDiv.innerHTML = `
          <div class="decision-result warning">
            <div class="decision-title">❌ 连接失败</div>
            <p style="margin-top: 8px; color: var(--text-light);">${error.message}</p>
          </div>
        `;
      }
    }

    /**
     * 同步哪吒服务器
     */
    async function syncNezhaServers() {
      const resultDiv = document.getElementById('nezha-sync-result');
      resultDiv.innerHTML = '<div style="display: flex; align-items: center; gap: 8px; color: var(--text-light);"><div class="loading"></div> 正在同步服务器列表...</div>';

      try {
        const response = await ApiService.syncNezha();

        if (!response.ok) throw new Error('同步失败');

        const data = await response.json();
        if (!data.success) throw new Error(data.error || '同步失败');

        const servers = data.data;

        if (servers.length === 0) {
          resultDiv.innerHTML = `
            <div class="decision-result warning">
              <div class="decision-title">⚠️ 未找到服务器</div>
              <p style="margin-top: 8px; color: var(--text-light);">哪吒探针中没有服务器数据</p>
            </div>
          `;
          return;
        }

        // 询问是否导入
        if (confirm(`找到 ${servers.length} 台服务器，是否导入到 VPS 列表？\n\n注意：需要手动补充价格和购买日期信息。`)) {
          // 合并到 vpsList
          servers.forEach(server => {
            // 检查是否已存在（通过 nezha.serverId 判断）
            const existing = vpsList.find(vps => vps.nezha && vps.nezha.serverId === server.nezha.serverId);
            if (!existing) {
              // 新增服务器，需要用户补充价格信息
              vpsList.push({
                id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
                name: server.name,
                provider: '哪吒探针',
                price: 0, // 需要用户补充
                currency: 'CNY',
                cycle: 'monthly',
                purchaseDate: new Date().toISOString().split('T')[0],
                notes: '从哪吒探针同步',
                specs: server.specs,
                nezha: server.nezha
              });
            } else {
              // 更新现有服务器的 specs
              existing.specs = server.specs;
              existing.nezha = server.nezha;
            }
          });

          await saveVpsList();
          renderVpsList();

          resultDiv.innerHTML = `
            <div class="decision-result">
              <div class="decision-title">✅ 同步成功！</div>
              <p style="margin-top: 8px; color: var(--text-light);">
                已导入 ${servers.length} 台服务器。<br>
                请在"批量管理"页面编辑 VPS，补充价格和购买日期信息。
              </p>
            </div>
          `;

          // 3秒后切换到管理页面
          setTimeout(() => {
            switchTab('management');
          }, 3000);
        } else {
          resultDiv.innerHTML = `
            <div class="decision-result warning">
              <div class="decision-title">已取消导入</div>
            </div>
          `;
        }
      } catch (error) {
        resultDiv.innerHTML = `
          <div class="decision-result warning">
            <div class="decision-title">❌ 同步失败</div>
            <p style="margin-top: 8px; color: var(--text-light);">${error.message}</p>
          </div>
        `;
      }
    }

    // ==================== 续费决策助手 ====================

    /**
     * 计算续费决策
     */
    async function calculateDecision() {
      const currentPrice = parseFloat(document.getElementById('current-price').value);
      const currentCurrency = document.getElementById('current-currency').value;
      const currentCycle = document.getElementById('current-cycle').value;
      const currentPurchaseDate = document.getElementById('current-purchase-date').value;

      const renewalPrice = parseFloat(document.getElementById('renewal-price').value);
      const renewalCurrency = document.getElementById('renewal-currency').value;
      const renewalCycle = document.getElementById('renewal-cycle').value;

      const discountPercent = parseFloat(document.getElementById('discount-percent').value) || 0;

      // 验证
      if (!currentPrice || !currentPurchaseDate || !renewalPrice) {
        showToast('请填写所有必填项', 'warning');
        return;
      }

      try {
        // 计算当前 VPS 剩余价值
        const currentTotalDays = getDaysByCycle(currentCycle);
        const currentUsedDays = calculateUsedDays(currentPurchaseDate);
        const currentResult = calculateRemainingValue(currentPrice, currentTotalDays, currentUsedDays);

        // 计算续费实际价格（考虑折扣）
        const actualRenewalPrice = renewalPrice * (1 - discountPercent / 100);

        // 获取汇率（如果货币不同）
        let exchangeRate = 1;
        if (currentCurrency !== renewalCurrency) {
          exchangeRate = await fetchExchangeRate(renewalCurrency, currentCurrency);
        }

        // 将续费价格转换为当前货币
        const renewalPriceInCurrentCurrency = actualRenewalPrice * exchangeRate;

        // 计算续费后的总价值
        const renewalTotalDays = getDaysByCycle(renewalCycle);
        const renewalDailyRate = renewalPriceInCurrentCurrency / renewalTotalDays;

        // 计算"放弃剩余价值+续费"的总成本
        const costOfRenewal = renewalPriceInCurrentCurrency;

        // 计算重新购买的成本（假设重新购买价格等于续费价格）
        const costOfRepurchase = renewalPriceInCurrentCurrency;

        // 决策逻辑
        const remainingValue = currentResult.remainingValue;
        const totalCostIfRenew = costOfRenewal; // 续费直接花费
        const totalCostIfRepurchase = costOfRepurchase - remainingValue; // 重购可以先用完剩余价值

        let recommendation = '';
        let savingsAmount = 0;
        let isWarning = false;

        if (remainingValue > renewalPriceInCurrentCurrency * 0.3) {
          // 剩余价值超过续费价格的 30%，建议先用完再考虑
          recommendation = '🚨 剩余价值较高，建议先用完现有服务再考虑续费或重购';
          savingsAmount = remainingValue;
          isWarning = true;
        } else if (totalCostIfRepurchase < totalCostIfRenew) {
          recommendation = '💡 建议重新购买新服务，更加划算';
          savingsAmount = totalCostIfRenew - totalCostIfRepurchase;
        } else {
          recommendation = '✅ 建议续费当前服务';
          savingsAmount = totalCostIfRepurchase - totalCostIfRenew;
        }

        // 显示结果
        const resultHTML = `
          <div class="decision-result ${isWarning ? 'warning' : ''}">
            <div class="decision-title">${recommendation}</div>
            ${savingsAmount > 0 ? `<p style="font-size: 16px; color: var(--text-light); margin-top: 8px;">预计可节省：<strong style="color: var(--success);">${currentCurrency} ${savingsAmount.toFixed(2)}</strong></p>` : ''}

            <div class="decision-details">
              <div class="decision-item">
                <div class="decision-item-label">当前剩余价值</div>
                <div class="decision-item-value">${currentCurrency} ${remainingValue.toFixed(2)}</div>
              </div>
              <div class="decision-item">
                <div class="decision-item-label">当前剩余天数</div>
                <div class="decision-item-value">${currentResult.remainingDays} 天</div>
              </div>
              <div class="decision-item">
                <div class="decision-item-label">续费价格（折后）</div>
                <div class="decision-item-value">${renewalCurrency} ${actualRenewalPrice.toFixed(2)}</div>
              </div>
              <div class="decision-item">
                <div class="decision-item-label">续费周期</div>
                <div class="decision-item-value">${getCycleName(renewalCycle)}</div>
              </div>
              <div class="decision-item">
                <div class="decision-item-label">续费日均成本</div>
                <div class="decision-item-value">${currentCurrency} ${renewalDailyRate.toFixed(2)}/天</div>
              </div>
              <div class="decision-item">
                <div class="decision-item-label">当前日均成本</div>
                <div class="decision-item-value">${currentCurrency} ${currentResult.dailyRate.toFixed(2)}/天</div>
              </div>
            </div>

            ${discountPercent > 0 ? `<p style="margin-top: 16px; font-size: 14px; color: var(--text-light);">✨ 已应用 ${discountPercent}% 折扣</p>` : ''}
            ${currentCurrency !== renewalCurrency ? `<p style="margin-top: 8px; font-size: 14px; color: var(--text-light);">💱 汇率: 1 ${renewalCurrency} = ${exchangeRate.toFixed(4)} ${currentCurrency}</p>` : ''}
          </div>
        `;

        document.getElementById('decision-result').innerHTML = resultHTML;
      } catch (error) {
        showToast('计算失败：' + error.message, 'error');
      }
    }

    // ==================== 初始化 ====================

    document.addEventListener('DOMContentLoaded', function() {
      const today = new Date().toISOString().split('T')[0];
      document.getElementById('current-purchase-date').value = today;

      document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
          if (e.target === modal) {
            modal.classList.remove('active');
          }
        });
      });

      handleHashChange();
    });
