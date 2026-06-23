/**
 * VPS 性价比计算引擎
 * 计算各维度性价比得分和综合排名
 */

const { getCPUBenchmark } = require('./cpu-benchmarks');

/**
 * 获取 VPS 的总成本（兼容 price 和 totalCost 字段）
 * @param {object} vps - VPS 对象
 * @returns {number} 总成本
 */
function getVpsCost(vps) {
  const cost = vps.totalCost ?? vps.price ?? 0;
  return typeof cost === 'number' && !isNaN(cost) && cost > 0 ? cost : 0;
}

/**
 * 计算日均价格
 * @param {number} totalCost - 总成本
 * @param {string} cycle - 付款周期
 * @returns {number} 日均价格
 */
function getDailyPrice(totalCost, cycle) {
  const daysMap = {
    'monthly': 30,
    'yearly': 365,
    'biennial': 730,
    'triennial': 1095
  };
  const days = daysMap[cycle] || 365;
  return totalCost / days;
}

/**
 * 计算 VPS 的日均价格（兼容 price/totalCost）
 * @param {object} vps - VPS 对象
 * @returns {number} 日均价格
 */
function getVpsDailyPrice(vps) {
  const cost = getVpsCost(vps);
  if (cost === 0) return 0;
  return getDailyPrice(cost, vps.cycle);
}

/**
 * 计算 CPU 性价比得分
 * @param {object} vps - VPS 对象
 * @returns {number} CPU 性价比得分
 */
function calculateCPUScore(vps) {
  if (!vps.specs?.cpu) return 0;

  const dailyPrice = getVpsDailyPrice(vps);
  if (dailyPrice === 0) return 0;

  const cpuData = getCPUBenchmark(vps.specs.cpu.model, vps.specs.cpu.cores);

  // 使用单线程分数 × 核心数作为性能指标
  const performance = cpuData.singleThread * vps.specs.cpu.cores;

  return performance / dailyPrice;
}

/**
 * 计算内存性价比得分
 * @param {object} vps - VPS 对象
 * @returns {number} 内存性价比得分
 */
function calculateMemoryScore(vps) {
  if (!vps.specs?.memory?.size) return 0;

  const dailyPrice = getVpsDailyPrice(vps);
  if (dailyPrice === 0) return 0;

  return vps.specs.memory.size / dailyPrice;
}

/**
 * 计算存储性价比得分
 * @param {object} vps - VPS 对象
 * @returns {number} 存储性价比得分
 */
function calculateStorageScore(vps) {
  if (!vps.specs?.storage?.size) return 0;

  const dailyPrice = getVpsDailyPrice(vps);
  if (dailyPrice === 0) return 0;

  // 根据存储类型调整权重
  const typeMultiplier = {
    'NVMe SSD': 1.5,
    'SSD': 1.2,
    'HDD': 1.0
  };

  const multiplier = typeMultiplier[vps.specs.storage.type] || 1.0;

  return (vps.specs.storage.size * multiplier) / dailyPrice;
}

/**
 * 计算网络性价比得分
 * @param {object} vps - VPS 对象
 * @returns {number} 网络性价比得分
 */
function calculateNetworkScore(vps) {
  if (!vps.specs?.network?.bandwidth) return 0;

  const dailyPrice = getVpsDailyPrice(vps);
  if (dailyPrice === 0) return 0;

  return vps.specs.network.bandwidth / dailyPrice;
}

/**
 * 计算价格得分（价格越低得分越高）
 * @param {object} vps - VPS 对象
 * @returns {number} 价格得分
 */
function calculatePriceScore(vps) {
  const dailyPrice = getVpsDailyPrice(vps);
  if (dailyPrice === 0) return 0;

  // 归一化：假设最高日价为 $10，最低为 $0.1
  const maxPrice = 10;
  const minPrice = 0.1;

  // 价格越低，得分越高
  return Math.max(0, (maxPrice - dailyPrice) / (maxPrice - minPrice)) * 100;
}

/**
 * 计算综合性价比得分
 * @param {object} vps - VPS 对象
 * @param {object} weights - 权重配置
 * @returns {object} 各维度得分和综合得分
 */
