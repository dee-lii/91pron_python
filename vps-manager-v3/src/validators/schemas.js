const zod = require('zod');

const authInitSchema = zod.object({
  username: zod.string()
    .min(3, '用户名至少需要3个字符')
    .max(50, '用户名不能超过50个字符')
    .trim(),
  password: zod.string()
    .min(6, '密码至少需要6个字符')
    .max(100, '密码不能超过100个字符')
});

const authLoginSchema = zod.object({
  username: zod.string()
    .min(1, '请输入用户名')
    .trim(),
  password: zod.string()
    .min(1, '请输入密码')
});

const vpsCreateSchema = zod.object({
  name: zod.string()
    .min(1, 'VPS名称不能为空')
    .max(100, 'VPS名称不能超过100个字符')
    .trim(),
  provider: zod.string()
    .max(100, '服务商名称不能超过100个字符')
    .optional(),
  price: zod.number()
    .min(0, '价格必须大于等于0')
    .optional(),
  currency: zod.string()
    .length(3, '货币代码必须是3个字符')
    .optional(),
  billingCycle: zod.string()
    .optional(),
  purchaseDate: zod.string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, '日期格式必须为YYYY-MM-DD')
    .optional(),
  expireDate: zod.string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, '日期格式必须为YYYY-MM-DD')
    .optional(),
  network: zod.object({
    ip: zod.string()
      .regex(/^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/, '无效的 IPv4 地址')
      .optional()
      .or(zod.literal('')),
    ipv6: zod.string()
      .regex(/^([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])$/, '无效的 IPv6 地址')
      .optional()
      .or(zod.literal(''))
  }).optional(),
  specs: zod.object({
    cpu: zod.string().optional(),
    ram: zod.string().optional(),
    storage: zod.string().optional(),
    bandwidth: zod.string().optional()
  }).optional(),
  notes: zod.string()
    .max(1000, '备注不能超过1000个字符')
    .optional()
});

const vpsUpdateSchema = vpsCreateSchema.partial().extend({
  id: zod.string().optional()
});

const budgetCreateSchema = zod.object({
  periodType: zod.enum(['monthly', 'yearly'], {
    errorMap: () => ({ message: 'periodType必须是monthly或yearly' })
  }),
  amount: zod.number()
    .gt(0, 'amount必须大于0'),
  currency: zod.string()
    .length(3, '货币代码必须是3个字符')
    .default('CNY')
    .optional(),
  startDate: zod.string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, '日期格式必须为YYYY-MM-DD'),
  endDate: zod.string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, '日期格式必须为YYYY-MM-DD')
    .optional(),
  notes: zod.string()
    .max(500, '备注不能超过500个字符')
    .optional()
});

const budgetUpdateSchema = budgetCreateSchema.partial().omit({ periodType: true });

module.exports = {
  authInitSchema,
  authLoginSchema,
  vpsCreateSchema,
  vpsUpdateSchema,
  budgetCreateSchema,
  budgetUpdateSchema
};
