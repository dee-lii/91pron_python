const express = require('express');
const router = express.Router();
const { VpsDB, TagDB } = require('../database');
const { authMiddleware } = require('../auth');
const { getDaysByCycle, calculateUsedDays } = require('../calculator');

// ==================== 批量操作 API（需要认证） ====================

// 批量添加标签到多个VPS
router.post('/add-tags', authMiddleware, (req, res) => {
  try {
    const { vpsIds, tagIds } = req.body;

    if (!Array.isArray(vpsIds) || !Array.isArray(tagIds)) {
      return res.status(400).json({
        success: false,
        error: 'vpsIds和tagIds必须是数组'
      });
    }

    if (vpsIds.length === 0 || tagIds.length === 0) {
      return res.status(400).json({
        success: false,
        error: '请选择至少一个VPS和一个标签'
      });
    }

    // 验证所有VPS和标签都存在
    for (const vpsId of vpsIds) {
      const vps = VpsDB.getById(vpsId);
      if (!vps) {
        return res.status(404).json({
          success: false,
          error: `VPS不存在: ${vpsId}`
        });
      }
    }

    for (const tagId of tagIds) {
      const tag = TagDB.getById(tagId);
      if (!tag) {
        return res.status(404).json({
          success: false,
          error: `标签不存在: ${tagId}`
        });
      }
    }

    // 批量添加标签
    let addedCount = 0;
    for (const vpsId of vpsIds) {
      for (const tagId of tagIds) {
        TagDB.addTagToVps(vpsId, tagId);
        addedCount++;
      }
    }

    res.json({
      success: true,
      message: `已为 ${vpsIds.length} 台服务器添加 ${tagIds.length} 个标签`,
      details: {
        vpsCount: vpsIds.length,
        tagCount: tagIds.length,
        operationCount: addedCount
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '批量添加标签失败: ' + error.message
    });
  }
});

// 批量移除标签从多个VPS
router.post('/remove-tags', authMiddleware, (req, res) => {
  try {
    const { vpsIds, tagIds } = req.body;

    if (!Array.isArray(vpsIds) || !Array.isArray(tagIds)) {
      return res.status(400).json({
        success: false,
        error: 'vpsIds和tagIds必须是数组'
      });
    }

    if (vpsIds.length === 0 || tagIds.length === 0) {
      return res.status(400).json({
        success: false,
        error: '请选择至少一个VPS和一个标签'
      });
    }

    // 批量移除标签
    let removedCount = 0;
    for (const vpsId of vpsIds) {
      for (const tagId of tagIds) {
        TagDB.removeTagFromVps(vpsId, tagId);
        removedCount++;
      }
    }

    res.json({
      success: true,
      message: `已从 ${vpsIds.length} 台服务器移除 ${tagIds.length} 个标签`,
      details: {
        vpsCount: vpsIds.length,
        tagCount: tagIds.length,
        operationCount: removedCount
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '批量移除标签失败: ' + error.message
    });
  }
});

// 批量更新VPS属性
router.post('/update-properties', authMiddleware, (req, res) => {
  try {
    const { vpsIds, properties } = req.body;

    if (!Array.isArray(vpsIds)) {
      return res.status(400).json({
        success: false,
        error: 'vpsIds必须是数组'
      });
    }

    if (!properties || typeof properties !== 'object') {
      return res.status(400).json({
        success: false,
        error: 'properties必须是对象'
      });
    }

    if (vpsIds.length === 0) {
      return res.status(400).json({
        success: false,
        error: '请选择至少一个VPS'
      });
    }

    // 验证所有VPS都存在
    for (const vpsId of vpsIds) {
      const vps = VpsDB.getById(vpsId);
      if (!vps) {
        return res.status(404).json({
          success: false,
          error: `VPS不存在: ${vpsId}`
        });
      }
    }

    // 批量更新属性
    const updatedVps = [];
    for (const vpsId of vpsIds) {
      const existing = VpsDB.getById(vpsId);
      const updated = { ...existing, ...properties, id: vpsId };
      VpsDB.update(updated);
      updatedVps.push(updated);
    }

    res.json({
      success: true,
      message: `已更新 ${vpsIds.length} 台服务器`,
      data: updatedVps
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '批量更新失败: ' + error.message
    });
  }
});

// 批量删除VPS
router.post('/delete', authMiddleware, (req, res) => {
  try {
    const { vpsIds } = req.body;

    if (!Array.isArray(vpsIds)) {
      return res.status(400).json({
        success: false,
        error: 'vpsIds必须是数组'
      });
    }

    if (vpsIds.length === 0) {
      return res.status(400).json({
        success: false,
        error: '请选择至少一个VPS'
      });
    }

    // 验证所有VPS都存在并收集名称
    const vpsNames = [];
    for (const vpsId of vpsIds) {
      const vps = VpsDB.getById(vpsId);
      if (!vps) {
        return res.status(404).json({
          success: false,
          error: `VPS不存在: ${vpsId}`
        });
      }
      vpsNames.push(vps.name);
    }

    // 批量删除
    for (const vpsId of vpsIds) {
      VpsDB.delete(vpsId);
    }

    res.json({
      success: true,
      message: `已删除 ${vpsIds.length} 台服务器`,
      deletedServers: vpsNames
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '批量删除失败: ' + error.message
    });
  }
});

// 根据条件批量选择VPS
router.post('/select', authMiddleware, (req, res) => {
  try {
    const { filters } = req.body;

    if (!filters || typeof filters !== 'object') {
      return res.status(400).json({
        success: false,
        error: 'filters必须是对象'
      });
    }

    let vpsList = VpsDB.getAll();

    // 根据provider筛选
    if (filters.provider) {
      vpsList = vpsList.filter(vps => vps.provider === filters.provider);
    }

    // 根据location筛选
    if (filters.location) {
      vpsList = vpsList.filter(vps => vps.location === filters.location);
    }

    // 根据cycle筛选
    if (filters.cycle) {
      vpsList = vpsList.filter(vps => vps.cycle === filters.cycle);
    }

    // 根据price范围筛选
    if (filters.minPrice !== undefined) {
      vpsList = vpsList.filter(vps => vps.price >= filters.minPrice);
    }
    if (filters.maxPrice !== undefined) {
      vpsList = vpsList.filter(vps => vps.price <= filters.maxPrice);
    }

    // 根据标签筛选
    if (filters.tags && Array.isArray(filters.tags) && filters.tags.length > 0) {
      const vpsWithTags = TagDB.filterVpsByTags(filters.tags);
      const vpsIdsWithTags = new Set(vpsWithTags.map(v => v.id));
      vpsList = vpsList.filter(vps => vpsIdsWithTags.has(vps.id));
    }

    // 根据到期时间筛选
    if (filters.expiringInDays !== undefined) {
      vpsList = vpsList.filter(vps => {
        if (!vps.cycle || !vps.purchaseDate) return false;
        const totalDays = getDaysByCycle(vps.cycle);
        const usedDays = calculateUsedDays(vps.purchaseDate);
        const remainingDays = totalDays - usedDays;
        return remainingDays > 0 && remainingDays <= filters.expiringInDays;
      });
    }

    // 为每个VPS添加标签信息
    const vpsWithTags = vpsList.map(vps => {
      const tags = TagDB.getVpsTags(vps.id);
      return { ...vps, tags };
    });

    res.json({
      success: true,
      data: vpsWithTags,
      count: vpsWithTags.length,
      filters: filters
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '批量选择失败: ' + error.message
    });
  }
});

module.exports = router;
