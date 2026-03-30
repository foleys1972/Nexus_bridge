@echo off
setlocal EnableExtensions

REM Build NexusBridge backend into a standalone EXE (Windows)
REM - Builds backend only (FastAPI via uvicorn)
REM - Optionally builds frontend (uncomment section)
REM Prereqs: Python installed and available on PATH.

set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

set BACKEND_DIR=%ROOT%\apps\backend-python
set FRONTEND_DIR=%ROOT%\apps\frontend
set DIST_DIR=%ROOT%\dist-exe

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%" >nul

echo.
echo === Building frontend bundle ===
pushd "%FRONTEND_DIR%"
call npm install
call npm run build
popd

REM Copy frontend dist next to EXE for backend to serve
if exist "%DIST_DIR%\frontend" rmdir /s /q "%DIST_DIR%\frontend"
if exist "%FRONTEND_DIR%\dist" xcopy /E /I /Y "%FRONTEND_DIR%\dist" "%DIST_DIR%\frontend" >nul

echo.
echo === Building backend EXE ===
pushd "%BACKEND_DIR%"

if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

REM Clean previous PyInstaller outputs
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build exe
pyinstaller --noconfirm --clean --onefile --name NexusBridge --collect-all ldap3 --collect-all cryptography --collect-submodules passlib.handlers --hidden-import passlib.handlers.bcrypt run_exe.py

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%" >nul
if exist "%DIST_DIR%\NexusBridge.exe" del /f /q "%DIST_DIR%\NexusBridge.exe" >nul
copy /Y dist\NexusBridge.exe "%DIST_DIR%\NexusBridge.exe" >nul

REM Copy runtime files next to the EXE (so double-click run works)
if exist "%ROOT%\config.yaml" copy /Y "%ROOT%\config.yaml" "%DIST_DIR%\config.yaml" >nul
if not exist "%DIST_DIR%\.env" (
  if exist "%ROOT%\.env" (
    copy /Y "%ROOT%\.env" "%DIST_DIR%\.env" >nul
  ) else (
    > "%DIST_DIR%\.env" echo JWT_SECRET=
    >> "%DIST_DIR%\.env" echo ENCRYPTION_KEY_BASE64=
    >> "%DIST_DIR%\.env" echo ADMIN_EMAIL=
    >> "%DIST_DIR%\.env" echo ADMIN_PASSWORD=
  )
)

REM Create a run wrapper that logs output and keeps the window open
(
  echo @echo off
  echo setlocal EnableExtensions
  echo set "DIR=%%~dp0"
  echo if "%%DIR:~-1%%"=="\" set "DIR=%%DIR:~0,-1%%"
  echo if not exist "%%DIR%%\logs" mkdir "%%DIR%%\logs" ^>nul
  echo echo Starting NexusBridge... ^> "%%DIR%%\logs\exe-stdout.log"
  echo echo Time: %%DATE%% %%TIME%% ^>^> "%%DIR%%\logs\exe-stdout.log"
  echo "%%DIR%%\NexusBridge.exe" ^>^> "%%DIR%%\logs\exe-stdout.log" 2^> "%%DIR%%\logs\exe-stderr.log"
  echo echo.
  echo echo If it crashed, check:
  echo echo - %%DIR%%\logs\exe-stderr.log
  echo echo - %%DIR%%\logs\exe-stdout.log
  echo echo - %%DIR%%\logs\exe-startup.log
  echo echo - %%DIR%%\logs\exe-crash.log
  echo pause
  echo endlocal
) > "%DIST_DIR%\run-nexusbridge.bat"

echo.
echo Built file details:
powershell -NoProfile -Command "Get-Item '%DIST_DIR%\NexusBridge.exe' | Select-Object FullName,Length,LastWriteTime | Format-List"

echo.
echo EXE created at: %DIST_DIR%\NexusBridge.exe
echo Run it using: %DIST_DIR%\run-nexusbridge.bat
echo.
echo IMPORTANT:
echo - Place .env next to the exe (repo root) or set env vars in the shell.
echo - Ensure ENCRYPTION_KEY_BASE64 and JWT_SECRET are set.
echo - Default port is 3000 (set NB_PORT to change).
echo.

popd
endlocal
