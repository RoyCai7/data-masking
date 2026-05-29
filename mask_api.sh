#!/bin/bash
# SUSE Data Masking Service — full flow script
#
# Usage:
#   ./mask_api.sh -f <file> -k <api_key> [options]
#
# Options:
#   -f <file>        File to mask (required)
#   -k <api_key>     API key (required)
#   -s <server>      Server base URL (default: http://<SERVER_IP>:8080)
#   -w <whitelist>   Comma-separated whitelist values (default: none)
#   -i <session_id>  Session ID (default: auto-generated UUID)
#   -h               Show this help message
#
# Examples:
#   ./mask_api.sh -f test_data.txt -k <YOUR_API_KEY>
#   ./mask_api.sh -f secrets.log -k dms_mykey -w "localhost,127.0.0.1"
#   ./mask_api.sh -f data.txt -k dms_mykey -s http://myserver:8080

set -euo pipefail

# Defaults
API_KEY=""
SERVER="http://<SERVER_IP>:8080"
WHITELIST=""
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
FILE=""

usage() {
  sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

json_get() {
  python3 -c "import json,os,sys; print(json.loads(os.environ['_JSON_DATA'])['$1'])"
}

# Parse flags
while getopts "f:k:s:w:i:h" opt; do
  case $opt in
    f) FILE="$OPTARG" ;;
    k) API_KEY="$OPTARG" ;;
    s) SERVER="$OPTARG" ;;
    w) WHITELIST="$OPTARG" ;;
    i) SESSION_ID="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

[ -z "$FILE" ] && echo "Error: -f <file> is required." && usage
[ -z "$API_KEY" ] && echo "Error: -k <api_key> is required." && usage
[ ! -f "$FILE" ] && echo "Error: file not found: $FILE" && exit 1

BASE="${SERVER}/api/v1"

echo "Server:     $SERVER"
echo "File:       $FILE"
echo "Whitelist:  ${WHITELIST:-<none>}"
echo "Session ID: $SESSION_ID"

# Step 1: Upload
echo -e "\n[1/4] Uploading..."
RESPONSE=$(curl -s -X POST "$BASE/mask" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID" \
  -F "file=@$FILE" \
  -F "whitelist=$WHITELIST")
echo "$RESPONSE" | python3 -m json.tool
export _JSON_DATA="$RESPONSE"
TASK_ID=$(json_get task_id)
SESSION_ID=$(json_get session_id)
echo "Task ID:    $TASK_ID"
echo "Session ID: $SESSION_ID"

# Step 2: Poll status
echo -e "\n[2/4] Waiting for completion..."
while true; do
  POLL=$(curl -s "$BASE/task/$TASK_ID" \
    -H "X-API-Key: $API_KEY" \
    -H "X-Session-ID: $SESSION_ID")
  export _JSON_DATA="$POLL"
  STATUS=$(json_get status)
  echo "  status: $STATUS"
  [ "$STATUS" = "completed" ] && break
  [ "$STATUS" = "failed" ] && echo "Task failed!" && exit 1
  sleep 1
done

# Step 3: Download masked file
echo -e "\n[3/4] Downloading masked file..."
curl -OJ "$BASE/download/$TASK_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID"

# Step 4: Report
echo -e "\n[4/4] Masking report:"
curl -s "$BASE/report/$TASK_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: $SESSION_ID" | python3 -m json.tool

echo -e "\nDone."
