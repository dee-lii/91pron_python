/**
 * 哪吒配置管理 - 优先从环境变量读取
 * 安全策略: 敏感信息不存储在数据库中
 */

function getNezhaConfig() {
  // 优先从环境变量读取
  if (process.env.NEZHA_API_URL && process.env.NEZHA_TOKEN) {
    return {
      apiUrl: process.env.NEZHA_API_URL,
      token: process.env.NEZHA_TOKEN,
      autoSync: process.env.NEZHA_AUTO_SYNC === 'true',
      syncInterval: parseInt(process.env.NEZHA_SYNC_INTERVAL || '3600', 10)
    };
  }

  // 降级到数据库读取 (用于迁移期，不推荐)
  const { ConfigDB } = require('../database');
  const dbConfig = ConfigDB.get('nezha');

  if (!dbConfig || !dbConfig.token) {
    console.warn('⚠️  哪吒配置未设置，请配置环境变量:');
    console.warn('   NEZHA_API_URL=https://your-nezha-domain.com');
    console.warn('   NEZHA_TOKEN=your_token_here');
    return {
      apiUrl: '',
      token: '',
      autoSync: false,
      syncInterval: 3600
    };
  }

  // 如果从数据库读取到配置，警告用户迁移
  console.warn('⚠️  检测到数据库中存储了哪吒配置，建议迁移到环境变量');
  console.warn('   执行: sqlite3 data/vps-manager.db "DELETE FROM config WHERE key=\'nezha\';"');

  return dbConfig;
}

module.exports = { getNezhaConfig };
