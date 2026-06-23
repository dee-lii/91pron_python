// tests/api/setup.js
const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');

process.env.NODE_ENV = 'test';
process.env.PORT = 3001 + Math.floor(Math.random() * 1000); 

const TEST_DB_DIR = path.join(__dirname, '..', '..', 'data');
const TEST_DB_PATH = path.join(TEST_DB_DIR, 'test.db');
process.env.DB_PATH = TEST_DB_PATH;

process.env.JWT_SECRET = 'test-secret-key-min-32-chars-length';
process.env.JWT_EXPIRY = '1h';

// Helper: Generate test token
const getAuthToken = (username = 'admin') => {
  return jwt.sign(
    { username },
    process.env.JWT_SECRET,
    { expiresIn: process.env.JWT_EXPIRY }
  );
};

// Helper: Clear test database
const clearDatabase = () => {
  const { db } = require('../../src/database');
  const tables = ['users', 'vps', 'config', 'tags', 'vps_tags', 'budgets', 'health_history', 'cost_history', 'budget_history'];
  
  db.transaction(() => {
    tables.forEach(table => {
      try {
        db.prepare(`DELETE FROM ${table}`).run();
        db.prepare(`DELETE FROM sqlite_sequence WHERE name = ?`).run(table);
      } catch (e) {
      }
    });
  })();
};

// Helper: Create test user
const createTestUser = async (username = 'admin', password = 'password123') => {
  const { UserDB } = require('../../src/database');
  const passwordHash = await bcrypt.hash(password, 10);
  
  try {
    if (!UserDB.getByUsername(username)) {
      UserDB.create(username, passwordHash);
    }
  } catch (e) {
  }
  return { username, password };
};

// Helper: Close database connection
const closeDatabase = () => {
    try {
        const { db } = require('../../src/database');
        if (db && db.open) {
            db.close();
        }
    } catch (e) {
    }
};

module.exports = {
  TEST_DB_PATH,
  getAuthToken,
  clearDatabase,
  createTestUser,
  closeDatabase
};
