@echo off
cd backend
echo Starting BiliNote backend server...
python -m uvicorn main:app --reload --port 8000 --host 127.0.0.1
pause 