function calculateOverallScore(vps, weights = null) {
  // 默认权重
  const defaultWeights = {
    cpu: 0.30,
    memory: 0.25,
    storage: 0.15,
    network: 0.10,
    price: 0.20
  };

  const w = weights || defaultWeights;

  const cpuScore = calculateCPUScore(vps);
  const memoryScore = calculateMemoryScore(vps);
  const storageScore = calculateStorageScore(vps);
  const networkScore = calculateNetworkScore(vps);
  const priceScore = calculatePriceScore(vps);

  // 归一化各维度得分到 0-100
  const maxCpu = 100000;     // 假设最高 CPU 性价比
  const maxMemory = 1000;    // 假设最高内存性价比
  const maxStorage = 10000;  // 假设最高存储性价比
  const maxNetwork = 50000;  // 假设最高网络性价比

  const normalizedScores = {
    cpu: Math.min(100, (cpuScore / maxCpu) * 100),
    memory: Math.min(100, (memoryScore / maxMemory) * 100),
    storage: Math.min(100, (storageScore / maxStorage) * 100),
    network: Math.min(100, (networkScore / maxNetwork) * 100),
    price: priceScore
  };

  // 计算加权综合得分
  const overall = (
    normalizedScores.cpu * w.cpu +
    normalizedScores.memory * w.memory +
    normalizedScores.storage * w.storage +
    normalizedScores.network * w.network +
    normalizedScores.price * w.price
  );

  return {
    overall: parseFloat(overall.toFixed(2)),
    scores: {
      cpu: parseFloat(normalizedScores.cpu.toFixed(2)),
      memory: parseFloat(normalizedScores.memory.toFixed(2)),
      storage: parseFloat(normalizedScores.storage.toFixed(2)),
      network: parseFloat(normalizedScores.network.toFixed(2)),
      price: parseFloat(normalizedScores.price.toFixed(2))
    },
    rawScores: {
      cpu: parseFloat(cpuScore.toFixed(2)),
      memory: parseFloat(memoryScore.toFixed(2)),
      storage: parseFloat(storageScore.toFixed(2)),
      network: parseFloat(networkScore.toFixed(2))
    },
    dailyPrice: parseFloat(getVpsDailyPrice(vps).toFixed(2))
  };
}

/**
 * 计算 VPS 列表的性价比排名
 * @param {Array} vpsList - VPS 列表
 * @param {string} sortBy - 排序依据 (overall/cpu/memory/storage/network)
 * @returns {Array} 排序后的 VPS 列表
 */
