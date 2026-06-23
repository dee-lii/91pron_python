const express = require('express');
const router = express.Router();
const {
  isInitialized,
  initialize,
  login,
  authMiddleware,
  changePassword,
  isIPLocked,
  recordLoginFailure,
  clearLoginFailures
} = require('../auth');
const { authLimiter } = require('../middleware/rate-limit');
const { validate } = require('../validators/middleware');
const { authInitSchema, authLoginSchema } = require('../validators/schemas');

/**
 * @swagger
 * tags:
 *   name: Auth
 *   description: User authentication and management
 */

// ==================== 认证 API ====================

/**
 * @swagger
 * /auth/status:
 *   get:
 *     summary: Check initialization status
 *     tags: [Auth]
 *     responses:
 *       200:
 *         description: Initialization status
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: object
 *                   properties:
 *                     initialized:
 *                       type: boolean
 */
router.get('/status', (req, res) => {
  res.json({
    success: true,
    data: { initialized: isInitialized() }
  });
});

/**
 * @swagger
 * /auth/init:
 *   post:
 *     summary: Initialize the application with first user
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - username
 *               - password
 *             properties:
 *               username:
 *                 type: string
 *               password:
 *                 type: string
 *     responses:
 *       200:
 *         description: Initialization successful
 *       400:
 *         description: Already initialized or invalid input
 */
router.post('/init', authLimiter, validate(authInitSchema), async (req, res) => {
  try {
    const { username, password } = req.body;
    const result = await initialize(username, password);
    res.json({ success: true, data: result });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});

/**
 * @swagger
 * /auth/login:
 *   post:
 *     summary: Login to get access token
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - username
 *               - password
 *             properties:
 *               username:
 *                 type: string
 *               password:
 *                 type: string
 *     responses:
 *       200:
 *         description: Login successful
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: object
 *                   properties:
 *                     token:
 *                       type: string
 *       401:
 *         description: Invalid credentials
 *       429:
 *         description: Too many attempts
 */
router.post('/login', authLimiter, validate(authLoginSchema), async (req, res) => {
  const clientIP = req.ip || req.connection.remoteAddress;

  // 检查IP是否被锁定
  if (isIPLocked(clientIP)) {
    return res.status(429).json({
      success: false,
      error: '登录失败次数过多，账号已锁定30分钟'
    });
  }

  try {
    const { username, password } = req.body;
    const result = await login(username, password);

    // 登录成功，清除失败记录
    clearLoginFailures(clientIP);

    res.json({ success: true, data: result });
  } catch (error) {
    // 记录失败尝试
    const failureCount = recordLoginFailure(clientIP);
    const remainingAttempts = Math.max(0, 5 - failureCount);

    res.status(401).json({
      success: false,
      error: error.message,
      remainingAttempts
    });
  }
});

router.put('/password', authMiddleware, async (req, res) => {
  try {
    const { oldPassword, newPassword } = req.body;
    await changePassword(req.user.username, oldPassword, newPassword);
    res.json({ success: true, message: '密码修改成功' });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});

router.get('/me', authMiddleware, (req, res) => {
  res.json({ success: true, data: { username: req.user.username } });
});

module.exports = router;
