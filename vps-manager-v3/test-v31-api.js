/**
 * VPS Manager v3.1 - 后端 API 测试脚本
 * 测试哪吒集成和性价比计算功能
 */

const http = require('http');

const BASE_URL = 'http://localhost:3000';

// 工具函数：HTTP 请求
function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            statusCode: res.statusCode,
            data: res.headers['content-type']?.includes('application/json')
              ? JSON.parse(data)
              : data
          });
        } catch (e) {
          resolve({ statusCode: res.statusCode, data });
        }
      });
    });

    req.on('error', reject);

    if (options.body) {
      req.write(JSON.stringify(options.body));
    }

    req.end();
  });
}

// 测试数据：带完整配置的 VPS 列表
const testVPSList = [
  {
    id: 'vps-001',
    name: 'Hetzner Germany CPX31',
    provider: 'Hetzner',
    totalCost: 39,
    currency: 'EUR',
    cycle: 'yearly',
    purchaseDate: '2025-08-20',
    notes: '性价比之王',
    specs: {
      cpu: {
        model: 'AMD EPYC 7542',
        cores: 4,
        threads: 4
      },
      memory: {
        size: 8,
        type: 'DDR4'
      },
      storage: {
        size: 160,
        type: 'NVMe SSD'
      },
      network: {
        bandwidth: 1000,
        traffic: 20000
      }
    }
  },
  {
    id: 'vps-002',
    name: 'Vultr Tokyo High Freq',
    provider: 'Vultr',
    totalCost: 120,
    currency: 'USD',
    cycle: 'yearly',
    purchaseDate: '2025-06-01',
    notes: '高性能计算',
    specs: {
      cpu: {
        model: 'AMD EPYC 7763',
        cores: 4,
        threads: 8
      },
      memory: {
        size: 8,
        type: 'DDR4'
      },
      storage: {
        size: 128,
        type: 'NVMe SSD'
      },
      network: {
        bandwidth: 1000,
        traffic: 3000
      }
    }
  },
  {
    id: 'vps-003',
    name: 'AWS EC2 t3.medium',
    provider: 'AWS',
    totalCost: 240,
    currency: 'USD',
    cycle: 'yearly',
    purchaseDate: '2025-03-15',
    notes: '生产环境',
    specs: {
      cpu: {
        model: 'Intel Xeon Platinum 8375C',
        cores: 2,
        threads: 4
      },
      memory: {
        size: 4,
        type: 'DDR4'
      },
      storage: {
        size: 50,
        type: 'SSD'
      },
      network: {
        bandwidth: 5000,
        traffic: 1000
      }
    }
  },
  {
    id: 'vps-004',
    name: 'DigitalOcean NYC',
    provider: 'DigitalOcean',
    totalCost: 60,
    currency: 'USD',
    cycle: 'yearly',
    purchaseDate: '2025-10-01',
    notes: 'API 服务器',
    specs: {
      cpu: {
        model: 'Intel Xeon',
        cores: 2,
        threads: 2
      },
      memory: {
        size: 4,
        type: 'DDR4'
      },
      storage: {
        size: 80,
        type: 'SSD'
      },
      network: {
        bandwidth: 1000,
        traffic: 3000
      }
    }
  },
  {
    id: 'vps-005',
    name: '腾讯云轻量服务器',
    provider: '腾讯云',
    totalCost: 288,
    currency: 'CNY',
    cycle: 'yearly',
    purchaseDate: '2025-11-11',
    notes: 'CDN 加速节点',
    specs: {
      cpu: {
        model: 'AMD EPYC',
        cores: 2,
        threads: 2
      },
      memory: {
        size: 4,
        type: 'DDR4'
      },
      storage: {
        size: 100,
        type: 'SSD'
      },
      network: {
        bandwidth: 5,
        traffic: 2000
      }
    }
  },
  {
    id: 'vps-006',
    name: 'OVH VPS SSD',
    provider: 'OVH',
    totalCost: 72,
    currency: 'EUR',
    cycle: 'yearly',
    purchaseDate: '2025-05-10',
    notes: '文件存储',
    specs: {
      cpu: {
        model: 'Intel Xeon E5-2680 v4',
        cores: 2,
        threads: 4
      },
      memory: {
        size: 4,
        type: 'DDR4'
      },
      storage: {
        size: 200,
        type: 'SSD'
      },
      network: {
        bandwidth: 100,
        traffic: 0
      }
    }
  },
  {
    id: 'vps-007',
    name: 'Linode Singapore Dedicated',
    provider: 'Linode',
    totalCost: 48,
    currency: 'USD',
    cycle: 'yearly',
    purchaseDate: '2025-09-15',
    notes: '数据库服务器',
    specs: {
      cpu: {
        model: 'AMD EPYC 7713',
        cores: 2,
        threads: 4
      },
      memory: {
        size: 8,
        type: 'DDR4'
      },
      storage: {
        size: 160,
        type: 'NVMe SSD'
      },
      network: {
        bandwidth: 1000,
        traffic: 5000
      }
    }
  }
];

