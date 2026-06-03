@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   PremiumNumber Miner v3.0 - 一键编译安装包
echo   适配 v3 合约 (CREATE2 地址挖矿)
echo ==========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装或未加入 PATH.
    echo 请安装 Python 3.10+ : https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败.
    pause
    exit /b 1
)

echo.
echo [2/3] 打包 .exe 安装文件...

REM 构建 PyInstaller 命令参数
set PYINST_ARGS=--noconfirm --onefile --windowed --name "PremiumNumberMiner" --icon "icon.ico"
set PYINST_ARGS=%PYINST_ARGS% --add-data "icon_circle.png;." --add-data "icon.ico;."

REM 检查 GPU 模块
if exist gpu_miner.py (
    set PYINST_ARGS=%PYINST_ARGS% --add-data "gpu_miner.py;."
    echo        包含 GPU 挖矿模块...
)

REM 检查 config.yaml
if exist config.yaml (
    set PYINST_ARGS=%PYINST_ARGS% --add-data "config.yaml;."
    echo        包含默认配置文件...
)

set PYINST_ARGS=%PYINST_ARGS% --hidden-import "web3" --hidden-import "eth_abi" --hidden-import "eth_abi.packed"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "eth_account" --hidden-import "eth_utils" --hidden-import "eth_typing"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "eth_hash.auto" --hidden-import "eth_hash.backends.pycryptodome"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "Crypto.Hash.keccak" --hidden-import "Crypto.Hash"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "numpy" --hidden-import "pyopencl" --hidden-import "pyopencl.array" --hidden-import "pyopencl.clrandom"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "cytoolz" --hidden-import "cytoolz.utils" --hidden-import "cytoolz._signatures"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "PIL" --hidden-import "multiprocessing" --hidden-import "multiprocessing.pool"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "requests" --hidden-import "yaml"
set PYINST_ARGS=%PYINST_ARGS% --collect-all "web3" --collect-all "eth_abi" --collect-all "eth_account"

python -m PyInstaller %PYINST_ARGS% premium_miner.py

if errorlevel 1 (
    echo [错误] 打包失败.
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成!
echo.
echo ==========================================
echo   EXE 文件位置: dist\PremiumNumberMiner.exe
echo ==========================================
echo.
echo   使用方法:
echo   1. 双击 dist\PremiumNumberMiner.exe 即可运行
echo   2. 首次运行需在界面填写私钥并连接钱包
echo   3. 或编辑 config.yaml 配置私钥后运行
echo   4. 切换到"挖矿"页, 点击"开始挖矿"
echo.
pause
