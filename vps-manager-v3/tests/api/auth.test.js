const request = require('supertest');
const { clearDatabase, createTestUser, getAuthToken } = require('./setup');
const app = require('../../src/server');

describe('Auth API', () => {
  let server;

  beforeAll(() => {
    // Server is handled by supertest
  });

  beforeEach(() => {
    clearDatabase();
  });

  describe('GET /api/auth/status', () => {
    it('should return initialization status', async () => {
      const res = await request(app).get('/api/auth/status');
      
      expect(res.statusCode).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data).toHaveProperty('initialized');
      expect(res.body.data.initialized).toBe(false);
    });
  });

  describe('POST /api/auth/init', () => {
    it('should initialize admin user', async () => {
      const res = await request(app)
        .post('/api/auth/init')
        .send({
          username: 'admin',
          password: 'password123'
        });

      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);
      
      const statusRes = await request(app).get('/api/auth/status');
      expect(statusRes.body.data.initialized).toBe(true);
    });

    it('should fail if already initialized', async () => {
      await createTestUser();
      
      const res = await request(app)
        .post('/api/auth/init')
        .send({
          username: 'admin2',
          password: 'password123'
        });

      expect(res.statusCode).toBe(400);
    });
  });

  describe('POST /api/auth/login', () => {
    beforeEach(async () => {
      await createTestUser('admin', 'password123');
    });

    it('should login successfully with correct credentials', async () => {
      const res = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'admin',
          password: 'password123'
        });

      expect(res.statusCode).toBe(200);
      expect(res.body.data).toHaveProperty('token');
      expect(res.body.data).toHaveProperty('username', 'admin');
    });

    it('should fail with incorrect password', async () => {
      const res = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'admin',
          password: 'wrongpassword'
        });

      expect(res.statusCode).toBe(401);
    });
  });

  describe('GET /api/auth/me', () => {
    it('should return user info when authenticated', async () => {
      const token = getAuthToken();
      
      const res = await request(app)
        .get('/api/auth/me')
        .set('Authorization', `Bearer ${token}`);

      expect(res.statusCode).toBe(200);
      expect(res.body.data).toHaveProperty('username', 'admin');
    });

    it('should fail when unauthenticated', async () => {
      const res = await request(app).get('/api/auth/me');
      expect(res.statusCode).toBe(401);
    });
  });

  describe('PUT /api/auth/password', () => {
    beforeEach(async () => {
      await createTestUser('admin', 'password123');
    });

    it('should update password', async () => {
      const token = getAuthToken();
      
      const res = await request(app)
        .put('/api/auth/password')
        .set('Authorization', `Bearer ${token}`)
        .send({
          oldPassword: 'password123',
          newPassword: 'newpassword123'
        });

      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);

      const loginRes = await request(app)
        .post('/api/auth/login')
        .send({
          username: 'admin',
          password: 'newpassword123'
        });
        
      expect(loginRes.statusCode).toBe(200);
    });
  });
});
