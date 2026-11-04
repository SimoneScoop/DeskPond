@echo off
rem 把 Windows 版打包成一个文件夹（里面有 DeskPond.exe），可以拷到别的 Windows 电脑上直接用。
rem 用法：在项目文件夹里双击，或在命令行里运行 tools\build_windows.bat
rem 打出来的东西在 dist\DeskPond\ ；不含任何游戏素材（运行时从本机游戏读取）。
cd /d "%~dp0\.."
python -m pip install -r requirements-windows.txt pyinstaller || goto :error
python -m PyInstaller --noconfirm --windowed --name DeskPond ^
  --collect-submodules src run_win.pyw || goto :error
echo.
echo 打包好了：dist\DeskPond\DeskPond.exe
pause
exit /b 0
:error
echo 打包失败，请把上面的报错发给开发者。
pause
exit /b 1
