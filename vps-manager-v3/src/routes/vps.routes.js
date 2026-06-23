const express = require('express');
const router = express.Router();
const { VpsDB } = require('../database');
const { authMiddleware } = require('../auth');
const { vpsOperationLimiter } = require('../middleware/rate-limit');
const { validate } = require('../validators/middleware');
const { vpsCreateSchema, vpsUpdateSchema } = require('../validators/schemas');
const { TagDB } = require('../database');

/**
 * @swagger
 * tags:
 *   name: VPS
 *   description: VPS management endpoints
 */

/**
 * @swagger
 * components:
 *   schemas:
 *     VPS:
 *       type: object
 *       required:
 *         - name
 *         - provider
 *       properties:
 *         id:
 *           type: string
 *         name:
 *           type: string
 *         provider:
 *           type: string
 *         ip:
 *           type: string
 *         price:
 *           type: number
 *         currency:
 *           type: string
 *         billingCycle:
 *           type: string
 *         purchaseDate:
 *           type: string
 *           format: date
 *         expireDate:
 *           type: string
 *           format: date
 */

// ==================== VPS 管理 API（需要认证） ====================

/**
 * @swagger
 * /vps:
 *   get:
 *     summary: Get all VPS instances
 *     tags: [VPS]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: List of VPS
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: array
 *                   items:
 *                     $ref: '#/components/schemas/VPS'
 */
router.get('/', authMiddleware, (req, res) => {
  const vpsList = VpsDB.getAll();
  
  res.json({
    success: true,
    data: vpsList
  });
});

router.put('/', authMiddleware, (req, res) => {
  const { vpsList } = req.body;
  
  if (!Array.isArray(vpsList)) {
    return res.status(400).json({
      success: false,
      error: 'vpsList 必须是数组'
    });
  }
  
  try {
    VpsDB.bulkReplace(vpsList);
    res.json({
      success: true,
      message: `已保存 ${vpsList.length} 台服务器`
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '保存失败: ' + error.message
    });
  }
});

/**
 * @swagger
 * /vps:
 *   post:
 *     summary: Create a new VPS
 *     tags: [VPS]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/VPS'
 *     responses:
 *       200:
 *         description: VPS created successfully
 *       400:
 *         description: Invalid input
 */
