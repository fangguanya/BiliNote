@echo off
chcp 65001 >nul
title 安装 BiliNote 依赖（CUDA 13）

echo.
echo ========================================
echo 🚀 安装 BiliNote 依赖（CUDA 13）
echo ========================================
echo.

call conda activate bilinote
if %errorlevel% neq 0 (
    echo ❌ conda 环境激活失败
    pause
    exit /b 1
)

echo 📌 当前环境: bilinote
echo.

echo ========================================
echo 📥 步骤 1: 安装 PyTorch（CUDA 13）
echo ========================================
echo.
echo 💡 从 PyTorch 官方源安装支持 CUDA 13 的版本
echo.

pip install torch==2.9.0 torchvision==0.24.0 torchaudio==2.9.0 --index-url https://download.pytorch.org/whl/cu130

if %errorlevel% neq 0 (
    echo ❌ PyTorch 安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 📥 步骤 2: 安装其他依赖
echo ========================================
echo.

pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 🧪 步骤 3: 验证安装
echo ========================================
echo.

echo 🔍 检查 PyTorch 版本...
python -c "import torch; print(f'PyTorch: {torch.__version__}')"

echo.
echo 🔍 检查 CUDA 支持...
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'CUDA Version: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')" 2>nul

echo.
echo 🔍 检查 Whisper...
python -c "import whisper; print('Whisper: installed')"

echo.
echo ========================================
echo ✅ 安装完成！
echo ========================================
echo.
echo 💡 下一步：
echo    运行 start_server.bat 启动服务器
echo.

pause

