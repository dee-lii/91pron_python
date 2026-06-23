const VPSCalculator = require('../src/calculator');

describe('VPSCalculator', () => {
  describe('isValidNumber', () => {
    test('returns true for valid numbers', () => {
      expect(VPSCalculator.isValidNumber(0)).toBe(true);
      expect(VPSCalculator.isValidNumber(100)).toBe(true);
      expect(VPSCalculator.isValidNumber(-50)).toBe(true);
      expect(VPSCalculator.isValidNumber(3.14)).toBe(true);
    });

    test('returns false for NaN', () => {
      expect(VPSCalculator.isValidNumber(NaN)).toBe(false);
    });

    test('returns false for Infinity', () => {
      expect(VPSCalculator.isValidNumber(Infinity)).toBe(false);
      expect(VPSCalculator.isValidNumber(-Infinity)).toBe(false);
    });

    test('returns false for non-numbers', () => {
      expect(VPSCalculator.isValidNumber('100')).toBe(false);
      expect(VPSCalculator.isValidNumber(null)).toBe(false);
      expect(VPSCalculator.isValidNumber(undefined)).toBe(false);
      expect(VPSCalculator.isValidNumber({})).toBe(false);
    });
  });

  describe('validateInputs', () => {
    test('passes with valid inputs', () => {
      expect(() => VPSCalculator.validateInputs(100, 365, 100)).not.toThrow();
    });

    test('throws for zero totalCost', () => {
      expect(() => VPSCalculator.validateInputs(0, 365, 100)).toThrow('总成本必须是大于 0 的数字');
    });

    test('throws for negative totalCost', () => {
      expect(() => VPSCalculator.validateInputs(-100, 365, 100)).toThrow('总成本必须是大于 0 的数字');
    });

    test('throws for zero totalDays', () => {
      expect(() => VPSCalculator.validateInputs(100, 0, 0)).toThrow('总天数必须是大于 0 的整数');
    });

    test('throws for negative usedDays', () => {
      expect(() => VPSCalculator.validateInputs(100, 365, -1)).toThrow('已使用天数必须是非负整数');
    });

    test('throws when usedDays exceeds totalDays', () => {
      expect(() => VPSCalculator.validateInputs(100, 365, 400)).toThrow('已使用天数不能超过总天数');
    });
  });

  describe('getDaysByCycle', () => {
    test('returns 30 for monthly', () => {
      expect(VPSCalculator.getDaysByCycle('monthly')).toBe(30);
    });

    test('returns 365 for yearly', () => {
      expect(VPSCalculator.getDaysByCycle('yearly')).toBe(365);
    });

    test('returns 730 for biennial', () => {
      expect(VPSCalculator.getDaysByCycle('biennial')).toBe(730);
    });

    test('returns 1095 for triennial', () => {
      expect(VPSCalculator.getDaysByCycle('triennial')).toBe(1095);
    });

    test('throws for unknown cycle', () => {
      expect(() => VPSCalculator.getDaysByCycle('weekly')).toThrow('不支持的付款周期');
    });
  });

  describe('calculateRemainingValue', () => {
    test('calculates correctly for half usage', () => {
      const result = VPSCalculator.calculateRemainingValue(365, 365, 182);
      expect(result.remainingValue).toBeCloseTo(183, 0);
      expect(result.usedValue).toBeCloseTo(182, 0);
      expect(result.remainingDays).toBe(183);
      expect(result.usageRate).toBeCloseTo(49.86, 1);
      expect(result.dailyRate).toBe(1);
    });

    test('calculates correctly for zero usage', () => {
      const result = VPSCalculator.calculateRemainingValue(100, 100, 0);
      expect(result.remainingValue).toBe(100);
      expect(result.usedValue).toBe(0);
      expect(result.remainingDays).toBe(100);
      expect(result.usageRate).toBe(0);
    });

    test('calculates correctly for full usage', () => {
      const result = VPSCalculator.calculateRemainingValue(100, 100, 100);
      expect(result.remainingValue).toBe(0);
      expect(result.usedValue).toBe(100);
      expect(result.remainingDays).toBe(0);
      expect(result.usageRate).toBe(100);
    });

    test('handles decimal costs', () => {
      const result = VPSCalculator.calculateRemainingValue(99.99, 30, 15);
      expect(result.remainingValue).toBeCloseTo(50, 0);
      expect(result.usedValue).toBeCloseTo(50, 0);
      expect(result.usageRate).toBe(50);
    });
  });

  describe('calculateUsedDays', () => {
    test('calculates days from past date', () => {
      const today = new Date();
      const tenDaysAgo = new Date(today);
      tenDaysAgo.setDate(today.getDate() - 10);
      const dateStr = tenDaysAgo.toISOString().split('T')[0];
      
      expect(VPSCalculator.calculateUsedDays(dateStr)).toBe(10);
    });

    test('returns 0 for today', () => {
      const today = new Date().toISOString().split('T')[0];
      expect(VPSCalculator.calculateUsedDays(today)).toBe(0);
    });

    test('throws for invalid date format', () => {
      expect(() => VPSCalculator.calculateUsedDays('invalid')).toThrow('购买日期格式不正确');
    });

    test('throws for future date', () => {
      const future = new Date();
      future.setDate(future.getDate() + 10);
      const dateStr = future.toISOString().split('T')[0];
      
      expect(() => VPSCalculator.calculateUsedDays(dateStr)).toThrow('购买日期不能晚于当前日期');
    });
  });
});
