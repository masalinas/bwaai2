import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export function resolveContractPath(customEnv = null) {
  const envVal = customEnv !== null ? customEnv : process.env.CONTRACT_PATH;
  if (envVal) {
    return path.resolve(envVal);
  }

  // 1. Check zip / staged layout: <root>/contracts/openapi.yaml
  const zipPath = path.resolve(__dirname, '../../contracts/openapi.yaml');
  if (fs.existsSync(zipPath)) {
    return zipPath;
  }

  // 2. Check dev multi-repo layout: <root>/bwaai2-store/contracts/openapi.yaml
  const devPath = path.resolve(__dirname, '../../../bwaai2-store/contracts/openapi.yaml');
  if (fs.existsSync(devPath)) {
    return devPath;
  }

  // 3. Fallbacks relative to current working directory
  const cwdZip = path.resolve(process.cwd(), '../contracts/openapi.yaml');
  if (fs.existsSync(cwdZip)) {
    return cwdZip;
  }

  return path.resolve(process.cwd(), '../bwaai2-store/contracts/openapi.yaml');
}

// If executed directly from CLI, print the resolved path
if (process.argv[1] === __filename) {
  const resolved = resolveContractPath();
  process.stdout.write(resolved);
}
