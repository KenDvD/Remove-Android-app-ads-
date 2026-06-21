@echo off
chcp 65001 >nul
echo ========================================
echo   广告移除工具 - 打包构建脚本
echo ========================================
echo.

echo [1/2] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 依赖安装失败！
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] PyInstaller 打包 (--clean)...
pyinstaller --clean remove_ads_gui.spec
if %errorlevel% neq 0 (
    echo 打包失败！
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================
echo   构建完成！
echo   输出: dist\remove_ads_gui.exe
echo ========================================
pause
