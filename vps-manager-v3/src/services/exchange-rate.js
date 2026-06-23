// 汇率缓存系统
const exchangeRateCache = new Map();
const CACHE_TTL = 60 * 60 * 1000;
const FALLBACK_CACHE = new Map();

/**
 * 获取汇率（多源降级策略）
 */
async function fetchExchangeRate(from, to) {
  if (from === to) {
    return { rate: 1, source: 'identity' };
  }

  const cacheKey = `${from}-${to}`;
  const cached = exchangeRateCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return { rate: cached.rate, source: cached.source, fromCache: true };
  }

  const apiSources = [
    {
      name: 'exchangerate-api',
      url: `https://v6.exchangerate-api.com/v6/latest/${from}`,
      transform: (data) => data.conversion_rates[to]
    },
    {
      name: 'open.er-api',
      url: `https://open.er-api.com/v6/latest/${from}`,
      transform: (data) => data.rates[to]
    },
    {
      name: 'frankfurter',
      url: `https://api.frankfurter.app/latest?from=${from}&to=${to}`,
      transform: (data) => data.rates[to]
    }
  ];

  for (const source of apiSources) {
    try {
      const response = await fetch(source.url);
      if (!response.ok) continue;

      const data = await response.json();
      const rate = source.transform(data);

      if (rate && typeof rate === 'number' && rate > 0) {
        exchangeRateCache.set(cacheKey, { rate, source: source.name, timestamp: Date.now() });
        FALLBACK_CACHE.set(cacheKey, { rate, source: source.name });
        return { rate, source: source.name };
      }
    } catch (error) {
      console.log(`${source.name} API 失败:`, error.message);
    }
  }

  const fallback = FALLBACK_CACHE.get(cacheKey);
  if (fallback) {
    console.log(`使用降级缓存: ${cacheKey}`);
    return { rate: fallback.rate, source: fallback.source + ' (cached)', fromCache: true };
  }

  throw new Error(`无法获取汇率: ${from} -> ${to}`);
}

module.exports = {
  fetchExchangeRate
};
