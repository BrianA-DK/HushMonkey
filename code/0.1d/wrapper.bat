@echo off
:: wrapper.bat — Runs main.py and acts on its return code.
::   RC=0  -> restart main.py
::   RC=2  -> reboot the machine
::   RC=3  -> power off the machine
::	 RC=9  -> Exit wrapper
::   other -> log RC and restart the application

setlocal enabledelayedexpansion

set PYTHON=python
set MAIN=%~dp0main.py

:loop
    call :log "Starting main.py ..."
    "%PYTHON%" "%MAIN%"
    set RC=%ERRORLEVEL%
    call :log "main.py exited with RC=!RC!"

    if !RC! == 0 (
        call :log "RC=0 - restarting ..."
        goto loop
    )
    if !RC! == 2 (
        call :log "RC=2 - rebooting machine ..."
        shutdown /r /t 5 /c "wrapper.bat: RC=2 triggered reboot"
        exit /b 0
    )
    if !RC! == 3 (
        call :log "RC=3 - powering off machine ..."
        shutdown /s /t 5 /c "wrapper.bat: RC=3 triggered shutdown"
        exit /b 0
    )
	if !RC! == 9 (
        call :log "RC=9 - exit wrapper ..."
        exit /b 0
    )

    call :log "RC=!RC! - unhandled, restarting application"
    goto loop

:log
    for /f "tokens=1-2 delims=T" %%a in ("%DATE%T%TIME%") do (
        echo [%%a %%b] %~1
    )
    exit /b 0