router.post('/', authMiddleware, vpsOperationLimiter, validate(vpsCreateSchema), (req, res) => {
  const vps = req.body;

  if (!vps || !vps.name) {
    return res.status(400).json({
      success: false,
      error: 'VPS 名称不能为空'
    });
  }

  if (!vps.id) {
    vps.id = `vps_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  try {
    VpsDB.create(vps);
    res.json({
      success: true,
      data: vps,
      message: `已添加服务器: ${vps.name}`
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '添加失败: ' + error.message
    });
  }
});

/**
 * @swagger
 * /vps/{id}:
 *   put:
 *     summary: Update an existing VPS
 *     tags: [VPS]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         schema:
 *           type: string
 *         required: true
 *         description: VPS ID
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/VPS'
 *     responses:
 *       200:
 *         description: VPS updated successfully
 *       404:
 *         description: VPS not found
 */
router.put('/:id', authMiddleware, vpsOperationLimiter, validate(vpsUpdateSchema), (req, res) => {
  const { id } = req.params;
  const updates = req.body;
  
  const existing = VpsDB.getById(id);
  if (!existing) {
    return res.status(404).json({
      success: false,
      error: 'VPS 不存在'
    });
  }
  
  const updated = { ...existing, ...updates, id };
  
  try {
    VpsDB.update(updated);
    res.json({
      success: true,
      data: updated,
      message: `已更新服务器: ${updated.name}`
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '更新失败: ' + error.message
    });
  }
});

/**
 * @swagger
 * /vps/{id}:
 *   delete:
 *     summary: Delete a VPS
 *     tags: [VPS]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         schema:
 *           type: string
 *         required: true
 *         description: VPS ID
 *     responses:
 *       200:
 *         description: VPS deleted successfully
 *       404:
 *         description: VPS not found
 */
router.delete('/:id', authMiddleware, vpsOperationLimiter, (req, res) => {
  const { id } = req.params;
  
  const existing = VpsDB.getById(id);
  if (!existing) {
    return res.status(404).json({
      success: false,
      error: 'VPS 不存在'
    });
  }
  
  try {
    VpsDB.delete(id);
    res.json({
      success: true,
      message: `已删除服务器: ${existing.name}`
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '删除失败: ' + error.message
    });
  }
});

// 获取VPS的所有标签
router.get('/:id/tags', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;

    // 检查VPS是否存在
    const vps = VpsDB.getById(id);
    if (!vps) {
      return res.status(404).json({
        success: false,
        error: 'VPS不存在'
      });
    }

    const tags = TagDB.getVpsTags(id);

    res.json({
      success: true,
      data: tags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取VPS标签失败: ' + error.message
    });
  }
});

// 设置VPS的标签（替换）
router.put('/:id/tags', authMiddleware, (req, res) => {
  try {
    const { id } = req.params;
    const { tagIds } = req.body;

    // 检查VPS是否存在
    const vps = VpsDB.getById(id);
    if (!vps) {
      return res.status(404).json({
        success: false,
        error: 'VPS不存在'
      });
    }

    if (!Array.isArray(tagIds)) {
      return res.status(400).json({
        success: false,
        error: 'tagIds必须是数组'
      });
    }

    // 验证所有标签ID都存在
    for (const tagId of tagIds) {
      const tag = TagDB.getById(tagId);
      if (!tag) {
        return res.status(400).json({
          success: false,
          error: `标签ID ${tagId} 不存在`
        });
      }
    }

    TagDB.setVpsTags(id, tagIds);
    const tags = TagDB.getVpsTags(id);

    res.json({
      success: true,
      data: tags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '设置VPS标签失败: ' + error.message
    });
  }
});

// 给VPS添加单个标签
router.post('/:id/tags/:tagId', authMiddleware, (req, res) => {
  try {
    const { id, tagId } = req.params;

    // 检查VPS是否存在
    const vps = VpsDB.getById(id);
    if (!vps) {
      return res.status(404).json({
        success: false,
        error: 'VPS不存在'
      });
    }

    // 检查标签是否存在
    const tag = TagDB.getById(parseInt(tagId));
    if (!tag) {
      return res.status(404).json({
        success: false,
        error: '标签不存在'
      });
    }

    TagDB.addTagToVps(id, parseInt(tagId));
    const tags = TagDB.getVpsTags(id);

    res.json({
      success: true,
      data: tags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '添加标签失败: ' + error.message
    });
  }
});

// 从VPS移除单个标签
router.delete('/:id/tags/:tagId', authMiddleware, (req, res) => {
  try {
    const { id, tagId } = req.params;

    TagDB.removeTagFromVps(id, parseInt(tagId));
    const tags = TagDB.getVpsTags(id);

    res.json({
      success: true,
      data: tags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '移除标签失败: ' + error.message
    });
  }
});

// 获取所有VPS及其标签
router.get('/with-tags', authMiddleware, (req, res) => {
  try {
    const vpsWithTags = TagDB.getAllWithTags();

    res.json({
      success: true,
      data: vpsWithTags
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '获取VPS列表失败: ' + error.message
    });
  }
});

// 根据标签筛选VPS
router.get('/filter-by-tags', authMiddleware, (req, res) => {
  try {
    const { tags } = req.query;

    if (!tags) {
      return res.status(400).json({
        success: false,
        error: '请提供tags参数'
      });
    }

    const tagNames = Array.isArray(tags) ? tags : [tags];
    const filteredVps = TagDB.filterVpsByTags(tagNames);

    res.json({
      success: true,
      data: filteredVps,
      count: filteredVps.length
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: '筛选VPS失败: ' + error.message
    });
  }
});

module.exports = router;
