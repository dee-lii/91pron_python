const NezhaClient = require('../src/nezha-client');

describe('NezhaClient', () => {
  describe('constructor', () => {
    test('stores apiUrl and token', () => {
      const client = new NezhaClient('https://api.example.com', 'test-token');
      expect(client.apiUrl).toBe('https://api.example.com');
      expect(client.token).toBe('test-token');
    });

    test('removes trailing slash from apiUrl', () => {
      const client = new NezhaClient('https://api.example.com/', 'test-token');
      expect(client.apiUrl).toBe('https://api.example.com');
    });

    test('handles undefined apiUrl', () => {
      const client = new NezhaClient(undefined, 'test-token');
      expect(client.apiUrl).toBeUndefined();
    });
  });

  describe('mapToVPS', () => {
    const client = new NezhaClient('https://api.example.com', 'token');

    test('maps nezha server to VPS format', () => {
      const nezhaServer = {
        id: 123,
        name: 'Tokyo Server',
        host: {
          Platform: 'linux',
          PlatformVersion: '5.15.0',
          CPU: ['AMD EPYC 7763 64-Core Processor', 'AMD EPYC 7763 64-Core Processor'],
          MemTotal: 8589934592,
          DiskTotal: 171798691840,
          Virtualization: 'kvm'
        },
        state: {
          CPU: 15.5,
          MemUsed: 4294967296,
          DiskUsed: 85899345920,
          NetInSpeed: 1000000,
          NetOutSpeed: 1000000,
          Uptime: 864000
        },
        last_active: Math.floor(Date.now() / 1000) - 60
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.name).toBe('Tokyo Server');
      expect(vps.specs.cpu.model).toBe('AMD EPYC 7763 64-Core Processor');
      expect(vps.specs.cpu.cores).toBe(2);
      expect(vps.specs.memory.size).toBe(8);
      expect(vps.specs.storage.size).toBe(160);
      expect(vps.nezha.serverId).toBe(123);
      expect(vps.nezha.online).toBe(true);
      expect(vps.nezha.platform).toBe('linux');
      expect(vps.nezha.virtualization).toBe('kvm');
    });

    test('handles missing host data', () => {
      const nezhaServer = {
        id: 456,
        name: 'Empty Server'
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.name).toBe('Empty Server');
      expect(vps.specs.cpu.model).toBe('Unknown CPU');
      expect(vps.specs.cpu.cores).toBe(1);
      expect(vps.specs.memory.size).toBe(0);
      expect(vps.specs.storage.size).toBe(0);
    });

    test('handles missing state data', () => {
      const nezhaServer = {
        id: 789,
        name: 'No State',
        host: {
          CPU: ['Intel Xeon'],
          MemTotal: 4294967296,
          DiskTotal: 42949672960
        }
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.nezha.uptime).toBe(0);
      expect(vps.nezha.cpuUsage).toBe(0);
    });

    test('uses server ID as fallback name', () => {
      const nezhaServer = {
        id: 999
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.name).toBe('Server 999');
    });

    test('marks server as offline when last_active is old', () => {
      const nezhaServer = {
        id: 111,
        name: 'Offline Server',
        last_active: Math.floor(Date.now() / 1000) - 600
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.nezha.online).toBe(false);
    });

    test('sets hardware types to null (not hardcoded)', () => {
      const nezhaServer = {
        id: 222,
        name: 'Test Server',
        host: {
          CPU: ['Test CPU'],
          MemTotal: 8589934592,
          DiskTotal: 107374182400
        }
      };

      const vps = client.mapToVPS(nezhaServer);

      expect(vps.specs.memory.type).toBeNull();
      expect(vps.specs.storage.type).toBeNull();
      expect(vps.specs.network.bandwidth).toBeNull();
    });
  });

  describe('request', () => {
    test('throws when apiUrl is missing', async () => {
      const client = new NezhaClient(undefined, 'token');
      
      await expect(client.request('/test')).rejects.toThrow('哪吒 API 配置不完整');
    });

    test('throws when token is missing', async () => {
      const client = new NezhaClient('https://api.example.com', undefined);
      
      await expect(client.request('/test')).rejects.toThrow('哪吒 API 配置不完整');
    });
  });
});
