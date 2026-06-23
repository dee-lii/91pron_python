const request = require('supertest');
const { clearDatabase, createTestUser, getAuthToken } = require('./setup');
const app = require('../../src/server');

describe('VPS API', () => {
  let token;

  beforeEach(async () => {
    clearDatabase();
    await createTestUser();
    token = getAuthToken();
  });

  describe('GET /api/vps', () => {
    it('should return empty list initially', async () => {
      const res = await request(app)
        .get('/api/vps')
        .set('Authorization', `Bearer ${token}`);

      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);
      expect(Array.isArray(res.body.data)).toBe(true);
      expect(res.body.data).toHaveLength(0);
    });

    it('should require authentication', async () => {
      const res = await request(app).get('/api/vps');
      expect(res.statusCode).toBe(401);
    });
  });

  describe('POST /api/vps', () => {
    const newVps = {
      name: 'Test VPS',
      provider: 'AWS',
      price: 10,
      currency: 'USD',
      cycle: 'monthly',
      purchaseDate: '2023-01-01',
      notes: 'Test notes'
    };

    it('should create a new VPS', async () => {
      const res = await request(app)
        .post('/api/vps')
        .set('Authorization', `Bearer ${token}`)
        .send(newVps);

      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);
      expect(res.body.data).toHaveProperty('id');
      expect(res.body.data.name).toBe(newVps.name);
    });

    it('should require name', async () => {
      const res = await request(app)
        .post('/api/vps')
        .set('Authorization', `Bearer ${token}`)
        .send({ ...newVps, name: '' });

      expect(res.statusCode).toBe(400);
    });
  });

  describe('PUT /api/vps/:id', () => {
    let vpsId;

    beforeEach(async () => {
      const res = await request(app)
        .post('/api/vps')
        .set('Authorization', `Bearer ${token}`)
        .send({
          name: 'Original VPS',
          provider: 'AWS'
        });
      vpsId = res.body.data.id;
    });

    it('should update VPS details', async () => {
      const res = await request(app)
        .put(`/api/vps/${vpsId}`)
        .set('Authorization', `Bearer ${token}`)
        .send({
          id: vpsId,
          name: 'Updated VPS',
          provider: 'GCP'
        });

      expect(res.statusCode).toBe(200);
      expect(res.body.data.name).toBe('Updated VPS');
      expect(res.body.data.provider).toBe('GCP');
    });
  });

  describe('DELETE /api/vps/:id', () => {
    let vpsId;

    beforeEach(async () => {
      const res = await request(app)
        .post('/api/vps')
        .set('Authorization', `Bearer ${token}`)
        .send({
          name: 'To Delete',
          provider: 'AWS'
        });
      vpsId = res.body.data.id;
    });

    it('should delete VPS', async () => {
      const res = await request(app)
        .delete(`/api/vps/${vpsId}`)
        .set('Authorization', `Bearer ${token}`);

      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty('success', true);

      const listRes = await request(app)
        .get('/api/vps')
        .set('Authorization', `Bearer ${token}`);
      expect(listRes.body.data).toHaveLength(0);
    });
  });
});
