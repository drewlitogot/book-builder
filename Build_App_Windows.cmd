@echo off
rem Build a launchable Book Builder for Windows (a folder with Python, Pandoc and Typst inside).
rem Double-click this file. The result is in dist\packages.
rem To build for other systems too:  Build_App_Windows.cmd --target all
setlocal EnableExtensions
title Build Book Builder
cd /d "%~dp0"
set "BB_PY="
set "BB_PYARG="
if exist "%~dp0.venv\Scripts\python.exe" set "BB_PY=%~dp0.venv\Scripts\python.exe"
if not defined BB_PY (
  where py >nul 2>nul && set "BB_PY=py" && set "BB_PYARG=-3"
)
if not defined BB_PY (
  where python >nul 2>nul && set "BB_PY=python"
)
if not defined BB_PY (
  echo Python 3.10 or newer is needed to build. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
"%BB_PY%" %BB_PYARG% "%~dp0tools\package_app.py" %*
set "BB_CODE=%ERRORLEVEL%"
if "%BB_CODE%"=="0" start "" "%~dp0dist\packages"
pause
exit /b %BB_CODE%
