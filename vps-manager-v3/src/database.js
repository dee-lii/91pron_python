const Database = require('better-sqlite3');
const path = require('path');
const logger = require('./lib/logger');
const fs = require('fs');

const DB_PATH = process.env.NODE_ENV === 'test' 
  ? (process.env.DB_PATH || path.join(__dirname, '..', 'data', 'test.db'))
  : path.join(__dirname, '..', 'data', 'vps-manager.db');

const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// 设置数据库文件权限为 600 (仅所有者可读写)
try {
  fs.chmodSync(DB_PATH, 0o600);

  // 同时设置 WAL 和 SHM 文件的权限
  const walPath = DB_PATH + '-wal';
  const shmPath = DB_PATH + '-shm';

  if (fs.existsSync(walPath)) {
    fs.chmodSync(walPath, 0o600);
  }
  if (fs.existsSync(shmPath)) {
    fs.chmodSync(shmPath, 0o600);
  }

  logger.info('✅ 数据库文件权限已设置为 600');
} catch (error) {
  logger.warn(`⚠️  无法设置数据库文件权限: ${error.message}`);
}

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS vps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT,
    price REAL,
    currency TEXT DEFAULT 'CNY',
    cycle TEXT,
    purchase_date TEXT,
    notes TEXT,
    location TEXT,
    ip TEXT,
    specs TEXT,
    nezha TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT DEFAULT '#3b82f6',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS vps_tags (
    vps_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (vps_id, tag_id),
    FOREIGN KEY (vps_id) REFERENCES vps(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_vps_tags_vps_id ON vps_tags(vps_id);
  CREATE INDEX IF NOT EXISTS idx_vps_tags_tag_id ON vps_tags(tag_id);

  CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_type TEXT NOT NULL CHECK(period_type IN ('monthly', 'yearly')),
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'CNY',
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_active INTEGER DEFAULT 1,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_budgets_period_type ON budgets(period_type);
  CREATE INDEX IF NOT EXISTS idx_budgets_is_active ON budgets(is_active);

  CREATE TABLE IF NOT EXISTS health_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_type TEXT NOT NULL CHECK(check_type IN ('scheduled', 'manual')),
    total_vps INTEGER NOT NULL,
    avg_score REAL NOT NULL,
    healthy_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    down_count INTEGER DEFAULT 0,
    problematic_vps TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_health_history_created_at ON health_history(created_at);

  CREATE TABLE IF NOT EXISTS cost_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    total_monthly_cost REAL NOT NULL,
    total_yearly_cost REAL NOT NULL,
    vps_count INTEGER NOT NULL,
    currency TEXT DEFAULT 'CNY',
    by_provider TEXT,
    by_cycle TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_cost_history_period ON cost_history(period);
  CREATE INDEX IF NOT EXISTS idx_cost_history_created_at ON cost_history(created_at);

  CREATE TABLE IF NOT EXISTS budget_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_id INTEGER NOT NULL,
    period_type TEXT NOT NULL,
    budget_amount REAL NOT NULL,
    used_amount REAL NOT NULL,
    remaining_amount REAL NOT NULL,
    usage_percentage REAL NOT NULL,
    alert_level TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (budget_id) REFERENCES budgets(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_budget_history_budget_id ON budget_history(budget_id);
  CREATE INDEX IF NOT EXISTS idx_budget_history_created_at ON budget_history(created_at);
`);

const userQueries = {
  getByUsername: db.prepare('SELECT * FROM users WHERE username = ?'),
  create: db.prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)'),
  updatePassword: db.prepare('UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?'),
  count: db.prepare('SELECT COUNT(*) as count FROM users')
};

const vpsQueries = {
  getAll: db.prepare('SELECT * FROM vps ORDER BY created_at DESC'),
  getById: db.prepare('SELECT * FROM vps WHERE id = ?'),
  create: db.prepare(`
    INSERT INTO vps (id, name, provider, price, currency, cycle, purchase_date, notes, location, ip, specs, nezha)
    VALUES (@id, @name, @provider, @price, @currency, @cycle, @purchase_date, @notes, @location, @ip, @specs, @nezha)
  `),
  update: db.prepare(`
    UPDATE vps SET 
      name = @name, provider = @provider, price = @price, currency = @currency,
      cycle = @cycle, purchase_date = @purchase_date, notes = @notes,
      location = @location, ip = @ip, specs = @specs, nezha = @nezha,
      updated_at = CURRENT_TIMESTAMP
    WHERE id = @id
  `),
  delete: db.prepare('DELETE FROM vps WHERE id = ?'),
  deleteAll: db.prepare('DELETE FROM vps')
};

const configQueries = {
  get: db.prepare('SELECT value FROM config WHERE key = ?'),
  set: db.prepare('INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)')
};

const tagQueries = {
  getAll: db.prepare('SELECT * FROM tags ORDER BY name ASC'),
  getById: db.prepare('SELECT * FROM tags WHERE id = ?'),
  getByName: db.prepare('SELECT * FROM tags WHERE name = ?'),
  create: db.prepare('INSERT INTO tags (name, color) VALUES (?, ?)'),
  update: db.prepare('UPDATE tags SET name = ?, color = ? WHERE id = ?'),
  delete: db.prepare('DELETE FROM tags WHERE id = ?'),

  // VPS标签关联查询
  getVpsTags: db.prepare(`
    SELECT t.* FROM tags t
    INNER JOIN vps_tags vt ON t.id = vt.tag_id
    WHERE vt.vps_id = ?
    ORDER BY t.name ASC
  `),

  getTagVps: db.prepare(`
    SELECT v.* FROM vps v
    INNER JOIN vps_tags vt ON v.id = vt.vps_id
    WHERE vt.tag_id = ?
    ORDER BY v.created_at DESC
  `),

  addVpsTag: db.prepare('INSERT OR IGNORE INTO vps_tags (vps_id, tag_id) VALUES (?, ?)'),
  removeVpsTag: db.prepare('DELETE FROM vps_tags WHERE vps_id = ? AND tag_id = ?'),
  removeAllVpsTags: db.prepare('DELETE FROM vps_tags WHERE vps_id = ?'),

  // 批量操作
  getVpsIdsByTags: db.prepare(`
    SELECT DISTINCT vps_id FROM vps_tags WHERE tag_id IN (
      SELECT id FROM tags WHERE name IN (${Array(10).fill('?').join(',')})
    )
  `)
};

const budgetQueries = {
  getAll: db.prepare('SELECT * FROM budgets ORDER BY created_at DESC'),
  getById: db.prepare('SELECT * FROM budgets WHERE id = ?'),
  getActive: db.prepare('SELECT * FROM budgets WHERE is_active = 1 ORDER BY created_at DESC'),
  getByPeriodType: db.prepare('SELECT * FROM budgets WHERE period_type = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1'),
  create: db.prepare(`
    INSERT INTO budgets (period_type, amount, currency, start_date, end_date, notes)
    VALUES (?, ?, ?, ?, ?, ?)
  `),
  update: db.prepare(`
    UPDATE budgets SET
      amount = ?,
      currency = ?,
      start_date = ?,
      end_date = ?,
      notes = ?,
      updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `),
  deactivate: db.prepare('UPDATE budgets SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?'),
  delete: db.prepare('DELETE FROM budgets WHERE id = ?')
};

const healthHistoryQueries = {
  create: db.prepare(`
    INSERT INTO health_history (check_type, total_vps, avg_score, healthy_count, warning_count, critical_count, down_count, problematic_vps)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `),
  getRecent: db.prepare('SELECT * FROM health_history ORDER BY created_at DESC LIMIT ?'),
  getByDateRange: db.prepare(`
    SELECT * FROM health_history
    WHERE created_at >= ? AND created_at <= ?
    ORDER BY created_at ASC
  `),
  getByDays: db.prepare(`
    SELECT * FROM health_history
    WHERE created_at >= datetime('now', '-' || ? || ' days')
    ORDER BY created_at ASC
  `),
  deleteOlderThan: db.prepare(`
    DELETE FROM health_history
    WHERE created_at < datetime('now', '-' || ? || ' days')
  `)
};

const costHistoryQueries = {
  create: db.prepare(`
    INSERT INTO cost_history (period, total_monthly_cost, total_yearly_cost, vps_count, currency, by_provider, by_cycle)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `),
  getByPeriod: db.prepare('SELECT * FROM cost_history WHERE period = ?'),
  getRecent: db.prepare('SELECT * FROM cost_history ORDER BY created_at DESC LIMIT ?'),
  getByDateRange: db.prepare(`
    SELECT * FROM cost_history
    WHERE created_at >= ? AND created_at <= ?
    ORDER BY created_at ASC
  `),
  getByDays: db.prepare(`
    SELECT * FROM cost_history
    WHERE created_at >= datetime('now', '-' || ? || ' days')
    ORDER BY created_at ASC
  `),
  getByMonths: db.prepare(`
    SELECT * FROM cost_history
    WHERE created_at >= datetime('now', '-' || ? || ' months')
    ORDER BY created_at ASC
  `),
  deleteOlderThan: db.prepare(`
    DELETE FROM cost_history
    WHERE created_at < datetime('now', '-' || ? || ' days')
  `)
};

const budgetHistoryQueries = {
  create: db.prepare(`
    INSERT INTO budget_history (budget_id, period_type, budget_amount, used_amount, remaining_amount, usage_percentage, alert_level)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `),
  getByBudgetId: db.prepare(`
    SELECT * FROM budget_history
    WHERE budget_id = ?
    ORDER BY created_at DESC
  `),
  getRecent: db.prepare('SELECT * FROM budget_history ORDER BY created_at DESC LIMIT ?'),
  getByDays: db.prepare(`
    SELECT * FROM budget_history
    WHERE created_at >= datetime('now', '-' || ? || ' days')
    ORDER BY created_at ASC
  `),
  deleteByBudgetId: db.prepare('DELETE FROM budget_history WHERE budget_id = ?')
};

function rowToVps(row) {
  if (!row) return null;
  return {
    id: row.id,
    name: row.name,
    provider: row.provider,
    price: row.price,
    currency: row.currency,
    cycle: row.cycle,
    purchaseDate: row.purchase_date,
    notes: row.notes,
    location: row.location,
    ip: row.ip,
    specs: row.specs ? JSON.parse(row.specs) : null,
    nezha: row.nezha ? JSON.parse(row.nezha) : null
  };
}

function vpsToRow(vps) {
  return {
    id: vps.id,
    name: vps.name,
    provider: vps.provider || null,
    price: vps.price || null,
    currency: vps.currency || 'CNY',
    cycle: vps.cycle || null,
    purchase_date: vps.purchaseDate || null,
    notes: vps.notes || null,
    location: vps.location || null,
    ip: vps.ip || null,
    specs: vps.specs ? JSON.stringify(vps.specs) : null,
    nezha: vps.nezha ? JSON.stringify(vps.nezha) : null
  };
}

const UserDB = {
  isInitialized() {
    const result = userQueries.count.get();
    return result.count > 0;
  },

  getByUsername(username) {
    const row = userQueries.getByUsername.get(username);
    if (!row) return null;
    return { username: row.username, passwordHash: row.password_hash };
  },

  create(username, passwordHash) {
    userQueries.create.run(username, passwordHash);
  },

  updatePassword(username, passwordHash) {
    userQueries.updatePassword.run(passwordHash, username);
  }
};

const VpsDB = {
  getAll() {
    const rows = vpsQueries.getAll.all();
    return rows.map(rowToVps);
  },

  getById(id) {
    return rowToVps(vpsQueries.getById.get(id));
  },

  create(vps) {
    vpsQueries.create.run(vpsToRow(vps));
    return vps;
  },

  update(vps) {
    vpsQueries.update.run(vpsToRow(vps));
    return vps;
  },

  delete(id) {
    vpsQueries.delete.run(id);
  },

  bulkReplace(vpsList) {
    const transaction = db.transaction((list) => {
      vpsQueries.deleteAll.run();
      for (const vps of list) {
        vpsQueries.create.run(vpsToRow(vps));
      }
    });
    transaction(vpsList);
  }
};

const ConfigDB = {
  get(key) {
    const row = configQueries.get.get(key);
    if (!row) return null;
    try {
      return JSON.parse(row.value);
    } catch {
      return row.value;
    }
  },

  set(key, value) {
    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    configQueries.set.run(key, serialized);
  }
};

const TagDB = {
  /**
   * 获取所有标签
   */
  getAll() {
    return tagQueries.getAll.all();
  },

  /**
   * 根据ID获取标签
   */
  getById(id) {
    return tagQueries.getById.get(id);
  },

  /**
   * 根据名称获取标签
   */
  getByName(name) {
    return tagQueries.getByName.get(name);
  },

  /**
   * 创建新标签
   */
  create(name, color = '#3b82f6') {
    const result = tagQueries.create.run(name, color);
    return { id: result.lastInsertRowid, name, color };
  },

  /**
   * 更新标签
   */
  update(id, name, color) {
    tagQueries.update.run(name, color, id);
    return { id, name, color };
  },

  /**
   * 删除标签（会自动删除关联关系）
   */
  delete(id) {
    tagQueries.delete.run(id);
  },

  /**
   * 获取VPS的所有标签
   */
  getVpsTags(vpsId) {
    return tagQueries.getVpsTags.all(vpsId);
  },

  /**
   * 获取某标签下的所有VPS
   */
  getVpsByTag(tagId) {
    const rows = tagQueries.getTagVps.all(tagId);
    return rows.map(rowToVps);
  },

  /**
   * 给VPS添加标签
   */
  addTagToVps(vpsId, tagId) {
    tagQueries.addVpsTag.run(vpsId, tagId);
  },

  /**
   * 从VPS移除标签
   */
  removeTagFromVps(vpsId, tagId) {
    tagQueries.removeVpsTag.run(vpsId, tagId);
  },

  /**
   * 设置VPS的标签（替换所有现有标签）
   */
  setVpsTags(vpsId, tagIds) {
    const transaction = db.transaction((vId, tIds) => {
      tagQueries.removeAllVpsTags.run(vId);
      for (const tagId of tIds) {
        tagQueries.addVpsTag.run(vId, tagId);
      }
    });
    transaction(vpsId, tagIds);
  },

  /**
   * 获取所有VPS及其标签（优化查询）
   */
  getAllWithTags() {
    const vpsList = VpsDB.getAll();
    const vpsWithTags = vpsList.map(vps => {
      const tags = this.getVpsTags(vps.id);
      return { ...vps, tags };
    });
    return vpsWithTags;
  },

  /**
   * 根据标签筛选VPS
   */
  filterVpsByTags(tagNames) {
    if (!tagNames || tagNames.length === 0) {
      return VpsDB.getAll();
    }

    // 获取标签ID
    const tagIds = tagNames
      .map(name => this.getByName(name))
      .filter(tag => tag !== null)
      .map(tag => tag.id);

    if (tagIds.length === 0) {
      return [];
    }

    // 获取拥有这些标签的VPS ID（交集）
    const vpsIdSets = tagIds.map(tagId => {
      const vps = this.getVpsByTag(tagId);
      return new Set(vps.map(v => v.id));
    });

    // 计算交集
    const commonVpsIds = [...vpsIdSets[0]].filter(id =>
      vpsIdSets.every(set => set.has(id))
    );

    // 返回VPS详情和标签
    return commonVpsIds.map(id => {
      const vps = VpsDB.getById(id);
      const tags = this.getVpsTags(id);
      return { ...vps, tags };
    });
  }
};

const BudgetDB = {
  /**
   * 获取所有预算
   */
  getAll() {
    return budgetQueries.getAll.all();
  },

  /**
   * 根据ID获取预算
   */
  getById(id) {
    return budgetQueries.getById.get(id);
  },

  /**
   * 获取所有活跃的预算
   */
  getActive() {
    return budgetQueries.getActive.all();
  },

  /**
   * 根据周期类型获取当前活跃预算
   */
  getByPeriodType(periodType) {
    return budgetQueries.getByPeriodType.get(periodType);
  },

  /**
   * 创建新预算
   */
  create(budget) {
    const result = budgetQueries.create.run(
      budget.periodType,
      budget.amount,
      budget.currency || 'CNY',
      budget.startDate,
      budget.endDate || null,
      budget.notes || null
    );

    return {
      id: result.lastInsertRowid,
      ...budget,
      isActive: 1
    };
  },

  /**
   * 更新预算
   */
  update(id, budget) {
    budgetQueries.update.run(
      budget.amount,
      budget.currency,
      budget.startDate,
      budget.endDate || null,
      budget.notes || null,
      id
    );

    return this.getById(id);
  },

  /**
   * 停用预算
   */
  deactivate(id) {
    budgetQueries.deactivate.run(id);
  },

  /**
   * 删除预算
   */
  delete(id) {
    budgetQueries.delete.run(id);
  }
};

/**
 * 健康检查历史数据访问器
 */
const HealthHistoryDB = {
  /**
   * 创建健康检查历史记录
   */
  create(checkData) {
    const result = healthHistoryQueries.create.run(
      checkData.checkType,
      checkData.totalVps,
      checkData.avgScore,
      checkData.healthyCount || 0,
      checkData.warningCount || 0,
      checkData.criticalCount || 0,
      checkData.downCount || 0,
      checkData.problematicVps ? JSON.stringify(checkData.problematicVps) : null
    );

    return {
      id: result.lastInsertRowid,
      ...checkData,
      createdAt: new Date().toISOString()
    };
  },

  /**
   * 获取最近N条记录
   */
  getRecent(limit = 30) {
    const rows = healthHistoryQueries.getRecent.all(limit);
    return rows.map(row => ({
      ...row,
      problematicVps: row.problematic_vps ? JSON.parse(row.problematic_vps) : []
    }));
  },

  /**
   * 获取指定日期范围的记录
   */
  getByDateRange(startDate, endDate) {
    const rows = healthHistoryQueries.getByDateRange.all(startDate, endDate);
    return rows.map(row => ({
      ...row,
      problematicVps: row.problematic_vps ? JSON.parse(row.problematic_vps) : []
    }));
  },

  /**
   * 获取最近N天的记录
   */
  getByDays(days = 7) {
    const rows = healthHistoryQueries.getByDays.all(days);
    return rows.map(row => ({
      ...row,
      problematicVps: row.problematic_vps ? JSON.parse(row.problematic_vps) : []
    }));
  },

  /**
   * 删除N天前的旧记录
   */
  deleteOlderThan(days = 90) {
    const result = healthHistoryQueries.deleteOlderThan.run(days);
    return result.changes;
  }
};

/**
 * 成本历史数据访问器
 */
const CostHistoryDB = {
  /**
   * 创建成本历史记录
   */
  create(costData) {
    const result = costHistoryQueries.create.run(
      costData.period,
      costData.totalMonthlyCost,
      costData.totalYearlyCost,
      costData.vpsCount,
      costData.currency || 'CNY',
      costData.byProvider ? JSON.stringify(costData.byProvider) : null,
      costData.byCycle ? JSON.stringify(costData.byCycle) : null
    );

    return {
      id: result.lastInsertRowid,
      ...costData,
      createdAt: new Date().toISOString()
    };
  },

  /**
   * 获取最近N条记录
   */
  getRecent(limit = 30) {
    const rows = costHistoryQueries.getRecent.all(limit);
    return rows.map(row => ({
      ...row,
      byProvider: row.by_provider ? JSON.parse(row.by_provider) : null,
      byCycle: row.by_cycle ? JSON.parse(row.by_cycle) : null
    }));
  },

  /**
   * 获取指定日期范围的记录
   */
  getByDateRange(startDate, endDate) {
    const rows = costHistoryQueries.getByDateRange.all(startDate, endDate);
    return rows.map(row => ({
      ...row,
      byProvider: row.by_provider ? JSON.parse(row.by_provider) : null,
      byCycle: row.by_cycle ? JSON.parse(row.by_cycle) : null
    }));
  },

  /**
   * 获取最近N天的记录
   */
  getByDays(days = 30) {
    const rows = costHistoryQueries.getByDays.all(days);
    return rows.map(row => ({
      ...row,
      byProvider: row.by_provider ? JSON.parse(row.by_provider) : null,
      byCycle: row.by_cycle ? JSON.parse(row.by_cycle) : null
    }));
  },

  /**
   * 获取按月分组的成本趋势
   */
  getMonthlyTrend(months = 12) {
    const rows = costHistoryQueries.getByDays.all(months * 30);

    // 按月份分组，取每月第一条记录
    const monthlyData = {};
    rows.forEach(row => {
      const month = row.created_at.substring(0, 7); // YYYY-MM
      if (!monthlyData[month]) {
        monthlyData[month] = {
          period: month,
          totalMonthlyCost: row.total_monthly_cost,
          totalYearlyCost: row.total_yearly_cost,
          vpsCount: row.vps_count,
          createdAt: row.created_at
        };
      }
    });

    return Object.values(monthlyData).sort((a, b) =>
      a.period.localeCompare(b.period)
    );
  },

  /**
   * 删除N天前的旧记录
   */
  deleteOlderThan(days = 365) {
    const result = costHistoryQueries.deleteOlderThan.run(days);
    return result.changes;
  }
};

/**
 * 预算使用历史数据访问器
 */
const BudgetHistoryDB = {
  /**
   * 创建预算历史记录
   */
  create(historyData) {
    const result = budgetHistoryQueries.create.run(
      historyData.budgetId,
      historyData.periodType,
      historyData.budgetAmount,
      historyData.usedAmount,
      historyData.remainingAmount,
      historyData.usagePercentage,
      historyData.alertLevel || null
    );

    return {
      id: result.lastInsertRowid,
      ...historyData,
      createdAt: new Date().toISOString()
    };
  },

  /**
   * 获取指定预算的历史记录
   */
  getByBudgetId(budgetId) {
    return budgetHistoryQueries.getByBudgetId.all(budgetId);
  },

  /**
   * 获取最近N条记录
   */
  getRecent(limit = 30) {
    return budgetHistoryQueries.getRecent.all(limit);
  },

  /**
   * 获取最近N天的记录
   */
  getByDays(days = 30) {
    return budgetHistoryQueries.getByDays.all(days);
  },

  /**
   * 删除指定预算的所有历史记录
   */
  deleteByBudgetId(budgetId) {
    const result = budgetHistoryQueries.deleteByBudgetId.run(budgetId);
    return result.changes;
  }
};

function migrateFromJson() {
  const configPath = path.join(__dirname, '..', 'data', 'config.json');
  const adminPath = path.join(__dirname, '..', 'data', 'admin.json');

  if (fs.existsSync(adminPath) && !UserDB.isInitialized()) {
    try {
      const adminData = JSON.parse(fs.readFileSync(adminPath, 'utf8'));
      if (adminData.username && adminData.passwordHash) {
        UserDB.create(adminData.username, adminData.passwordHash);
        logger.info('已迁移管理员账号到数据库');
      }
    } catch (e) {
      logger.error(`迁移管理员数据失败: ${e.message}`);
    }
  }

  if (fs.existsSync(configPath)) {
    try {
      const configData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      
      if (configData.vpsList && configData.vpsList.length > 0) {
        const existingVps = VpsDB.getAll();
        if (existingVps.length === 0) {
          VpsDB.bulkReplace(configData.vpsList);
          logger.info(`已迁移 ${configData.vpsList.length} 台 VPS 到数据库`);
        }
      }

      if (configData.nezha) {
        const existingNezha = ConfigDB.get('nezha');
        if (!existingNezha) {
          ConfigDB.set('nezha', configData.nezha);
          logger.info('已迁移哪吒配置到数据库');
        }
      }
    } catch (e) {
      logger.error(`迁移配置数据失败: ${e.message}`);
    }
  }
}

migrateFromJson();

module.exports = {
  db,
  UserDB,
  VpsDB,
  ConfigDB,
  TagDB,
  BudgetDB,
  HealthHistoryDB,
  CostHistoryDB,
  BudgetHistoryDB
};