// 主测试函数
async function runTests() {
  console.log('\n🧪 VPS Manager v3.1 后端 API 完整测试\n');
  console.log('='.repeat(80));

  let passCount = 0;
  let totalCount = 0;

  // 测试 1: CPU 型号列表
  try {
    totalCount++;
    console.log('\n📍 测试 1: 获取 CPU 型号列表');
    const result = await httpRequest(`${BASE_URL}/api/cpu/models`);

    if (result.statusCode === 200 && result.data.success) {
      const models = result.data.data;
      console.log(`✅ 成功 - 支持 ${models.length} 种 CPU 型号`);
      console.log(`   前5个: ${models.slice(0, 5).join(', ')}`);
      passCount++;
    } else {
      throw new Error('获取失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 2: 哪吒配置（获取）
  try {
    totalCount++;
    console.log('\n📍 测试 2: 获取哪吒配置');
    const result = await httpRequest(`${BASE_URL}/api/nezha/config`);

    if (result.statusCode === 200 && result.data.success) {
      console.log('✅ 成功 - 配置获取正常');
      console.log(`   API URL: ${result.data.data.apiUrl || '(未配置)'}`);
      console.log(`   Token: ${result.data.data.token || '(未配置)'}`);
      passCount++;
    } else {
      throw new Error('获取失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 3: 哪吒配置（设置）
  try {
    totalCount++;
    console.log('\n📍 测试 3: 设置哪吒配置');
    const result = await httpRequest(`${BASE_URL}/api/nezha/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: {
        apiUrl: 'https://nezha.example.com',
        token: 'test-token-12345',
        autoSync: true,
        syncInterval: 3600
      }
    });

    if (result.statusCode === 200 && result.data.success) {
      console.log('✅ 成功 - 配置已保存');
      console.log(`   消息: ${result.data.message}`);
      passCount++;
    } else {
      throw new Error('设置失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 4: 性价比排行榜（综合排名）
  try {
    totalCount++;
    console.log('\n📍 测试 4: 性价比排行榜 - 综合排名');
    const result = await httpRequest(`${BASE_URL}/api/performance/rankings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { vpsList: testVPSList, sortBy: 'overall' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const rankings = result.data.data;
      console.log(`✅ 成功 - 生成 ${rankings.length} 个 VPS 的排名`);
      console.log('\n   🏆 Top 3 综合性价比:');
      rankings.slice(0, 3).forEach((vps, i) => {
        const medal = ['🥇', '🥈', '🥉'][i];
        console.log(`   ${medal} ${i + 1}. ${vps.name}`);
        console.log(`      综合得分: ${vps.performance.overall}`);
        console.log(`      日价格: ${vps.performance.dailyPrice.toFixed(2)} ${vps.currency}`);
        console.log(`      配置: ${vps.specs.cpu.cores}C ${vps.specs.memory.size}G ${vps.specs.storage.size}GB`);
      });
      passCount++;
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 5: 性价比排行榜（CPU 排名）
  try {
    totalCount++;
    console.log('\n📍 测试 5: 性价比排行榜 - CPU 性价比');
    const result = await httpRequest(`${BASE_URL}/api/performance/rankings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { vpsList: testVPSList, sortBy: 'cpu' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const rankings = result.data.data;
      console.log(`✅ 成功 - CPU 性价比排名`);
      console.log('\n   🏆 Top 3 CPU 性价比:');
      rankings.slice(0, 3).forEach((vps, i) => {
        console.log(`   ${i + 1}. ${vps.name} - CPU得分: ${vps.performance.scores.cpu}`);
        console.log(`      CPU: ${vps.specs.cpu.model} (${vps.specs.cpu.cores}核)`);
        console.log(`      原始得分: ${vps.performance.rawScores.cpu.toFixed(0)}`);
      });
      passCount++;
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 6: 性价比排行榜（内存排名）
  try {
    totalCount++;
    console.log('\n📍 测试 6: 性价比排行榜 - 内存性价比');
    const result = await httpRequest(`${BASE_URL}/api/performance/rankings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { vpsList: testVPSList, sortBy: 'memory' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const rankings = result.data.data;
      console.log(`✅ 成功 - 内存性价比排名`);
      console.log('\n   🏆 Top 3 内存性价比:');
      rankings.slice(0, 3).forEach((vps, i) => {
        console.log(`   ${i + 1}. ${vps.name} - 内存得分: ${vps.performance.scores.memory}`);
        console.log(`      内存: ${vps.specs.memory.size}GB ${vps.specs.memory.type}`);
        console.log(`      日价格: ${vps.performance.dailyPrice.toFixed(2)} ${vps.currency}`);
      });
      passCount++;
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试 7: 性价比报告
  try {
    totalCount++;
    console.log('\n📍 测试 7: 生成性价比完整报告');
    const result = await httpRequest(`${BASE_URL}/api/performance/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { vpsList: testVPSList }
    });

    if (result.statusCode === 200 && result.data.success) {
      const report = result.data.data;
      console.log(`✅ 成功 - 报告生成完成`);
      console.log(`\n   📊 总体统计:`);
      console.log(`      VPS 总数: ${report.total}`);
      console.log(`      平均综合得分: ${report.summary.avgScore}`);
      console.log(`      平均日价格: ${report.summary.avgDailyPrice.toFixed(2)}`);
      console.log(`\n   🏆 各维度最佳:`);
      console.log(`      综合: ${report.summary.best.overall.name} (${report.summary.best.overall.score})`);
      console.log(`      CPU: ${report.summary.best.cpu.name} (${report.summary.best.cpu.score})`);
      console.log(`      内存: ${report.summary.best.memory.name} (${report.summary.best.memory.score})`);
      console.log(`      存储: ${report.summary.best.storage.name} (${report.summary.best.storage.score})`);
      console.log(`      网络: ${report.summary.best.network.name} (${report.summary.best.network.score})`);
      passCount++;
    } else {
      throw new Error('生成失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
  }

  // 测试总结
  console.log('\n' + '='.repeat(80));
  console.log('\n📊 测试总结\n');
  console.log(`总测试数: ${totalCount}`);
  console.log(`✅ 通过: ${passCount}`);
  console.log(`❌ 失败: ${totalCount - passCount}`);
  console.log(`通过率: ${((passCount / totalCount) * 100).toFixed(2)}%`);

  console.log('\n' + '='.repeat(80));
  console.log('\n💾 测试数据已生成，可用于前端开发测试\n');
  console.log('测试数据保存在: test-vps-with-specs.json');
  console.log('使用命令查看: cat test-vps-with-specs.json\n');

  return { passCount, totalCount, testData: testVPSList };
}

// 执行测试
runTests().then(({ passCount, totalCount, testData }) => {
  // 保存测试数据到文件
  const fs = require('fs');
  fs.writeFileSync(
    'test-vps-with-specs.json',
    JSON.stringify({ vpsList: testData }, null, 2)
  );
  console.log('✅ 测试数据已保存到 test-vps-with-specs.json\n');

  if (passCount === totalCount) {
    console.log('🎉 所有测试通过！v3.1 后端功能完全正常！\n');
    process.exit(0);
  } else {
    console.log('⚠️  部分测试失败，请检查错误信息\n');
    process.exit(1);
  }
}).catch(error => {
  console.error('❌ 测试执行失败:', error);
  process.exit(1);
});
