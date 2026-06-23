#!/bin/bash

echo "🔐 开始安全验证测试..."
echo "================================"

BASE_URL="http://localhost:3000"
PASS_COUNT=0
FAIL_COUNT=0

# 测试1: 公开API应该不存在
echo "📝 测试1: 公开API已删除"
response=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/api/public/servers)
if [ "$response" == "404" ]; then
  echo "✅ 通过: 公开API已删除 (HTTP $response)"
  ((PASS_COUNT++))
else
  echo "❌ 失败: 公开API仍可访问 (HTTP $response)"
  ((FAIL_COUNT++))
fi

# 测试2: 未认证访问应该被拒绝
echo -e "\n📝 测试2: 认证保护"
response=$(curl -s $BASE_URL/api/vps | jq -r '.error // empty')
if [[ "$response" == "未登录" ]]; then
  echo "✅ 通过: 需要认证的API正确拒绝未登录请求"
  ((PASS_COUNT++))
else
  echo "❌ 失败: 认证保护无效 (响应: $response)"
  ((FAIL_COUNT++))
fi

# 测试3: 环境变量检查
echo -e "\n📝 测试3: 环境变量配置"
if [ -z "$JWT_SECRET" ]; then
  echo "❌ 失败: JWT_SECRET 未设置"
  ((FAIL_COUNT++))
else
  echo "✅ 通过: JWT_SECRET 已设置 (长度: ${#JWT_SECRET})"
  ((PASS_COUNT++))
fi

# 测试4: 文件权限检查
echo -e "\n📝 测试4: 文件权限"
db_perm=$(stat -f "%Sp" data/vps-manager.db 2>/dev/null || stat -c "%A" data/vps-manager.db 2>/dev/null)
if [[ "$db_perm" == "-rw-------" ]]; then
  echo "✅ 通过: 数据库文件权限正确 (600)"
  ((PASS_COUNT++))
else
  echo "❌ 失败: 数据库文件权限不正确 ($db_perm)"
  ((FAIL_COUNT++))
fi

# 测试5: 数据库中不应包含哪吒Token
echo -e "\n📝 测试5: 敏感数据检查"
nezha_in_db=$(sqlite3 data/vps-manager.db "SELECT COUNT(*) FROM config WHERE key='nezha';" 2>/dev/null || echo "0")
if [ "$nezha_in_db" == "0" ]; then
  echo "✅ 通过: 数据库中无哪吒凭据"
  ((PASS_COUNT++))
else
  echo "❌ 失败: 数据库中仍存在哪吒凭据"
  ((FAIL_COUNT++))
fi

# 测试6: 安全响应头检查
echo -e "\n📝 测试6: 安全响应头"
headers=$(curl -s -I $BASE_URL/api/health 2>/dev/null)
if echo "$headers" | grep -qi "X-Content-Type-Options"; then
  echo "✅ 通过: 安全响应头已启用"
  ((PASS_COUNT++))
else
  echo "⚠️  警告: 安全响应头可能未生效"
  ((FAIL_COUNT++))
fi

echo -e "\n================================"
echo "📊 测试结果汇总"
echo "✅ 通过: $PASS_COUNT 个"
echo "❌ 失败: $FAIL_COUNT 个"
echo "================================"

if [ $FAIL_COUNT -eq 0 ]; then
  echo "🎉 所有测试通过！安全修复已完成。"
  exit 0
else
  echo "⚠️  还有 $FAIL_COUNT 个问题需要修复"
  exit 1
fi
