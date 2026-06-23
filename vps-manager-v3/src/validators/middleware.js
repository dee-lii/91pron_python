const validate = (schema) => (req, res, next) => {
  try {
    const result = schema.safeParse(req.body);

    if (!result.success) {
      const details = result.error.issues.map(issue => ({
        field: issue.path.join('.'),
        message: issue.message
      }));

      return res.status(400).json({
        success: false,
        error: '输入校验失败',
        details
      });
    }
    
    next();
  } catch (error) {
    return res.status(500).json({
      success: false,
      error: '校验过程发生错误',
      details: [{ message: error.message }]
    });
  }
};

module.exports = { validate };
