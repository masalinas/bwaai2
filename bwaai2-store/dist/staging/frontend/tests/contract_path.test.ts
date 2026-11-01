import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';
import { resolveContractPath } from '../scripts/resolve-contract.js';

describe('Contract Path Resolution', () => {
  it('resolves explicit CONTRACT_PATH override', () => {
    const custom = '/tmp/custom_openapi.yaml';
    expect(resolveContractPath(custom)).toBe(path.resolve(custom));
  });

  it('resolves default contract path when unset and verifies file exists', () => {
    const resolved = resolveContractPath();
    expect(fs.existsSync(resolved)).toBe(true);
    expect(resolved.endsWith('openapi.yaml')).toBe(true);
  });
});
