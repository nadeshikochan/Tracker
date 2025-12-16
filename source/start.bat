@echo off
REM 移除 chcp 65001 可能导致的兼容性闪退问题，如果乱码请恢复
chcp 65001 >nul

cd /d "%~dp0"
title Python项目启动器(调试版)

setlocal EnableDelayedExpansion

echo ==========================================
echo       正在初始化环境 (调试模式)
echo ==========================================
echo.

REM ========= 1. 检查 Python =========
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [错误] 未检测到 Python 或未加入 PATH。
    echo.
    pause
    goto END
)

REM ========= 2. 虚拟环境 =========
if not exist "venv" (
    echo [1/4] 正在创建虚拟环境...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo [错误] 创建虚拟环境失败！
        echo.
        pause
        goto END
    )
) else (
    echo [1/4] 检测到现有虚拟环境。
)

call venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [错误] 无法激活虚拟环境。
    pause
    goto END
)

REM ========= 3. 依赖 =========
if exist "requirements.txt" (
    echo [2/4] 正在安装依赖...
    REM 增加 --no-cache-dir 尝试解决部分安装崩溃问题
    pip install -r requirements.txt
    
    REM 关键：检查 pip 是否报错
    if !errorlevel! neq 0 (
        echo.
        echo ==========================================
        echo [严重错误] 依赖安装失败！
        echo ==========================================
        pause
        goto END
    )
) else (
    echo [跳过] 未找到 requirements.txt
)

echo.


REM ========= 4. 配置检查 =========
echo [3/4] 正在检查配置文件...



(
echo import json, os, sys
echo cfg='config.json'
echo d={"api_key":"","base_url":"https://api-inference.modelscope.cn/v1/","model":"Qwen/Qwen2.5-72B-Instruct","check_interval":30,"batch_size":5}
echo if not os.path.exists(cfg^):
echo     json.dump(d,open(cfg,'w',encoding='utf-8'^),indent=4,ensure_ascii=False^);sys.exit(2^)
echo try:
echo     data=json.load(open(cfg,'r',encoding='utf-8'^)^)
echo     k=str(data.get("api_key",""^)^).strip(^)
echo     sys.exit(0 if k else 1^)
echo except: sys.exit(1^)
) > _check_conf.py

python _check_conf.py
set CHECK_RESULT=!errorlevel!
if exist _check_conf.py del _check_conf.py

if !CHECK_RESULT!==2 (
    echo.
    echo [提示] 已自动生成 config.json。
    echo 请打开 config.json 填入 API Key 后重新运行。
    pause
    goto END
)



REM ========= 5. 启动主程序 =========
echo [4/4] 启动 launcher.py...
echo ------------------------------------------
python launcher.py
if !errorlevel! neq 0 (
    echo.
    echo [程序崩溃] 运行结束，状态码：!errorlevel!
) else (
    echo [程序结束] 运行完毕。
)

:END
echo.
echo 按任意键退出...
pause >nul
