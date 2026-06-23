    function authFetch(url, options = {}) {
      const token = getToken();
      return fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          ...options.headers
        }
      });
    }

    /**
     * 获取汇率
     */
    async function fetchExchangeRate(from, to) {
      if (from === to) return 1;

      try {
        const response = await fetch(`/api/exchange-rate?from=${from}&to=${to}`);
        if (!response.ok) {
          throw new Error('汇率获取失败');
        }
        const result = await response.json();
        if (!result.success || !result.data?.rate) {
          throw new Error(result.error || '汇率数据无效');
        }
        return result.data.rate;
      } catch (error) {
        console.error('汇率获取失败:', error);
        throw new Error('无法获取汇率，请检查网络连接');
      }
    }

    /**
     * API Service - Encapsulates all backend calls
     */
    const ApiService = {
      // Auth
      authStatus: () => fetch('/api/auth/status'),
      authMe: () => authFetch('/api/auth/me'),
      authInit: (data) => fetch('/api/auth/init', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(data) 
      }),
      authLogin: (data) => fetch('/api/auth/login', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(data) 
      }),
      changePassword: (data) => authFetch('/api/auth/password', { 
        method: 'PUT', 
        body: JSON.stringify(data) 
      }),

      // Public
      publicStats: () => fetch('/api/public/stats'),
      publicServers: () => fetch('/api/public/servers'),
      publicRankings: () => fetch('/api/public/rankings'),

      // VPS Management
      getVpsList: () => authFetch('/api/vps'),
      saveVpsList: (vpsList) => authFetch('/api/vps', { 
        method: 'PUT', 
        body: JSON.stringify({ vpsList }) 
      }),

      // Performance Rankings & Reports
      getPerformanceRankings: (vpsList, sortBy) => authFetch('/api/performance/rankings', { 
        method: 'POST', 
        body: JSON.stringify({ vpsList, sortBy }) 
      }),
      getPerformanceReport: (vpsList) => authFetch('/api/performance/report', { 
        method: 'POST', 
        body: JSON.stringify({ vpsList }) 
      }),

      // Hardware Info
      getCpuModels: () => fetch('/api/cpu/models'),

      // Nezha Integration
      getNezhaConfig: () => authFetch('/api/nezha/config'),
      saveNezhaConfig: (data) => authFetch('/api/nezha/config', { 
        method: 'POST', 
        body: JSON.stringify(data) 
      }),
      testNezha: (data) => authFetch('/api/nezha/test', { 
        method: 'POST', 
        body: JSON.stringify(data) 
      }),
      syncNezha: () => authFetch('/api/nezha/sync', { 
        method: 'POST' 
      })
    };
