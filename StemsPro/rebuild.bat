@echo off
REM Set your Android SDK path:
REM set ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk
REM set ANDROID_SDK_ROOT=%ANDROID_HOME%
cd /d "%~dp0"
echo Building Stems Pro...
call gradlew.bat assembleDebug --console=plain 2>&1
if %errorlevel% equ 0 (
    echo.
    echo SUCCESS! APK:
    dir /b "app\build\outputs\apk\debug\*.apk"
) else (
    echo FAILED
)
pause
