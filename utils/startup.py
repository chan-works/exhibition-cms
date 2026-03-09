"""Windows 시작 시 자동 실행 등록/해제 유틸리티."""
import sys
import logging

log = logging.getLogger(__name__)

APP_NAME = "ExhibitionCMS"
REG_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_path() -> str:
    """현재 실행 파일 경로 반환."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # 개발 환경에서는 main.py 절대경로
    import os
    return os.path.abspath(sys.argv[0])


def is_startup_enabled() -> bool:
    """Windows 시작 프로그램에 등록되어 있으면 True."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def enable_startup() -> bool:
    """Windows 시작 프로그램에 등록. 성공하면 True."""
    try:
        import winreg
        exe = _get_exe_path()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        winreg.CloseKey(key)
        log.info("자동 시작 등록: %s", exe)
        return True
    except Exception as e:
        log.warning("자동 시작 등록 실패: %s", e)
        return False


def disable_startup() -> bool:
    """Windows 시작 프로그램에서 제거. 성공하면 True."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0,
            winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        log.info("자동 시작 해제")
        return True
    except Exception as e:
        log.warning("자동 시작 해제 실패: %s", e)
        return False
