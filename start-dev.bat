@echo off
setlocal

REM NexusBridge dev launcher (Frontend + Python Backend)
REM Prereqs:
REM - Node.js installed
REM - Python installed
REM - .env present in repo root with JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, etc.

set ROOT=%~dp0

REM Normalize trailing backslash to avoid quoted path issues (e.g. "C:\path\")
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

if not exist "%ROOT%\.env" (
  if exist "%ROOT%\.env.example" (
    echo Missing %ROOT%\.env - creating it from .env.example...
    copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
    echo Created %ROOT%\.env
    echo Please edit .env ^(set at least JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD^) and re-run start-dev.bat
  ) else (
    echo Missing %ROOT%\.env and %ROOT%\.env.example
  )
  pause
  exit /b 1
)

REM Load .env into environment for this session (so backend has JWT_SECRET, etc.)
for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\.env") do (
  if not "%%A"=="" (
    if /i not "%%A"=="REM" (
      if not "%%A:~0,1"=="#" (
        set "%%A=%%B"
      )
    )
  )
)

if "%JWT_SECRET%"=="" (
  echo WARNING: JWT_SECRET not loaded from .env.
  echo The backend now also tries to load %ROOT%\.env automatically, but you should ensure JWT_SECRET is set.
)

REM Start frontend in a new window
for /f "tokens=1 delims=." %%V in ('node -p "process.versions.node" 2^>nul') do set NODE_MAJOR=%%V
if "%NODE_MAJOR%"=="" (
  echo Node.js not found on PATH - skipping frontend.
) else (
  if %NODE_MAJOR% GEQ 23 (
    echo Detected Node.js v%NODE_MAJOR% - this is too new for reliable Windows Rollup optional deps.
    echo Install Node 20 LTS, then delete apps\frontend\node_modules and apps\frontend\package-lock.json and rerun.
  ) else (
    start "NexusBridge Frontend" /D "%ROOT%\apps\frontend" cmd /k "npm install && npm run dev"
  )
)

echo Starting backend in this window...
pushd "%ROOT%\apps\backend-python"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt --upgrade
set "CONFIG_PATH=%ROOT%\config.yaml"
set "LOG_BASE_PATH=%ROOT%\logs"
if not exist "%LOG_BASE_PATH%" mkdir "%LOG_BASE_PATH%"
echo Backend CONFIG_PATH=%CONFIG_PATH%
echo Backend LOG_BASE_PATH=%LOG_BASE_PATH%
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
popd

echo Started frontend and backend.
echo - Frontend: http://localhost:5173
echo - Backend:  http://localhost:3000

endlocal
