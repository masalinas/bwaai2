#!/usr/bin/env bash
set -e

# ==============================================================================
# Interactive Demonstration Script (bwaai-pdf-processor)
# ==============================================================================
# 1. Uploads a sample PDF with pypdf parser
# 2. Polls GET /documents/{id}/status respecting Retry-After
# 3. Fetches full document details and displays extracted pages + summary
# ==============================================================================

API_PORT="${API_PORT:-8000}"
BASE_URL="http://localhost:${API_PORT}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SAMPLE_FILE="${SCRIPT_DIR}/../samples/normal.pdf"

if [ ! -f "${SAMPLE_FILE}" ]; then
    echo "ERROR: Sample PDF not found at ${SAMPLE_FILE}" >&2
    exit 1
fi

echo "================================================================================"
echo " Bwaai Async PDF Processor - Interactive End-to-End Demo"
echo "================================================================================"
echo "Target API: ${BASE_URL}"
echo "Sample PDF: ${SAMPLE_FILE}"
echo "--------------------------------------------------------------------------------"

# 1. Healthcheck
echo "==> Step 1: Checking API health status..."
HEALTH_RESP=$(curl -s "${BASE_URL}/health")
echo "    Response: ${HEALTH_RESP}"

# 2. Upload Document
echo ""
echo "==> Step 2: Uploading document via POST /documents (parser=pypdf)..."
UPLOAD_RESP=$(curl -s -X POST "${BASE_URL}/documents" \
    -F "files=@${SAMPLE_FILE};type=application/pdf" \
    -F "parser=pypdf")

echo "    Upload Response (202 Accepted):"
echo "    ${UPLOAD_RESP}"

DOC_ID=$(echo "${UPLOAD_RESP}" | grep -o '"document_id":"[^"]*' | head -n 1 | cut -d'"' -f4)

if [ -z "${DOC_ID}" ]; then
    echo "ERROR: Could not parse document_id from upload response!" >&2
    exit 1
fi

echo "    Tracking Document ID: ${DOC_ID}"

# 3. Status Polling Loop
echo ""
echo "==> Step 3: Polling status endpoint (GET /documents/${DOC_ID}/status)..."
START_TIME=$(date +%s)
ATTEMPT=1

while true; do
    STATUS_RESP=$(curl -s -i "${BASE_URL}/documents/${DOC_ID}/status")
    STATUS_BODY=$(echo "${STATUS_RESP}" | sed -e '1,/^\r\{0,1\}$/d')
    CURRENT_STATUS=$(echo "${STATUS_BODY}" | grep -o '"status":"[^"]*' | head -n 1 | cut -d'"' -f4)
    RETRY_AFTER=$(echo "${STATUS_RESP}" | grep -i '^Retry-After:' | awk '{print $2}' | tr -d '\r\n')

    echo "    [Poll #${ATTEMPT}] Status: '${CURRENT_STATUS}' | Retry-After Header: ${RETRY_AFTER:-none}"

    if [ "${CURRENT_STATUS}" = "done" ] || [ "${CURRENT_STATUS}" = "failed" ]; then
        echo "    Terminal status '${CURRENT_STATUS}' reached!"
        break
    fi

    # Respect Retry-After if provided, else default to 2 seconds
    SLEEP_SEC=${RETRY_AFTER:-2}
    sleep "${SLEEP_SEC}"
    ATTEMPT=$((ATTEMPT + 1))
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "    Completed in ${ELAPSED}s across ${ATTEMPT} poll cycles."

# 4. Fetch Full Document Details
echo ""
echo "==> Step 4: Retrieving complete document payload (GET /documents/${DOC_ID})..."
DETAIL_RESP=$(curl -s "${BASE_URL}/documents/${DOC_ID}")

echo "--------------------------------------------------------------------------------"
echo " Final Document Details:"
echo "--------------------------------------------------------------------------------"
echo "${DETAIL_RESP}" | grep -o '"status":"[^"]*' | head -n 1
echo "${DETAIL_RESP}" | grep -o '"filename":"[^"]*' | head -n 1

# Check for summary
SUMMARY_TEXT=$(echo "${DETAIL_RESP}" | grep -o '"summary":"[^"]*' | head -n 1 | cut -d'"' -f4)
if [ -n "${SUMMARY_TEXT}" ] && [ "${SUMMARY_TEXT}" != "null" ]; then
    echo ""
    echo " Executive Summary:"
    echo " ${SUMMARY_TEXT}"
else
    ERROR_MSG=$(echo "${DETAIL_RESP}" | grep -o '"message":"[^"]*' | head -n 1 | cut -d'"' -f4)
    if [ -n "${ERROR_MSG}" ]; then
        echo ""
        echo " Summary Status / Notice:"
        echo " [Notice] ${ERROR_MSG}"
        echo " (Extracted pages remain fully available in Redis as designed)."
    fi
fi

echo "================================================================================"
echo " Demo completed successfully!"
echo "================================================================================"
