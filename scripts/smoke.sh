#!/usr/bin/env bash
# ==============================================================================
# MediCode End-to-End Stack Smoke Test
# ==============================================================================

set -euo pipefail

API_URL="${1:-http://localhost:8000}"

echo "======================================================"
echo " Running MediCode Smoke Tests against $API_URL"
echo "======================================================"

# 1. Health Probe
echo -n "Checking /health ... "
HEALTH=$(curl -s -f "$API_URL/health" || echo "FAIL")
if [ "$HEALTH" = "FAIL" ]; then
    echo "FAILED"
    exit 1
fi
echo "OK ($HEALTH)"

# 2. Readiness Probe
echo -n "Checking /ready ... "
READY_RESP=$(curl -s "$API_URL/ready" || echo "FAIL")
echo "HTTP Status / Body: $READY_RESP"

# 3. Direct Run Endpoint Check
echo -n "Checking /api/run ... "
RUN_RESP=$(curl -s -X POST "$API_URL/api/run" \
    -H "Content-Type: application/json" \
    -d '{"source_code": "print(2 + 2)", "language": "python"}' || echo "FAIL")
echo "Response: $RUN_RESP"

echo "======================================================"
echo " Smoke test script executed successfully."
echo "======================================================"
