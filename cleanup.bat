@echo off
REM Automatyczny cleanup projektu Sejm Highlights Final
REM Autor: Claude AI Assistant
REM Data: 2025-12-05

echo ============================================
echo    SEJM HIGHLIGHTS CLEANUP SCRIPT (Windows)
echo ============================================
echo.

REM === KROK 1: Cleanup cache ===
echo [1/5] Cleaning local cache files...

if exist "__pycache__" (
    echo   Removing __pycache__/
    rmdir /s /q __pycache__
)

for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc 2>nul

if exist ".ruff_cache" (
    echo   Removing .ruff_cache/
    rmdir /s /q .ruff_cache
)

if exist "temp" (
    echo   Cleaning temp/
    del /q temp\* 2>nul
    for /d %%p in (temp\*) do rmdir /s /q "%%p"
)

echo   [OK] Cache cleaned
echo.

REM === KROK 2: Backup requirements ===
echo [2/5] Backing up requirements...

if exist "venv\Scripts\activate.bat" (
    echo   Generating fresh requirements.txt...
    call venv\Scripts\activate.bat
    pip freeze > requirements_backup.txt
    call deactivate
    echo   [OK] Requirements saved to requirements_backup.txt
) else if exist "venv311\Scripts\activate.bat" (
    echo   Generating fresh requirements.txt...
    call venv311\Scripts\activate.bat
    pip freeze > requirements_backup.txt
    call deactivate
    echo   [OK] Requirements saved to requirements_backup.txt
) else (
    echo   [SKIP] No venv found
)
echo.

REM === KROK 3: Remove venv ===
echo [3/5] Virtual environments...
echo WARNING: This will remove venv/ and venv311/
echo You can recreate with: python -m venv venv
echo.
set /p REPLY="Remove virtual environments? (y/N): "

if /i "%REPLY%"=="y" (
    if exist "venv" (
        echo   Removing venv/
        rmdir /s /q venv
    )
    if exist "venv311" (
        echo   Removing venv311/
        rmdir /s /q venv311
    )
    echo   [OK] Virtual environments removed
) else (
    echo   [SKIP] Keeping venv
)
echo.

REM === KROK 4: Move dev tools ===
echo [4/5] Git cleanup - moving dev tools...

if not exist "dev" mkdir dev

set MOVED_COUNT=0

if exist "APP_URL_INTEGRATION_SNIPPET.py" (
    git mv APP_URL_INTEGRATION_SNIPPET.py dev\ 2>nul || move APP_URL_INTEGRATION_SNIPPET.py dev\
    set /a MOVED_COUNT+=1
)

if exist "check_srt.py" (
    git mv check_srt.py dev\ 2>nul || move check_srt.py dev\
    set /a MOVED_COUNT+=1
)

if exist "finish_processing.py" (
    git mv finish_processing.py dev\ 2>nul || move finish_processing.py dev\
    set /a MOVED_COUNT+=1
)

if exist "list_youtube_channels.py" (
    git mv list_youtube_channels.py dev\ 2>nul || move list_youtube_channels.py dev\
    set /a MOVED_COUNT+=1
)

if exist "quick_export.py" (
    git mv quick_export.py dev\ 2>nul || move quick_export.py dev\
    set /a MOVED_COUNT+=1
)

if exist "regenerate_hardsub.py" (
    git mv regenerate_hardsub.py dev\ 2>nul || move regenerate_hardsub.py dev\
    set /a MOVED_COUNT+=1
)

if exist "monitor_gpu.py" (
    git mv monitor_gpu.py dev\ 2>nul || move monitor_gpu.py dev\
    set /a MOVED_COUNT+=1
)

if exist "test_correct_channel.py" (
    git mv test_correct_channel.py dev\ 2>nul || move test_correct_channel.py dev\
    set /a MOVED_COUNT+=1
)

if exist "test_youtube_auth.py" (
    git mv test_youtube_auth.py dev\ 2>nul || move test_youtube_auth.py dev\
    set /a MOVED_COUNT+=1
)

echo   [OK] Moved dev tools to dev/
echo.

REM === KROK 5: Update .gitignore ===
echo [5/5] Updating .gitignore...

findstr /C:"# Project-specific" .gitignore >nul 2>&1
if errorlevel 1 (
    echo. >> .gitignore
    echo # Project-specific >> .gitignore
    echo output/ >> .gitignore
    echo temp/ >> .gitignore
    echo downloads/ >> .gitignore
    echo models/*.pt >> .gitignore
    echo models/*.bin >> .gitignore
    echo venv311/ >> .gitignore
    echo. >> .gitignore
    echo # Development >> .gitignore
    echo # dev/ >> .gitignore
    echo. >> .gitignore
    echo # System files >> .gitignore
    echo *.swp >> .gitignore
    echo *.swo >> .gitignore
    echo *~ >> .gitignore
    echo .DS_Store >> .gitignore
    echo Thumbs.db >> .gitignore
    echo. >> .gitignore
    echo # IDE >> .gitignore
    echo .vscode/ >> .gitignore
    echo .idea/ >> .gitignore
    echo *.code-workspace >> .gitignore

    echo   [OK] .gitignore updated
) else (
    echo   [SKIP] .gitignore already updated
)
echo.

REM === Git status ===
echo Git Status:
git status --short

echo.
echo ============================================
echo    CLEANUP COMPLETE!
echo ============================================
echo.
echo Next steps:
echo   1. Review changes: git status
echo   2. Commit: git add . ^&^& git commit -m "chore: Project cleanup"
echo   3. Recreate venv: python -m venv venv
echo      Then: venv\Scripts\activate ^&^& pip install -r requirements.txt
echo.
echo See CLEANUP_AND_STABILIZATION_PLAN.md for full plan
echo.
pause
