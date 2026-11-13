@echo off
setlocal
cd /d "%~dp0"
if not exist "node_modules\vitepress\bin\vitepress.js" (
  echo Install dependencies first: npm ci
  pause
  exit /b 1
)
echo Starting VitePress development server with live reload...
call npm run dev -- --open %*
set "launch_exit=%errorlevel%"
if not "%launch_exit%"=="0" pause
exit /b %launch_exit%
