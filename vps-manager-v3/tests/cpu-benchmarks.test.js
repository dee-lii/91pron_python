const {
  CPU_BENCHMARKS,
  getCPUBenchmark,
  getSupportedCPUs,
  addCustomCPU
} = require('../src/cpu-benchmarks');

describe('cpu-benchmarks', () => {
  describe('CPU_BENCHMARKS', () => {
    test('contains AMD EPYC entries', () => {
      expect(CPU_BENCHMARKS['AMD EPYC 7763']).toBeDefined();
      expect(CPU_BENCHMARKS['AMD EPYC 7763'].singleThread).toBe(3356);
    });

    test('contains Intel Xeon entries', () => {
      expect(CPU_BENCHMARKS['Intel Xeon E5-2696 v3']).toBeDefined();
    });

    test('contains generic Virtual CPU', () => {
      expect(CPU_BENCHMARKS['Virtual CPU']).toBeDefined();
    });
  });

  describe('getCPUBenchmark', () => {
    test('returns exact match', () => {
      const result = getCPUBenchmark('AMD EPYC 7763');
      expect(result.singleThread).toBe(3356);
      expect(result.multiThread).toBe(83490);
      expect(result.cores).toBe(64);
    });

    test('returns fuzzy match for partial model name', () => {
      const result = getCPUBenchmark('AMD EPYC 7763 64-Core Processor');
      expect(result.singleThread).toBe(3356);
    });

    test('returns generic EPYC for unknown EPYC model', () => {
      const result = getCPUBenchmark('AMD EPYC 9999', 8);
      expect(result.singleThread).toBe(2500);
    });

    test('returns generic Xeon for unknown Xeon model', () => {
      const result = getCPUBenchmark('Intel Xeon Unknown', 4);
      expect(result.singleThread).toBe(2000);
    });

    test('returns generic Ryzen for unknown Ryzen model', () => {
      const result = getCPUBenchmark('AMD Ryzen 11 9999X', 16);
      expect(result.singleThread).toBe(3000);
    });

    test('returns default virtual CPU for unknown model', () => {
      const result = getCPUBenchmark('Unknown CPU Model', 2);
      expect(result.singleThread).toBe(1500);
      expect(result.multiThread).toBe(6000);
      expect(result.cores).toBe(2);
    });

    test('handles case insensitive matching', () => {
      const result = getCPUBenchmark('amd epyc 7763');
      expect(result.singleThread).toBe(3356);
    });
  });

  describe('getSupportedCPUs', () => {
    test('returns array of CPU models', () => {
      const cpus = getSupportedCPUs();
      expect(Array.isArray(cpus)).toBe(true);
      expect(cpus.length).toBeGreaterThan(10);
    });

    test('returns sorted list', () => {
      const cpus = getSupportedCPUs();
      const sorted = [...cpus].sort();
      expect(cpus).toEqual(sorted);
    });

    test('includes known models', () => {
      const cpus = getSupportedCPUs();
      expect(cpus).toContain('AMD EPYC 7763');
      expect(cpus).toContain('Intel Core i9-12900K');
    });
  });

  describe('addCustomCPU', () => {
    test('adds new CPU to benchmarks', () => {
      addCustomCPU('Custom CPU X1', 5000, 100000, 32);
      
      const result = getCPUBenchmark('Custom CPU X1');
      expect(result.singleThread).toBe(5000);
      expect(result.multiThread).toBe(100000);
      expect(result.cores).toBe(32);
    });
  });
});
