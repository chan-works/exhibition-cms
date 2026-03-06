@echo off
chcp 65001 > nul
echo ==========================================
echo   Exhibition CMS - Windows 빌드 스크립트
echo ==========================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.11 이상을 설치하세요.
    pause
    exit /b 1
)

echo [1/4] 의존성 설치 중...
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 (
    echo [오류] 의존성 설치 실패
    pause
    exit /b 1
)

echo.
echo [2/4] exe 파일 빌드 중...
pyinstaller build.spec --clean
if errorlevel 1 (
    echo [오류] PyInstaller 빌드 실패
    pause
    exit /b 1
)

echo.
echo [3/4] Inno Setup 확인 중...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo [안내] Inno Setup이 없습니다. exe 단독 파일만 생성합니다.
    echo        설치 파일을 만들려면 https://jrsoftware.org/isdl.php 에서 설치하세요.
    goto :done_no_installer
)

echo [4/4] 설치 파일(Setup.exe) 생성 중...
%ISCC% installer.iss
if errorlevel 1 (
    echo [오류] Inno Setup 빌드 실패
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   빌드 완료!
echo   설치 파일: Output\ExhibitionCMS-Setup-v1.0.0.exe
echo   단독 exe:  dist\ExhibitionCMS.exe
echo ==========================================
goto :end

:done_no_installer
echo.
echo ==========================================
echo   빌드 완료!
echo   단독 exe: dist\ExhibitionCMS.exe
echo ==========================================

:end
pause
