@echo off
REM 一键构建：Vivado 2026.1 + build.config。可用 VIVADO_BAT 覆盖 Vivado 路径。
setlocal
cd /d "%~dp0"
if "%VIVADO_BAT%"=="" (
  echo ERROR: 未设置 VIVADO_BAT
  echo 请先设置环境变量 VIVADO_BAT 指向 Vivado 2026.1 的 vivado.bat
  exit /b 1
)
if not exist "%VIVADO_BAT%" (
  echo ERROR: 找不到 Vivado：%VIVADO_BAT%
  exit /b 1
)
if not exist "logs" mkdir logs
"%VIVADO_BAT%" -mode batch -log "logs\vivado.log" -journal "logs\vivado.jou" -source "build_driver.tcl"
