@echo off
cd /d "%~dp0"
py -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Install Python 3 from python.org and try again.
  pause
  exit /b 1
)
echo.
echo RX75 Stream Pad dependencies installed.
pause
