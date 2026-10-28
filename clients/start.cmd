@echo off
rem Starts both demo partner sites. Double-click this file, or run it from a terminal.
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Install the LTS version from https://nodejs.org, then run this again.
  pause
  exit /b 1
)

if not exist "northstar-bank\node_modules" (
  echo Installing Northstar Bank. This takes a minute the first time...
  pushd northstar-bank
  call npm install --no-audit --no-fund
  popd
)
if not exist "paylite-wallet\node_modules" (
  echo Installing PayLite Wallet...
  pushd paylite-wallet
  call npm install --no-audit --no-fund
  popd
)

start "Northstar Bank - localhost:3001" /D "%~dp0northstar-bank" cmd /k npm run dev
start "PayLite Wallet - localhost:3002" /D "%~dp0paylite-wallet" cmd /k npm run dev

echo Waiting for both sites to start...
timeout /t 15 /nobreak >nul
start "" http://localhost:3001
start "" http://localhost:3002
echo.
echo Northstar Bank:  http://localhost:3001   (ops console: /ops, passcode northstar-ops)
echo PayLite Wallet:  http://localhost:3002   (ops console: /ops, passcode paylite-ops)
echo Close the two server windows to stop them.
