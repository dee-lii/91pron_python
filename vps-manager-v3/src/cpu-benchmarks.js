/**
 * CPU 基准分数数据库
 * 数据来源：PassMark CPU Benchmarks
 * 更新时间：2026-01-13
 */

const CPU_BENCHMARKS = {
  // AMD EPYC 系列
  'AMD EPYC 7763': { singleThread: 3356, multiThread: 83490, cores: 64 },
  'AMD EPYC 7713': { singleThread: 2900, multiThread: 79000, cores: 64 },
  'AMD EPYC 7542': { singleThread: 2450, multiThread: 52000, cores: 32 },
  'AMD EPYC 7402': { singleThread: 2300, multiThread: 38000, cores: 24 },

  // Intel Xeon 系列
  'Intel Xeon E5-2696 v3': { singleThread: 1950, multiThread: 22000, cores: 18 },
  'Intel Xeon E5-2680 v4': { singleThread: 1850, multiThread: 24000, cores: 14 },
  'Intel Xeon E5-2690 v2': { singleThread: 1720, multiThread: 18000, cores: 10 },
  'Intel Xeon Gold 6254': { singleThread: 2500, multiThread: 38000, cores: 18 },
  'Intel Xeon Platinum 8375C': { singleThread: 3200, multiThread: 55000, cores: 32 },

  // AMD Ryzen 系列
  'AMD Ryzen 9 5950X': { singleThread: 3500, multiThread: 46000, cores: 16 },
  'AMD Ryzen 9 5900X': { singleThread: 3600, multiThread: 39500, cores: 12 },
  'AMD Ryzen 7 5800X': { singleThread: 3500, multiThread: 28000, cores: 8 },
  'AMD Ryzen 5 5600X': { singleThread: 3400, multiThread: 22000, cores: 6 },

  // Intel Core 系列
  'Intel Core i9-12900K': { singleThread: 4000, multiThread: 41000, cores: 16 },
  'Intel Core i7-12700K': { singleThread: 3800, multiThread: 35000, cores: 12 },
  'Intel Core i5-12600K': { singleThread: 3700, multiThread: 27000, cores: 10 },

  // 常见 VPS CPU
  'Intel Xeon': { singleThread: 2000, multiThread: 8000, cores: 4 },  // 通用
  'AMD EPYC': { singleThread: 2500, multiThread: 10000, cores: 4 },   // 通用
  'Virtual CPU': { singleThread: 1500, multiThread: 6000, cores: 2 }  // 虚拟 CPU
};

/**
 * 根据 CPU 型号获取基准分数
 * @param {string} cpuModel - CPU 型号
 * @param {number} cores - 核心数
 * @returns {object} 基准分数信息
 */
function getCPUBenchmark(cpuModel, cores = 1) {
  // 完全匹配
  if (CPU_BENCHMARKS[cpuModel]) {
    return CPU_BENCHMARKS[cpuModel];
  }

  // 模糊匹配
  const normalizedModel = cpuModel.toLowerCase();

  for (const [key, value] of Object.entries(CPU_BENCHMARKS)) {
    if (normalizedModel.includes(key.toLowerCase())) {
      return value;
    }
  }

  // EPYC 系列模糊匹配
  if (normalizedModel.includes('epyc')) {
    return { singleThread: 2500, multiThread: 10000 * cores, cores };
  }

  // Xeon 系列模糊匹配
  if (normalizedModel.includes('xeon')) {
    return { singleThread: 2000, multiThread: 8000 * cores, cores };
  }

  // Ryzen 系列模糊匹配
  if (normalizedModel.includes('ryzen')) {
    return { singleThread: 3000, multiThread: 15000 * cores, cores };
  }

  // 默认虚拟 CPU
  return { singleThread: 1500, multiThread: 3000 * cores, cores };
}

/**
 * 获取所有支持的 CPU 型号列表
 * @returns {Array} CPU 型号列表
 */
function getSupportedCPUs() {
  return Object.keys(CPU_BENCHMARKS).sort();
}

/**
 * 添加自定义 CPU 基准分数
 * @param {string} model - CPU 型号
 * @param {number} singleThread - 单线程分数
 * @param {number} multiThread - 多线程分数
 * @param {number} cores - 核心数
 */
function addCustomCPU(model, singleThread, multiThread, cores) {
  CPU_BENCHMARKS[model] = { singleThread, multiThread, cores };
}

module.exports = {
  CPU_BENCHMARKS,
  getCPUBenchmark,
  getSupportedCPUs,
  addCustomCPU
};
