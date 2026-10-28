@echo off
REM Starts both KYC-only replicas and opens them next to the originals. Needs Node.js (https://nodejs.org).
where node >nul 2>nul || (echo Node.js is not installed. Install the LTS version from https://nodejs.org and try again. & pause & exit /b 1)
start "Tideway KYC (Zerodha-style) :3011" /D "%~dp0kyc-zerodha-style" node server.js
start "Meridian KYC (HDFC-style) :3012" /D "%~dp0kyc-hdfc-insta-style" node server.js
start "Kestrel Home Finance KYC :3013" /D "%~dp0kyc-homeloan" node server.js
timeout /t 2 >nul
start "" http://localhost:3013
start "" http://localhost:3011
start "" https://signup.zerodha.com/
start "" http://localhost:3012
start "" https://applyonline.hdfc.bank.in/savings-account/insta-savings/open-instant-savings-account-online.html