function calculateRankings(vpsList, sortBy = 'overall') {
  const validVps = vpsList.filter(vps => vps.specs);
  
  if (validVps.length === 0) return [];

  const rawScoresArray = validVps.map(vps => ({
    vps,
    cpu: calculateCPUScore(vps),
    memory: calculateMemoryScore(vps),
    storage: calculateStorageScore(vps),
    network: calculateNetworkScore(vps),
    price: calculatePriceScore(vps),
    dailyPrice: getVpsDailyPrice(vps)
  }));

  const maxCpu = Math.max(...rawScoresArray.map(r => r.cpu), 1);
  const maxMemory = Math.max(...rawScoresArray.map(r => r.memory), 1);
  const maxStorage = Math.max(...rawScoresArray.map(r => r.storage), 1);
  const maxNetwork = Math.max(...rawScoresArray.map(r => r.network), 1);

  const defaultWeights = { cpu: 0.30, memory: 0.25, storage: 0.15, network: 0.10, price: 0.20 };

  const vpsWithScores = rawScoresArray.map(r => {
    const normalizedScores = {
      cpu: Math.min(100, (r.cpu / maxCpu) * 100),
      memory: Math.min(100, (r.memory / maxMemory) * 100),
      storage: Math.min(100, (r.storage / maxStorage) * 100),
      network: Math.min(100, (r.network / maxNetwork) * 100),
      price: r.price
    };

    const overall = (
      normalizedScores.cpu * defaultWeights.cpu +
      normalizedScores.memory * defaultWeights.memory +
      normalizedScores.storage * defaultWeights.storage +
      normalizedScores.network * defaultWeights.network +
      normalizedScores.price * defaultWeights.price
    );

    return {
      ...r.vps,
      scores: {
        overall: parseFloat(overall.toFixed(2)),
        cpu: parseFloat(normalizedScores.cpu.toFixed(2)),
        memory: parseFloat(normalizedScores.memory.toFixed(2)),
        storage: parseFloat(normalizedScores.storage.toFixed(2)),
        network: parseFloat(normalizedScores.network.toFixed(2)),
        price: parseFloat(normalizedScores.price.toFixed(2))
      },
      rawScores: {
        cpu: parseFloat(r.cpu.toFixed(2)),
        memory: parseFloat(r.memory.toFixed(2)),
        storage: parseFloat(r.storage.toFixed(2)),
        network: parseFloat(r.network.toFixed(2))
      },
      dailyPrice: parseFloat(r.dailyPrice.toFixed(2)),
      performance: {
        overall: parseFloat(overall.toFixed(2)),
        scores: {
          cpu: parseFloat(normalizedScores.cpu.toFixed(2)),
          memory: parseFloat(normalizedScores.memory.toFixed(2)),
          storage: parseFloat(normalizedScores.storage.toFixed(2)),
          network: parseFloat(normalizedScores.network.toFixed(2)),
          price: parseFloat(normalizedScores.price.toFixed(2))
        },
        rawScores: {
          cpu: parseFloat(r.cpu.toFixed(2)),
          memory: parseFloat(r.memory.toFixed(2)),
          storage: parseFloat(r.storage.toFixed(2)),
          network: parseFloat(r.network.toFixed(2))
        },
        dailyPrice: parseFloat(r.dailyPrice.toFixed(2))
      }
    };
  });

  vpsWithScores.sort((a, b) => {
    if (sortBy === 'overall') {
      return b.performance.overall - a.performance.overall;
    } else {
      return b.performance.scores[sortBy] - a.performance.scores[sortBy];
    }
  });

  vpsWithScores.forEach((vps, index) => {
    vps.rank = index + 1;
  });

  return vpsWithScores;
}

/**
 * 生成性价比报告
 * @param {Array} vpsList - VPS 列表
 * @returns {object} 性价比分析报告
 */
function generatePerformanceReport(vpsList) {
  const rankings = calculateRankings(vpsList, 'overall');

  if (rankings.length === 0) {
    return {
      total: 0,
      rankings: [],
      summary: null
    };
  }

  // 统计信息
  const avgScore = rankings.reduce((sum, vps) => sum + vps.performance.overall, 0) / rankings.length;
  const avgDailyPrice = rankings.reduce((sum, vps) => sum + vps.performance.dailyPrice, 0) / rankings.length;

  const bestOverall = rankings[0];
  const bestCPU = [...rankings].sort((a, b) => b.performance.scores.cpu - a.performance.scores.cpu)[0];
  const bestMemory = [...rankings].sort((a, b) => b.performance.scores.memory - a.performance.scores.memory)[0];
  const bestStorage = [...rankings].sort((a, b) => b.performance.scores.storage - a.performance.scores.storage)[0];
  const bestNetwork = [...rankings].sort((a, b) => b.performance.scores.network - a.performance.scores.network)[0];

  return {
    total: rankings.length,
    rankings,
    summary: {
      avgScore: parseFloat(avgScore.toFixed(2)),
      avgDailyPrice: parseFloat(avgDailyPrice.toFixed(2)),
      best: {
        overall: { name: bestOverall.name, score: bestOverall.performance.overall },
        cpu: { name: bestCPU.name, score: bestCPU.performance.scores.cpu },
        memory: { name: bestMemory.name, score: bestMemory.performance.scores.memory },
        storage: { name: bestStorage.name, score: bestStorage.performance.scores.storage },
        network: { name: bestNetwork.name, score: bestNetwork.performance.scores.network }
      }
    }
  };
}

module.exports = {
  getVpsCost,
  getDailyPrice,
  getVpsDailyPrice,
  calculateCPUScore,
  calculateMemoryScore,
  calculateStorageScore,
  calculateNetworkScore,
  calculatePriceScore,
  calculateOverallScore,
  calculateRankings,
  generatePerformanceReport
};
