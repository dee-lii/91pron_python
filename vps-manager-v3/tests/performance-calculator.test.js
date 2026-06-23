const {
  getVpsCost,
  getDailyPrice,
  getVpsDailyPrice,
  calculateMemoryScore,
  calculateStorageScore,
  calculateNetworkScore,
  calculatePriceScore,
  calculateRankings,
  generatePerformanceReport
} = require('../src/performance-calculator');

describe('performance-calculator', () => {
  describe('getVpsCost', () => {
    test('returns totalCost when present', () => {
      expect(getVpsCost({ totalCost: 100, price: 50 })).toBe(100);
    });

    test('falls back to price when totalCost missing', () => {
      expect(getVpsCost({ price: 50 })).toBe(50);
    });

    test('returns 0 for invalid cost', () => {
      expect(getVpsCost({})).toBe(0);
      expect(getVpsCost({ totalCost: -10 })).toBe(0);
      expect(getVpsCost({ totalCost: NaN })).toBe(0);
    });
  });

  describe('getDailyPrice', () => {
    test('calculates daily price for monthly', () => {
      expect(getDailyPrice(30, 'monthly')).toBe(1);
    });

    test('calculates daily price for yearly', () => {
      expect(getDailyPrice(365, 'yearly')).toBe(1);
    });

    test('defaults to yearly for unknown cycle', () => {
      expect(getDailyPrice(365, 'unknown')).toBe(1);
    });
  });

  describe('getVpsDailyPrice', () => {
    test('calculates daily price from VPS object', () => {
      const vps = { price: 365, cycle: 'yearly' };
      expect(getVpsDailyPrice(vps)).toBe(1);
    });

    test('returns 0 for invalid VPS', () => {
      expect(getVpsDailyPrice({})).toBe(0);
    });
  });

  describe('calculateMemoryScore', () => {
    test('returns 0 when no memory specs', () => {
      expect(calculateMemoryScore({})).toBe(0);
      expect(calculateMemoryScore({ specs: {} })).toBe(0);
    });

    test('calculates memory score correctly', () => {
      const vps = { price: 365, cycle: 'yearly', specs: { memory: { size: 8 } } };
      expect(calculateMemoryScore(vps)).toBe(8);
    });
  });

  describe('calculateStorageScore', () => {
    test('returns 0 when no storage specs', () => {
      expect(calculateStorageScore({})).toBe(0);
    });

    test('applies multiplier for NVMe SSD', () => {
      const vps = { price: 365, cycle: 'yearly', specs: { storage: { size: 100, type: 'NVMe SSD' } } };
      expect(calculateStorageScore(vps)).toBe(150);
    });

    test('applies multiplier for SSD', () => {
      const vps = { price: 365, cycle: 'yearly', specs: { storage: { size: 100, type: 'SSD' } } };
      expect(calculateStorageScore(vps)).toBe(120);
    });

    test('uses default multiplier for HDD', () => {
      const vps = { price: 365, cycle: 'yearly', specs: { storage: { size: 100, type: 'HDD' } } };
      expect(calculateStorageScore(vps)).toBe(100);
    });
  });

  describe('calculateNetworkScore', () => {
    test('returns 0 when no network specs', () => {
      expect(calculateNetworkScore({})).toBe(0);
    });

    test('calculates network score correctly', () => {
      const vps = { price: 365, cycle: 'yearly', specs: { network: { bandwidth: 1000 } } };
      expect(calculateNetworkScore(vps)).toBe(1000);
    });
  });

  describe('calculatePriceScore', () => {
    test('returns 0 for invalid VPS', () => {
      expect(calculatePriceScore({})).toBe(0);
    });

    test('returns high score for low daily price', () => {
      const vps = { price: 36.5, cycle: 'yearly' };
      const score = calculatePriceScore(vps);
      expect(score).toBeGreaterThan(90);
    });

    test('returns low score for high daily price', () => {
      const vps = { price: 300, cycle: 'monthly' };
      const score = calculatePriceScore(vps);
      expect(score).toBe(0);
    });
  });

  describe('calculateRankings', () => {
    const vpsList = [
      {
        name: 'VPS-A',
        price: 100,
        cycle: 'yearly',
        specs: {
          cpu: { model: 'AMD EPYC', cores: 2 },
          memory: { size: 4 },
          storage: { size: 50, type: 'SSD' },
          network: { bandwidth: 1000 }
        }
      },
      {
        name: 'VPS-B',
        price: 200,
        cycle: 'yearly',
        specs: {
          cpu: { model: 'Intel Xeon', cores: 4 },
          memory: { size: 8 },
          storage: { size: 100, type: 'NVMe SSD' },
          network: { bandwidth: 2000 }
        }
      }
    ];

    test('returns empty array for empty list', () => {
      expect(calculateRankings([])).toEqual([]);
    });

    test('filters out VPS without specs', () => {
      expect(calculateRankings([{ name: 'No Specs' }])).toEqual([]);
    });

    test('ranks VPS list by overall score', () => {
      const rankings = calculateRankings(vpsList);
      expect(rankings).toHaveLength(2);
      expect(rankings[0].rank).toBe(1);
      expect(rankings[1].rank).toBe(2);
    });

    test('includes performance data', () => {
      const rankings = calculateRankings(vpsList);
      expect(rankings[0].performance).toBeDefined();
      expect(rankings[0].performance.overall).toBeGreaterThan(0);
      expect(rankings[0].performance.scores).toBeDefined();
      expect(rankings[0].performance.dailyPrice).toBeGreaterThan(0);
    });

    test('supports sorting by specific dimension', () => {
      const byMemory = calculateRankings(vpsList, 'memory');
      expect(byMemory.length).toBe(2);
      expect(byMemory[0].performance.scores.memory).toBeGreaterThanOrEqual(
        byMemory[1].performance.scores.memory
      );
    });
  });

  describe('generatePerformanceReport', () => {
    const vpsList = [
      {
        name: 'VPS-A',
        price: 100,
        cycle: 'yearly',
        specs: {
          cpu: { model: 'AMD EPYC', cores: 2 },
          memory: { size: 4 },
          storage: { size: 50, type: 'SSD' },
          network: { bandwidth: 1000 }
        }
      }
    ];

    test('returns empty report for empty list', () => {
      const report = generatePerformanceReport([]);
      expect(report.total).toBe(0);
      expect(report.rankings).toEqual([]);
      expect(report.summary).toBeNull();
    });

    test('generates report with summary', () => {
      const report = generatePerformanceReport(vpsList);
      expect(report.total).toBe(1);
      expect(report.rankings).toHaveLength(1);
      expect(report.summary).toBeDefined();
      expect(report.summary.avgScore).toBeGreaterThan(0);
      expect(report.summary.avgDailyPrice).toBeGreaterThan(0);
      expect(report.summary.best).toBeDefined();
    });

    test('identifies best VPS in each category', () => {
      const report = generatePerformanceReport(vpsList);
      expect(report.summary.best.overall.name).toBe('VPS-A');
      expect(report.summary.best.cpu.name).toBe('VPS-A');
      expect(report.summary.best.memory.name).toBe('VPS-A');
    });
  });
});
