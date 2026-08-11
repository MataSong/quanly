@echo off
REM Quanly Windows 入口:定位 git-bash 或 WSL 的 bash,转调 quanly.sh。
setlocal

REM 1) 优先常见 git-bash 路径
set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"

REM 2) 回退 PATH 中的 bash(git-bash 已加入 PATH 的情况)
if not defined BASH_EXE for %%i in (bash.exe) do if not defined BASH_EXE set "BASH_EXE=%%~$PATH:i"

if defined BASH_EXE (
  "%BASH_EXE%" "%~dp0quanly.sh" %*
  goto :eof
)

REM 3) 再回退 WSL
where wsl >nul 2>nul
if %errorlevel%==0 (
  wsl bash "./quanly.sh" %*
  goto :eof
)

echo [x] 未找到 bash。请安装 Git for Windows(自带 git-bash):
echo     https://git-scm.com/download/win
echo 安装后重新运行本命令。
exit /b 1
