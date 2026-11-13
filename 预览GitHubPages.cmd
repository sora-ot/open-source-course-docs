@echo off
setlocal
cd /d "%~dp0"
echo Previewing the GitHub Pages build with its recorded base path...
echo Build first if needed: npm run pages:build
call npm run pages:preview -- --open %*
set "launch_exit=%errorlevel%"
if not "%launch_exit%"=="0" pause
exit /b %launch_exit%
