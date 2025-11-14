@echo off
echo Starting BiliNote backend server...
echo.
call conda activate bilinote
echo.
cd backend
python main.py
pause 