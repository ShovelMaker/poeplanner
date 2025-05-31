# src/utils.py (새 파일)
import sys
import os

def resource_path(relative_path):
    """ 개발 환경과 PyInstaller로 배포된 환경 모두에서 리소스 파일의 절대 경로를 반환합니다. """
    try:
        # PyInstaller는 실행 시 _MEIPASS라는 임시 폴더 경로를 sys 모듈에 추가합니다.
        # 이 폴더 안에 번들된 파일들이 들어있습니다.
        base_path = sys._MEIPASS
    except Exception:
        # PyInstaller로 실행되지 않은 경우 (개발 환경)
        # 이 utils.py 파일은 src 폴더 안에 있으므로,
        # 프로젝트 루트 폴더는 현재 파일 위치의 부모 폴더의 부모 폴더가 됩니다.
        # 만약 utils.py를 프로젝트 루트에 둔다면 base_path = os.path.abspath(".") 로 변경해야 합니다.
        # 현재는 src/utils.py 기준입니다.
        # config.ini, api_keys.txt, resources/ 등은 프로젝트 루트를 기준으로 찾습니다.
        # 이 resource_path 함수가 app_planner.py나 guide.py 등 src 폴더 내 다른 파일에서 호출될 때,
        # 그 파일들의 위치를 기준으로 프로젝트 루트를 찾아야 합니다.
        # 따라서, 호출하는 파일의 위치를 기준으로 상대 경로를 계산하는 것이 더 일반적입니다.
        # 여기서는 프로젝트 루트에 파일이 있다고 가정하고, 이 함수를 호출하는 스크립트가 src/ 에 있다고 가정합니다.
        
        # 이 함수가 src/utils.py에 있고, config.ini 등이 프로젝트 루트에 있다면:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # 만약 이 함수가 app_planner.py에 직접 정의된다면, 그 파일 위치 기준이 됨.
        
    return os.path.join(base_path, relative_path)

if __name__ == '__main__':
    # 간단한 테스트
    print(f"Current base_path would be: {resource_path('')}")
    # 예시: print(resource_path('config.ini'))