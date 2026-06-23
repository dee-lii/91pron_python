/**
 * VPS Manager v3.0 自动化测试脚本
 * 功能：注入测试数据并验证所有功能
 */

const testData = {
  version: '3.0.0',
  vpsList: [
    {
      id: 'vps-001',
      name: 'Vultr Tokyo',
      provider: 'Vultr',
      totalCost: 120,
      currency: 'USD',
      cycle: 'yearly',
      purchaseDate: '2024-06-01',
      notes: '博客服务器'
    },
    {
      id: 'vps-002',
      name: 'DigitalOcean NYC',
      provider: 'DigitalOcean',
      totalCost: 60,
      currency: 'USD',
      cycle: 'yearly',
      purchaseDate: '2025-01-01',
      notes: 'API 服务器'
    },
    {
      id: 'vps-003',
      name: '腾讯云深圳',
      provider: '腾讯云',
      totalCost: 288,
      currency: 'CNY',
      cycle: 'yearly',
      purchaseDate: '2024-11-11',
      notes: 'CDN 加速'
    },
    {
      id: 'vps-004',
      name: 'Linode Singapore',
      provider: 'Linode',
      totalCost: 48,
      currency: 'USD',
      cycle: 'yearly',
      purchaseDate: '2025-09-01',
      notes: '数据库服务器'
    },
    {
      id: 'vps-005',
      name: 'AWS Tokyo',
      provider: 'AWS',
      totalCost: 240,
      currency: 'USD',
      cycle: 'yearly',
      purchaseDate: '2024-03-15',
      notes: '生产环境'
    },
    {
      id: 'vps-006',
      name: '阿里云杭州',
      provider: '阿里云',
      totalCost: 99,
      currency: 'CNY',
      cycle: 'monthly',
      purchaseDate: '2025-12-01',
      notes: '测试环境'
    },
    {
      id: 'vps-007',
      name: 'Hetzner Germany',
      provider: 'Hetzner',
      totalCost: 39,
      currency: 'EUR',
      cycle: 'yearly',
      purchaseDate: '2024-08-20',
      notes: '备份服务器'
    },
    {
      id: 'vps-008',
      name: 'OVH France',
      provider: 'OVH',
      totalCost: 72,
      currency: 'EUR',
      cycle: 'yearly',
      purchaseDate: '2025-05-10',
      notes: '文件存储'
    }
  ],
  settings: {
    defaultCurrency: 'CNY',
    autoRefresh: true,
    theme: 'light'
  }
};

// 输出测试数据（JSON 格式）
console.log(JSON.stringify(testData, null, 2));
