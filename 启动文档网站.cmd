@echo off
setlocal
cd /d "%~dp0"
echo Starting course documentation server...
echo Press Ctrl+C or close this window to stop the server.
python "%~dp0scripts\serve.py" --open %*
set "launch_exit=%errorlevel%"
if not "%launch_exit%"=="0" pause
exit /b %launch_exit%
