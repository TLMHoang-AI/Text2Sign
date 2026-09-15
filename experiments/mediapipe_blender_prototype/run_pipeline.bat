@echo off
setlocal

REM ==============================================================================
REM Text-to-Sign Pipeline Launcher
REM ==============================================================================

REM --- Configuration ---
REM Set the path to your Blender executable here if it's not in your System PATH.
REM Example: set BLENDER_EXE="C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
set BLENDER_EXE="D:\Workplace\blender.exe"

REM --- Step 1: Environment Setup ---
echo [1/3] Activating Virtual Environment...
set VENV_PATH=..\env_v1
if exist "%VENV_PATH%\Scripts\activate.bat" (
    call "%VENV_PATH%\Scripts\activate.bat"
) else (
    echo Error: Virtual environment not found at %VENV_PATH%
    echo Please run the setup steps first.
    pause
    exit /b 1
)

REM --- Step 2: Motion Extraction ---
echo [2/3] Checking Motion Data...
if exist "motion_data.json" (
    echo Motion data found. Skipping extraction to save time.
) else (
    echo Running Motion Extraction...
    python extract_motion.py
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Motion extraction failed.
        pause
        exit /b %ERRORLEVEL%
    )
)

REM --- Step 3: Blender Visualization ---
echo [3/3] Launching Blender...
echo If Blender does not open, please edit this file and set BLENDER_EXE to the correct path.
echo.

%BLENDER_EXE% --python blender_import.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Error: Could not launch Blender.
    echo Please ensure 'blender' is in your PATH or edit this script to set BLENDER_EXE.
    pause
)

endlocal
