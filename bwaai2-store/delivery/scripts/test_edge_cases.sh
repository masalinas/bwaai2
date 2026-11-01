#!/usr/bin/env bash
set -e

# ==============================================================================
# Edge Cases & Validation Test Suite (bwaai-pdf-processor)
# ==============================================================================
# Verifies all edge cases defined in OpenAPI contract against a running instance.
# ==============================================================================

API_PORT="${API_PORT:-8000}"
BASE_URL="http://localhost:${API_PORT}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SAMPLES_DIR="${SCRIPT_DIR}/../samples"

PASS_COUNT=0
FAIL_COUNT=0

assert_status() {
    TEST_NAME="$1"
    EXPECTED_CODE="$2"
    ACTUAL_CODE="$3"
    ACTUAL_BODY="$4"
    EXPECTED_ERR_CODE="$5"

    if [ "${ACTUAL_CODE}" -eq "${EXPECTED_CODE}" ]; then
        if [ -n "${EXPECTED_ERR_CODE}" ]; then
            if echo "${ACTUAL_BODY}" | grep -q "\"code\":\"${EXPECTED_ERR_CODE}\""; then
                echo "  [PASS] ${TEST_NAME} -> HTTP ${ACTUAL_CODE} with code '${EXPECTED_ERR_CODE}'"
                PASS_COUNT=$((PASS_COUNT + 1))
                return
            else
                echo "  [FAIL] ${TEST_NAME} -> Expected code '${EXPECTED_ERR_CODE}', got: ${ACTUAL_BODY}" >&2
                FAIL_COUNT=$((FAIL_COUNT + 1))
                return
            fi
        fi
        echo "  [PASS] ${TEST_NAME} -> HTTP ${ACTUAL_CODE}"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  [FAIL] ${TEST_NAME} -> Expected HTTP ${EXPECTED_CODE}, got ${ACTUAL_CODE}: ${ACTUAL_BODY}" >&2
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "================================================================================"
echo " Running Automated Edge Case Checks Against ${BASE_URL}"
echo "================================================================================"

# 1. Healthcheck
RESP=$(curl -s -w "\n%{http_code}" "${BASE_URL}/health")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "1. GET /health is OK" 200 "${CODE}" "${BODY}"

# 2. Upload Spoofed / Non-PDF file
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" \
    -F "files=@${SAMPLES_DIR}/not_a_pdf.pdf;type=application/pdf" \
    -F "parser=pypdf")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "2. Spoofed magic bytes rejected" 415 "${CODE}" "${BODY}" "INVALID_FILE_TYPE"

# 3. Upload Encrypted PDF
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" \
    -F "files=@${SAMPLES_DIR}/encrypted.pdf;type=application/pdf" \
    -F "parser=pypdf")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "3. Encrypted PDF rejected" 400 "${CODE}" "${BODY}" "ENCRYPTED_PDF"

# 4. Upload Empty File
TMP_EMPTY=$(mktemp /tmp/empty_test.XXXXXX.pdf)
touch "${TMP_EMPTY}"
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" \
    -F "files=@${TMP_EMPTY};type=application/pdf" \
    -F "parser=pypdf")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
rm -f "${TMP_EMPTY}"
assert_status "4. Empty file rejected" 400 "${CODE}" "${BODY}" "EMPTY_FILE"

# 5. Batch Size Exceeded (> 10 files)
CURL_ARGS=()
for i in $(seq 1 11); do
    CURL_ARGS+=(-F "files=@${SAMPLES_DIR}/normal.pdf;type=application/pdf")
done
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" "${CURL_ARGS[@]}" -F "parser=pypdf")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "5. Batch count > 10 rejected" 413 "${CODE}" "${BODY}" "TOO_MANY_FILES"

# 6. Unconfigured Mistral Upload (when MISTRAL_API_KEY is not set)
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" \
    -F "files=@${SAMPLES_DIR}/normal.pdf;type=application/pdf" \
    -F "parser=mistral")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "6. Unconfigured Mistral returns PARSER_UNAVAILABLE" 500 "${CODE}" "${BODY}" "PARSER_UNAVAILABLE"

# 7. Valid Normal Upload
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/documents" \
    -F "files=@${SAMPLES_DIR}/normal.pdf;type=application/pdf" \
    -F "parser=pypdf")
CODE=$(echo "${RESP}" | tail -n1)
BODY=$(echo "${RESP}" | sed '$d')
assert_status "7. Normal valid upload accepted" 202 "${CODE}" "${BODY}"

echo "--------------------------------------------------------------------------------"
echo "Edge Case Results: ${PASS_COUNT} Passed, ${FAIL_COUNT} Failed."
echo "================================================================================"

if [ "${FAIL_COUNT}" -gt 0 ]; then
    exit 1
fi
