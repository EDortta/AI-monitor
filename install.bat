@echo off
rem install.bat — create venv, install deps, register Task Scheduler autostart
setlocal enabledelayedexpansion

set "DIR=%~dp0"
set "VENV=%DIR%.venv"

echo [agent-monitor] Creating venv...
python -m venv "%VENV%"
"%VENV%\Scripts\pip" install --upgrade pip -q
"%VENV%\Scripts\pip" install -r "%DIR%requirements.txt" -q
echo [agent-monitor] Dependencies installed.

set "TASK=AgentMonitor"
schtasks /query /tn "%TASK%" >nul 2>&1 && (
    schtasks /delete /tn "%TASK%" /f >nul 2>&1
)

schtasks /create /tn "%TASK%" ^
  /tr "\"%VENV%\Scripts\pythonw.exe\" \"%DIR%monitor.py\"" ^
  /sc ONLOGON /ru "%USERNAME%" /rl LIMITED /f >nul

echo [agent-monitor] Task Scheduler entry '%TASK%' created (runs at logon).
echo [agent-monitor] Run now: "%VENV%\Scripts\pythonw.exe" "%DIR%monitor.py"
endlocal
