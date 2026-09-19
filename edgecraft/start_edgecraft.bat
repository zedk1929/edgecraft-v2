@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Setting up Edgecraft for the first time...
  py -3 -m venv .venv
  if errorlevel 1 goto :python_error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :install_error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :install_error
)

start "Edgecraft" ".venv\Scripts\pythonw.exe" edgecraft_app.py
exit /b 0

:python_error
echo.
echo Python 3 was not found. Install it from https://www.python.org/downloads/
pause
exit /b 1

:install_error
echo.
echo Edgecraft could not install its numerical dependencies.
echo Check your internet connection, then run this file again.
pause
exit /b 1
