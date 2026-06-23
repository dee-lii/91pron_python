    // ==================== 认证系统 ====================

    const AUTH_TOKEN_KEY = 'vps_manager_token';
    
    function getToken() {
      return localStorage.getItem(AUTH_TOKEN_KEY);
    }
    
    function setToken(token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    }
    
    function clearToken() {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }

    // ==================== Toast 通知组件 ====================

    function showToast(message, type = 'info') {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = `toast ${type}`;
      toast.textContent = message;
      container.appendChild(toast);
      
      setTimeout(() => {
        toast.style.animation = 'toastSlideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
      }, 3000);
    }

    // ==================== 核心计算函数（从 calculator.js 复用） ====================

    /**
     * 检查是否为有效数字
     */
    function isValidNumber(value) {
      return typeof value === 'number' && !isNaN(value) && isFinite(value);
    }

    /**
     * 验证输入参数
     */
    function validateInputs(totalCost, totalDays, usedDays) {
      if (!isValidNumber(totalCost) || totalCost <= 0) {
        throw new Error('总成本必须是大于 0 的数字');
      }
      if (!isValidNumber(totalDays) || totalDays <= 0) {
        throw new Error('总天数必须是大于 0 的整数');
      }
      if (!isValidNumber(usedDays) || usedDays < 0) {
        throw new Error('已使用天数必须是非负整数');
      }
      // 允许已过期的 VPS（usedDays > totalDays）
    }

    /**
     * 计算 VPS 剩余价值
     */
    function calculateRemainingValue(totalCost, totalDays, usedDays) {
      validateInputs(totalCost, totalDays, usedDays);

      const dailyRate = totalCost / totalDays;
      const usedValue = dailyRate * usedDays;
      const remainingDays = totalDays - usedDays;
      const remainingValue = dailyRate * remainingDays;
      const usageRate = (usedDays / totalDays) * 100;

      return {
        remainingValue: parseFloat(remainingValue.toFixed(2)),
        usedValue: parseFloat(usedValue.toFixed(2)),
        remainingDays,
        usageRate: parseFloat(usageRate.toFixed(2)),
        dailyRate: parseFloat(dailyRate.toFixed(2))
      };
    }

    /**
     * 根据付款周期获取总天数
     */
    function getDaysByCycle(cycle) {
      if (!cycle) return 365;
      if (typeof cycle !== 'string') return 365;

      const normalizedCycle = cycle.toLowerCase().trim();
      
      if (['monthly', 'month', 'mo'].includes(normalizedCycle)) return 30;
      if (['yearly', 'year', 'annually', 'annual', 'yr'].includes(normalizedCycle)) return 365;
      if (['biennial', 'biannual'].includes(normalizedCycle)) return 730;
      if (normalizedCycle === 'triennial') return 1095;

      const cycleDays = {
        monthly: 30,
        yearly: 365,
        biennial: 730,
        triennial: 1095
      };

      if (!cycleDays[normalizedCycle]) {
        return 365; // 默认按年计算
      }

      return cycleDays[normalizedCycle];
    }

    /**
     * 计算已使用天数
     */
    function calculateUsedDays(purchaseDate) {
      if (!purchaseDate) {
        return 0; // 没有购买日期，返回 0
      }
      const purchase = new Date(purchaseDate);
      if (isNaN(purchase.getTime())) {
        return 0; // 无效日期，返回 0
      }

      const now = new Date();
      const diffTime = now - purchase;

      if (diffTime < 0) {
        throw new Error('购买日期不能晚于当前日期');
      }

      return Math.floor(diffTime / (1000 * 60 * 60 * 24));
    }

    /**
     * 获取周期显示名称
     */
    function getCycleName(cycle) {
      const names = {
        monthly: '月付',
        yearly: '年付',
        biennial: '两年付',
        triennial: '三年付'
      };
      return names[cycle] || cycle || '未设置';
    }
