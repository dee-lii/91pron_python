/**
 * VPS 剩余价值计算核心模块
 * 提供价值计算、验证等功能
 * UMD 格式：支持 Node.js 和浏览器环境
 */

(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.VPSCalculator = factory();
  }
}(typeof self !== 'undefined' ? self : this, function() {

  function isValidNumber(value) {
    return typeof value === 'number' && !isNaN(value) && isFinite(value);
  }

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
    if (usedDays > totalDays) {
      throw new Error('已使用天数不能超过总天数');
    }
  }

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

  function getDaysByCycle(cycle) {
    if (typeof cycle !== 'string') {
      throw new Error('不支持的付款周期：' + cycle);
    }
    // Normalize cycle string
    const normalizedCycle = cycle.toLowerCase().trim();
    
    // Map variants to standard cycles
    if (['monthly', 'month', 'mo'].includes(normalizedCycle)) {
      return 30;
    }
    if (['yearly', 'year', 'annually', 'annual', 'yr'].includes(normalizedCycle)) {
      return 365;
    }
    if (['biennial', 'biannual'].includes(normalizedCycle)) {
      return 730;
    }
    if (normalizedCycle === 'triennial') {
      return 1095;
    }

    const cycleDays = {
      monthly: 30,
      yearly: 365,
      biennial: 730,
      triennial: 1095
    };
    if (!cycleDays[normalizedCycle]) {
      throw new Error('不支持的付款周期：' + cycle);
    }
    return cycleDays[normalizedCycle];
  }

  function calculateUsedDays(purchaseDate) {
    const purchase = new Date(purchaseDate);
    if (isNaN(purchase.getTime())) {
      throw new Error('购买日期格式不正确');
    }
    const now = new Date();
    const diffTime = now - purchase;
    if (diffTime < 0) {
      throw new Error('购买日期不能晚于当前日期');
    }
    return Math.floor(diffTime / (1000 * 60 * 60 * 24));
  }

  return {
    calculateRemainingValue: calculateRemainingValue,
    validateInputs: validateInputs,
    isValidNumber: isValidNumber,
    getDaysByCycle: getDaysByCycle,
    calculateUsedDays: calculateUsedDays
  };

}));
