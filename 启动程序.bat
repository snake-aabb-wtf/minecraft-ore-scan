@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Minecraft 矿物扫描工具
echo ========================================
echo.

echo [1/2] 检查 Python 依赖...
python -c "import nbtlib, openpyxl" 2>nul
if errorlevel 1 (
    echo 正在安装依赖包...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 依赖安装失败，请检查 Python 和 pip 是否正确配置
        pause
        exit /b 1
    )
) else (
    echo 依赖已就绪
)

echo.
echo [2/2] 启动程序...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo 程序异常退出
    pause
)
