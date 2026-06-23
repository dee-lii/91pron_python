const express = require('express');
const router = express.Router();
const { BudgetDB } = require('../database');
const { authMiddleware } = require('../auth');
const { validate } = require('../validators/middleware');
const { budgetCreateSchema } = require('../validators/schemas');
const { getBudgetManager } = require('../features/analytics/budget-manager');

// ==================== 预算管理 API（需要认证） ====================

// 获取所有预算
router.get('/', authMiddleware, (req, res) => {
  try {
    const budgets = BudgetDB.getAll();

    res.json({
      success: true,
      data: budgets
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算列表失败: ' + error.message
    });
  }
});

// 获取活跃预算
router.get('/active', authMiddleware, (req, res) => {
  try {
    const budgets = BudgetDB.getActive();

    res.json({
      success: true,
      data: budgets
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取活跃预算失败: ' + error.message
    });
  }
});

// 创建新预算
router.post('/', authMiddleware, validate(budgetCreateSchema), (req, res) => {
  try {
    const { periodType, amount, currency, startDate, endDate, notes } = req.body;

    if (!periodType || !amount || !startDate) {
      return res.status(400).json({
        success: false,
        error: '缺少必需参数：periodType, amount, startDate'
      });
    }

    if (!['monthly', 'yearly'].includes(periodType)) {
      return res.status(400).json({
        success: false,
        error: 'periodType必须是monthly或yearly'
      });
    }

    if (amount <= 0) {
      return res.status(400).json({
        success: false,
        error: 'amount必须大于0'
      });
    }

    const budget = BudgetDB.create({
      periodType,
      amount: parseFloat(amount),
      currency: currency || 'CNY',
      startDate,
      endDate,
      notes
    });

    res.json({
      success: true,
      data: budget,
      message: '预算创建成功'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '创建预算失败: ' + error.message
    });
  }
});

// 更新预算
router.put('/:id', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;
    const { amount, currency, startDate, endDate, notes } = req.body;

    const existing = BudgetDB.getById(parseInt(id));
    if (!existing) {
      return res.status(404).json({
        success: false,
        error: '预算不存在'
      });
    }

    if (amount !== undefined && amount <= 0) {
      return res.status(400).json({
        success: false,
        error: 'amount必须大于0'
      });
    }

    const budget = BudgetDB.update(parseInt(id), {
      amount: amount !== undefined ? parseFloat(amount) : existing.amount,
      currency: currency || existing.currency,
      startDate: startDate || existing.start_date,
      endDate: endDate !== undefined ? endDate : existing.end_date,
      notes: notes !== undefined ? notes : existing.notes
    });

    res.json({
      success: true,
      data: budget,
      message: '预算更新成功'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '更新预算失败: ' + error.message
    });
  }
});

// 停用预算
router.post('/:id/deactivate', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;

    const existing = BudgetDB.getById(parseInt(id));
    if (!existing) {
      return res.status(404).json({
        success: false,
        error: '预算不存在'
      });
    }

    BudgetDB.deactivate(parseInt(id));

    res.json({
      success: true,
      message: '预算已停用'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '停用预算失败: ' + error.message
    });
  }
});

// 删除预算
router.delete('/:id', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;

    const existing = BudgetDB.getById(parseInt(id));
    if (!existing) {
      return res.status(404).json({
        success: false,
        error: '预算不存在'
      });
    }

    BudgetDB.delete(parseInt(id));

    res.json({
      success: true,
      message: '预算已删除'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '删除预算失败: ' + error.message
    });
  }
});

// 获取预算使用状态
router.get('/status/:periodType', authMiddleware, (req, res) => {
  try {
    const { periodType } = req.params;

    if (!['monthly', 'yearly'].includes(periodType)) {
      return res.status(400).json({
        success: false,
        error: 'periodType必须是monthly或yearly'
      });
    }

    const manager = getBudgetManager();
    const status = manager.getBudgetStatus(periodType);

    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算状态失败: ' + error.message
    });
  }
});

// 获取预算概览
router.get('/overview', authMiddleware, (req, res) => {
  try {
    const manager = getBudgetManager();
    const overview = manager.getOverview();

    res.json({
      success: true,
      data: overview
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算概览失败: ' + error.message
    });
  }
});

// 预测预算耗尽日期
router.get('/prediction/:periodType', authMiddleware, (req, res) => {
  try {
    const { periodType } = req.params;

    if (!['monthly', 'yearly'].includes(periodType)) {
      return res.status(400).json({
        success: false,
        error: 'periodType必须是monthly或yearly'
      });
    }

    const manager = getBudgetManager();
    const prediction = manager.predictExhaustionDate(periodType);

    res.json({
      success: true,
      data: prediction
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '预测预算耗尽日期失败: ' + error.message
    });
  }
});

// 获取预算健康度
router.get('/health/:periodType', authMiddleware, (req, res) => {
  try {
    const { periodType } = req.params;

    if (!['monthly', 'yearly'].includes(periodType)) {
      return res.status(400).json({
        success: false,
        error: 'periodType必须是monthly或yearly'
      });
    }

    const manager = getBudgetManager();
    const health = manager.getHealthScore(periodType);

    res.json({
      success: true,
      data: health
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算健康度失败: ' + error.message
    });
  }
});

// 建议预算调整
router.get('/suggestion/:periodType', authMiddleware, (req, res) => {
  try {
    const { periodType } = req.params;

    if (!['monthly', 'yearly'].includes(periodType)) {
      return res.status(400).json({
        success: false,
        error: 'periodType必须是monthly或yearly'
      });
    }

    const manager = getBudgetManager();
    const suggestion = manager.suggestBudgetAdjustment(periodType);

    res.json({
      success: true,
      data: suggestion
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取预算建议失败: ' + error.message
    });
  }
});

module.exports = router;
