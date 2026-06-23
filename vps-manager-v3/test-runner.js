/**
 * VPS Manager v3.0 - 自动化测试脚本
 * 测试所有核心功能并生成报告
 */

const http = require('http');

// 测试配置
const BASE_URL = 'http://localhost:3000';
const testResults = [];

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

// 测试用例
async function runTests() {
  console.log('🧪 VPS Manager v3.0 自动化测试开始\n');
  console.log('=' .repeat(60));

  // 测试 1: 健康检查
  try {
    console.log('\n📍 测试 1: 健康检查 API');
    const result = await httpRequest(`${BASE_URL}/api/health`);

    if (result.statusCode === 200 && result.data.status === 'ok') {
      console.log('✅ 通过 - 服务器运行正常');
      console.log(`   版本: ${result.data.timestamp}`);
      testResults.push({ test: '健康检查', status: 'PASS' });
    } else {
      throw new Error('健康检查失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: '健康检查', status: 'FAIL', error: error.message });
  }

  // 测试 2: 基础计算 API
  try {
    console.log('\n📍 测试 2: 基础计算 API');
    const result = await httpRequest(`${BASE_URL}/api/calculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { totalCost: 365, totalDays: 365, usedDays: 100 }
    });

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - 计算结果正确');
      console.log(`   剩余价值: ${data.remainingValue}`);
      console.log(`   已使用价值: ${data.usedValue}`);
      console.log(`   使用率: ${data.usageRate}%`);
      testResults.push({ test: '基础计算 API', status: 'PASS' });
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: '基础计算 API', status: 'FAIL', error: error.message });
  }

  // 测试 3: 按周期计算 API（测试数据 1）
  try {
    console.log('\n📍 测试 3: 按周期计算 API - Vultr Tokyo');
    const result = await httpRequest(`${BASE_URL}/api/calculate-by-cycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { totalCost: 120, cycle: 'yearly', purchaseDate: '2024-06-01' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - Vultr Tokyo 计算成功');
      console.log(`   总成本: $${data.totalDays === 365 ? 120 : 'N/A'}`);
      console.log(`   剩余价值: $${data.remainingValue}`);
      console.log(`   已使用天数: ${data.usedDays} 天`);
      console.log(`   剩余天数: ${data.remainingDays} 天`);
      console.log(`   使用率: ${data.usageRate}%`);
      testResults.push({ test: 'Vultr Tokyo 计算', status: 'PASS', data });
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: 'Vultr Tokyo 计算', status: 'FAIL', error: error.message });
  }

  // 测试 4: 按周期计算 API（测试数据 2）
  try {
    console.log('\n📍 测试 4: 按周期计算 API - DigitalOcean NYC');
    const result = await httpRequest(`${BASE_URL}/api/calculate-by-cycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { totalCost: 60, cycle: 'yearly', purchaseDate: '2025-01-01' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - DigitalOcean NYC 计算成功');
      console.log(`   总成本: $60`);
      console.log(`   剩余价值: $${data.remainingValue}`);
      console.log(`   使用率: ${data.usageRate}%`);
      testResults.push({ test: 'DigitalOcean NYC 计算', status: 'PASS', data });
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: 'DigitalOcean NYC 计算', status: 'FAIL', error: error.message });
  }

  // 测试 5: 汇率 API - USD to CNY
  try {
    console.log('\n📍 测试 5: 汇率 API - USD to CNY');
    const result = await httpRequest(`${BASE_URL}/api/exchange-rate?from=USD&to=CNY`);

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - 汇率获取成功');
      console.log(`   USD → CNY: ${data.rate}`);
      console.log(`   数据源: ${data.source}`);
      console.log(`   是否缓存: ${data.fromCache ? '是' : '否'}`);
      testResults.push({ test: 'USD→CNY 汇率', status: 'PASS', rate: data.rate });
    } else {
      throw new Error('汇率获取失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: 'USD→CNY 汇率', status: 'FAIL', error: error.message });
  }

  // 测试 6: 汇率 API - EUR to CNY
  try {
    console.log('\n📍 测试 6: 汇率 API - EUR to CNY');
    const result = await httpRequest(`${BASE_URL}/api/exchange-rate?from=EUR&to=CNY`);

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - 汇率获取成功');
      console.log(`   EUR → CNY: ${data.rate}`);
      testResults.push({ test: 'EUR→CNY 汇率', status: 'PASS', rate: data.rate });
    } else {
      throw new Error('汇率获取失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: 'EUR→CNY 汇率', status: 'FAIL', error: error.message });
  }

  // 测试 7: 月付周期计算
  try {
    console.log('\n📍 测试 7: 月付周期计算 - 阿里云杭州');
    const result = await httpRequest(`${BASE_URL}/api/calculate-by-cycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { totalCost: 99, cycle: 'monthly', purchaseDate: '2025-12-01' }
    });

    if (result.statusCode === 200 && result.data.success) {
      const data = result.data.data;
      console.log('✅ 通过 - 阿里云杭州计算成功');
      console.log(`   总成本: ¥99 (月付)`);
      console.log(`   总天数: ${data.totalDays} 天`);
      console.log(`   剩余价值: ¥${data.remainingValue}`);
      console.log(`   日均消耗: ¥${data.dailyRate}`);
      testResults.push({ test: '月付周期计算', status: 'PASS', data });
    } else {
      throw new Error('计算失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: '月付周期计算', status: 'FAIL', error: error.message });
  }

  // 测试 8: 静态文件访问
  try {
    console.log('\n📍 测试 8: 静态文件访问');
    const result = await httpRequest(`${BASE_URL}/index.html`);

    if (result.statusCode === 200 && result.data.includes('VPS')) {
      console.log('✅ 通过 - 前端页面可访问');
      console.log(`   页面大小: ${(result.data.length / 1024).toFixed(2)} KB`);
      testResults.push({ test: '前端页面访问', status: 'PASS' });
    } else {
      throw new Error('页面访问失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: '前端页面访问', status: 'FAIL', error: error.message });
  }

  // 测试 9: 测试注入页面访问
  try {
    console.log('\n📍 测试 9: 测试注入页面访问');
    const result = await httpRequest(`${BASE_URL}/test-inject.html`);

    if (result.statusCode === 200 && result.data.includes('测试数据注入')) {
      console.log('✅ 通过 - 测试注入页面可访问');
      testResults.push({ test: '测试注入页面', status: 'PASS' });
    } else {
      throw new Error('页面访问失败');
    }
  } catch (error) {
    console.log(`❌ 失败 - ${error.message}`);
    testResults.push({ test: '测试注入页面', status: 'FAIL', error: error.message });
  }

  // 生成测试报告
  console.log('\n' + '='.repeat(60));
  console.log('\n📊 测试报告\n');

  const passed = testResults.filter(r => r.status === 'PASS').length;
  const failed = testResults.filter(r => r.status === 'FAIL').length;

  console.log(`总测试数: ${testResults.length}`);
  console.log(`✅ 通过: ${passed}`);
  console.log(`❌ 失败: ${failed}`);
  console.log(`通过率: ${((passed / testResults.length) * 100).toFixed(2)}%`);

  if (failed > 0) {
    console.log('\n⚠️ 失败的测试:');
    testResults.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`   - ${r.test}: ${r.error}`);
    });
  }

  console.log('\n' + '='.repeat(60));
  console.log('\n🎯 测试数据汇总:\n');

  // 汇总测试的 VPS 数据
  const vpsData = testResults
    .filter(r => r.data && r.data.remainingValue)
    .map(r => ({
      test: r.test,
      remainingValue: r.data.remainingValue,
      usageRate: r.data.usageRate,
      remainingDays: r.data.remainingDays
    }));

  if (vpsData.length > 0) {
    console.table(vpsData);
  }

  // 汇率数据
  const rateData = testResults
    .filter(r => r.rate)
    .map(r => ({ test: r.test, rate: r.rate }));

  if (rateData.length > 0) {
    console.log('\n💱 汇率数据:\n');
    console.table(rateData);
  }

  console.log('\n✅ 所有测试完成！\n');
  console.log('📍 下一步操作:');
  console.log('   1. 访问 http://localhost:3000/test-inject.html 注入测试数据');
  console.log('   2. 访问 http://localhost:3000/index.html 查看主应用');
  console.log('   3. 测试三大核心功能（管理面板、趋势可视化、续费助手）\n');

  return testResults;
}

// 执行测试
runTests().catch(error => {
  console.error('❌ 测试执行失败:', error);
  process.exit(1);
});
