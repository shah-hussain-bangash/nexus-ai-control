@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1
pushd frontend
call npm.cmd ci
if errorlevel 1 (popd & exit /b 1)
call npm.cmd run build
if errorlevel 1 (popd & exit /b 1)
popd
cd backend
..\.venv\Scripts\python.exe -m nexus.cli init
if errorlevel 1 exit /b 1
..\.venv\Scripts\python.exe -m nexus.local %*
exit /b %errorlevel%
