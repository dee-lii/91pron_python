const request = require('supertest');
const { clearDatabase, createTestUser, getAuthToken } = require('./setup');
const app = require('../../src/server');

describe('Health API', () => {
  let token;

  beforeEach(async () => {
    clearDatabase();
    await createTestUser();
    token = getAuthToken();
  });

  describe('GET /api/health/overview', () => {
    it('should return overview when authenticated', async () => {
      const res = await request(app)
        .get('/api/health/overview')
        .set('Authorization', `Bearer ${token}`);
      
      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);
      expect(res.body).toHaveProperty('data');
    });

    it('should require authentication', async () => {
      const res = await request(app).get('/api/health/overview');
      expect(res.statusCode).toBe(401);
    });
  });
});
