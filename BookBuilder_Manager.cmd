@echo off
rem Book Builder: Local Application Manager (Windows).
rem Double-click this file, or run it from Command Prompt or PowerShell. All the work is done by
rem tools\manage.py; this file only finds Python and starts it from the Book Builder folder.
setlocal EnableExtensions
title Book Builder Manager
cd /d "%~dp0"

rem BB_PY is the program (always quoted when used, so folders with spaces work); BB_PYARG an optional flag.
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
  echo Python 3.10 or newer is needed and wasn't found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo then run this file again.
  echo.
  pause
  exit /b 1
)

rem Any arguments go straight to the manager (for example: BookBuilder_Manager.cmd status).
if not "%~1"=="" (
  "%BB_PY%" %BB_PYARG% "%~dp0tools\manage.py" %*
  rem plain "exit /b" keeps the manager's exit code (%%ERRORLEVEL%% in a block is read too early)
  exit /b
)

"%BB_PY%" %BB_PYARG% "%~dp0tools\manage.py"
set "BB_CODE=%ERRORLEVEL%"
if not "%BB_CODE%"=="0" (
  echo.
  echo The manager stopped with exit code %BB_CODE%.
  pause
)
exit /b %BB_CODE%
