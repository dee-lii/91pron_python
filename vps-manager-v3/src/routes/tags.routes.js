const express = require('express');
const router = express.Router();
const { TagDB } = require('../database');
const { authMiddleware } = require('../auth');

// ==================== 标签管理 API（需要认证） ====================

// 获取所有标签
router.get('/', authMiddleware, (req, res) => {
  try {
    const tags = TagDB.getAll();
    res.json({
      success: true,
      data: tags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取标签列表失败: ' + error.message
    });
  }
});

// 创建新标签
router.post('/', authMiddleware, (req, res) => {
  try {
    const { name, color } = req.body;

    if (!name || !name.trim()) {
      return res.status(400).json({
        success: false,
        error: '标签名称不能为空'
      });
    }

    // 检查标签是否已存在
    const existing = TagDB.getByName(name.trim());
    if (existing) {
      return res.status(400).json({
        success: false,
        error: '标签已存在'
      });
    }

    const tag = TagDB.create(name.trim(), color || '#3b82f6');

    res.json({
      success: true,
      data: tag
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '创建标签失败: ' + error.message
    });
  }
});

// 更新标签
router.put('/:id', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;
    const { name, color } = req.body;

    if (!name || !name.trim()) {
      return res.status(400).json({
        success: false,
        error: '标签名称不能为空'
      });
    }

    // 检查标签是否存在
    const existing = TagDB.getById(parseInt(id));
    if (!existing) {
      return res.status(404).json({
        success: false,
        error: '标签不存在'
      });
    }

    // 检查名称是否与其他标签冲突
    const nameConflict = TagDB.getByName(name.trim());
    if (nameConflict && nameConflict.id !== parseInt(id)) {
      return res.status(400).json({
        success: false,
        error: '标签名称已被使用'
      });
    }

    const tag = TagDB.update(parseInt(id), name.trim(), color || existing.color);

    res.json({
      success: true,
      data: tag
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '更新标签失败: ' + error.message
    });
  }
});

// 删除标签
router.delete('/:id', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;

    const existing = TagDB.getById(parseInt(id));
    if (!existing) {
      return res.status(404).json({
        success: false,
        error: '标签不存在'
      });
    }

    TagDB.delete(parseInt(id));

    res.json({
      success: true,
      message: '标签已删除'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '删除标签失败: ' + error.message
    });
  }
});

module.exports = router;
