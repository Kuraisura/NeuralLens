@echo off
echo ========================================
echo Neural Eye - Quick Setup
echo ========================================
echo.

echo Installing dependencies...
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies
    echo Please make sure Python and pip are installed
    pause
    exit /b 1
)

echo.
echo ========================================
echo Running automated setup...
echo ========================================
python setup.py

if %errorlevel% neq 0 (
    echo.
    echo Setup encountered errors. Please check the output above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Edit .env file (set your SECRET_KEY)
echo 2. Run: python app.py
echo.
echo For more info, read: IMPLEMENTATION_GUIDE.md
echo.
pause
