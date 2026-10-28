#!/usr/bin/env bash
# Starts both demo partner sites (macOS / Linux). Ctrl+C stops both.
set -e
cd "$(dirname "$0")"
command -v node >/dev/null || { echo "Install Node.js LTS from https://nodejs.org first."; exit 1; }
for d in northstar-bank paylite-wallet; do
  [ -d "$d/node_modules" ] || (cd "$d" && npm install --no-audit --no-fund)
done
(cd northstar-bank && npm run dev) &
(cd paylite-wallet && npm run dev) &
trap 'kill 0' INT TERM EXIT
echo "Northstar Bank: http://localhost:3001   PayLite Wallet: http://localhost:3002"
wait
