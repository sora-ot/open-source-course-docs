@echo off
setlocal
cd /d "%~dp0"
echo Building, checking and packaging the website. This can take several minutes.
call npm run pages:package -- %*
set "launch_exit=%errorlevel%"
if "%launch_exit%"=="0" echo Packages are ready in the release folder.
pause
exit /b %launch_exit%
