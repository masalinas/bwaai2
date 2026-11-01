#!/bin/sh
set -e

# ==============================================================================
# Single-Archive Packaging Script (bwaai-pdf-processor)
# ==============================================================================
# Assembles all delivery artifacts, backend, frontend, contract, and openspec
# records into dist/staging/, performs strict security/secret checks,
# and outputs dist/bwaai-pdf-processor.zip.
# ==============================================================================

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
STORE_DIR=$(cd "${SCRIPT_DIR}/../.." && pwd)
BACKEND_DIR=$(cd "${STORE_DIR}/../bwaai2-backend" && pwd)
FRONTEND_DIR=$(cd "${STORE_DIR}/../bwaai2-frontend" && pwd)

DIST_DIR="${STORE_DIR}/dist"
STAGE_DIR="${DIST_DIR}/staging"
ZIP_FILE="${DIST_DIR}/bwaai-pdf-processor.zip"

echo "================================================================================"
echo " Packaging Bwaai Async PDF Processor"
echo "================================================================================"
echo "Store Dir:    ${STORE_DIR}"
echo "Backend Dir:  ${BACKEND_DIR}"
echo "Frontend Dir: ${FRONTEND_DIR}"
echo "Staging Dir:  ${STAGE_DIR}"
echo "Target Zip:   ${ZIP_FILE}"
echo "--------------------------------------------------------------------------------"

# 1. Clean previous staging artifacts
rm -rf "${STAGE_DIR}" "${ZIP_FILE}"
mkdir -p "${STAGE_DIR}"

# 2. Copy root delivery assets
echo "==> Staging root delivery assets..."
cp "${STORE_DIR}/delivery/docker-compose.yml" "${STAGE_DIR}/"
cp "${STORE_DIR}/delivery/.env.example" "${STAGE_DIR}/"
cp "${STORE_DIR}/delivery/Makefile" "${STAGE_DIR}/"

if [ -d "${STORE_DIR}/delivery/.github" ]; then
    cp -R "${STORE_DIR}/delivery/.github" "${STAGE_DIR}/"
fi

if [ -f "${STORE_DIR}/delivery/README.md" ]; then
    cp "${STORE_DIR}/delivery/README.md" "${STAGE_DIR}/"
else
    # Fallback to store root or template
    cp "${STORE_DIR}/README.md" "${STAGE_DIR}/"
fi

# Copy contracts and OpenSpec records
echo "==> Staging contracts and OpenSpec specification history..."
mkdir -p "${STAGE_DIR}/contracts"
cp "${STORE_DIR}/contracts/openapi.yaml" "${STAGE_DIR}/contracts/"

mkdir -p "${STAGE_DIR}/openspec"
rsync -a --exclude='.DS_Store' "${STORE_DIR}/openspec/" "${STAGE_DIR}/openspec/"

# Copy samples and scripts
echo "==> Staging samples and helper scripts..."
mkdir -p "${STAGE_DIR}/samples" "${STAGE_DIR}/scripts"
cp -R "${STORE_DIR}/delivery/samples/"* "${STAGE_DIR}/samples/"
cp -R "${STORE_DIR}/delivery/scripts/"* "${STAGE_DIR}/scripts/"
chmod +x "${STAGE_DIR}/scripts/"*.sh "${STAGE_DIR}/scripts/"*.py 2>/dev/null || true

# 3. Stage backend (clean copy)
echo "==> Staging backend application..."
mkdir -p "${STAGE_DIR}/backend"
rsync -a \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='.env*' \
    --exclude='.DS_Store' \
    --exclude='htmlcov' \
    --exclude='.coverage' \
    --exclude='dist' \
    "${BACKEND_DIR}/" "${STAGE_DIR}/backend/"

# 4. Stage frontend (clean copy)
echo "==> Staging frontend application..."
mkdir -p "${STAGE_DIR}/frontend"
rsync -a \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='dist' \
    --exclude='.env*' \
    --exclude='.DS_Store' \
    --exclude='coverage' \
    "${FRONTEND_DIR}/" "${STAGE_DIR}/frontend/"

# 5. Security Guard: Check for .env or private secrets
echo "==> Performing security checks (scanning for .env and secrets)..."

# A. Disallow any .env files (except .env.example)
ENV_LEAKS=$(find "${STAGE_DIR}" -type f -name ".env*" ! -name ".env.example")
if [ -n "${ENV_LEAKS}" ]; then
    echo "ERROR: Secret leakage detected! Found active .env files in staging:" >&2
    echo "${ENV_LEAKS}" >&2
    exit 1
fi

# B. Disallow private key files (.pem, .key, id_rsa)
KEY_LEAKS=$(find "${STAGE_DIR}" -type f \( -name "*.pem" -o -name "*.key" -o -name "id_rsa*" \))
if [ -n "${KEY_LEAKS}" ]; then
    echo "ERROR: Private key files detected in staging:" >&2
    echo "${KEY_LEAKS}" >&2
    exit 1
fi

# C. Disallow real Google or Mistral API key patterns
SECRET_MATCHES=$(grep -rnE '(AIza[0-9A-Za-z-_]{35}|mistral_[0-9A-Za-z]{24,})' "${STAGE_DIR}" 2>/dev/null || true)
if [ -n "${SECRET_MATCHES}" ]; then
    echo "ERROR: Potential hardcoded API keys detected in staged files:" >&2
    echo "${SECRET_MATCHES}" >&2
    exit 1
fi

echo "Security check PASSED: No secrets or environment overrides found."

# 6. Create Zip Archive
echo "==> Creating distribution archive: ${ZIP_FILE}..."
(
    cd "${STAGE_DIR}"
    zip -r -q "${ZIP_FILE}" .
)

# 7. Summary
ZIP_SIZE=$(ls -lh "${ZIP_FILE}" | awk '{print $5}')
TOTAL_FILES=$(find "${STAGE_DIR}" -type f | wc -l | tr -d ' ')

echo "--------------------------------------------------------------------------------"
echo " Packaging Complete!"
echo " Archive Path: ${ZIP_FILE}"
echo " Archive Size: ${ZIP_SIZE}"
echo " Total Files:  ${TOTAL_FILES}"
echo " Staged Root:"
ls -la "${STAGE_DIR}"
echo "================================================================================"
