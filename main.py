'''
이 코드의 모든 저작권은 StockCopilot(yoshikime@gmail.com)에게 있습니다. 
all rights reserved to StockCopilot(yoshikime@gmail.com)
저작권자의 허가없이 무단으로 복제, 수정, 배포 시 법적인 제재를 받을 수 있습니다.
'''

# -*- coding: utf-8 -*-

'''
pip install -r requirements.txt 패키지 종합 설치 명령어. 터미널에서 실행. 

'''


import dotenv
import os
import sys
import logging
import tempfile
import shutil
import time
import atexit
from menugui import MenuGUI
from PyQt5.QtWidgets import QApplication, QMessageBox

# 환경 변수를 가져옵니다. 
dotenv.load_dotenv()

logging.basicConfig(
    filename=os.path.join(os.getcwd().replace('\\', '/'), 'app.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def cleanup_old_cookies():
    # 현재 디렉토리의 모든 파일을 탐색
    current_dir = os.getcwd()
    for file_name in os.listdir(current_dir):
        # 'cookies_'로 시작하고 '.pkl'로 끝나는 파일 확인
        if file_name.startswith('cookies_') and file_name.endswith('.pkl'):
            # 파일 경로 생성
            cookie_file_path = os.path.join(current_dir, file_name)
            # 파일 제거
            os.remove(cookie_file_path)
            print(f'쿠키 파일을 제거합니다: {cookie_file_path}')
        
def cleanup_old_images():
    image_dir = os.getcwd().replace('\\', '/')
    for file_name in os.listdir(image_dir):
        if file_name.startswith('today_shopping'):
            file_path = os.path.join(image_dir, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f'이미지 파일을 제거합니다: {file_path}')

def cleanup_old_mei_folders():
    """
    현재 사용 중인 _MEI 폴더를 제외하고 모든 _MEI 폴더를 삭제합니다.
    """
    # 현재 사용 중인 _MEI 폴더를 확인합니다.
    current_mei_folder = None
    if hasattr(sys, '_MEIPASS'):
        current_mei_folder = sys._MEIPASS

    # 시스템의 임시 디렉토리 위치를 가져옵니다.
    temp_dir = tempfile.gettempdir()

    # 임시 디렉토리 내의 모든 파일 및 폴더를 탐색합니다.
    for item in os.listdir(temp_dir):
        item_path = os.path.join(temp_dir, item)

        # 이름이 _MEI로 시작하는 디렉토리인 경우
        if os.path.isdir(item_path) and item.startswith('_MEI'):
            # 현재 사용 중인 _MEI 폴더는 건너뜁니다.
            if current_mei_folder and os.path.abspath(item_path) == os.path.abspath(current_mei_folder):
                print(f"현재 사용중인 임시폴더는 다음 실행 때 삭제 됩니다: {item_path}" )
                continue

            # 다른 _MEI 폴더들을 삭제합니다.
            try:
                shutil.rmtree(item_path)
                print(f"오래된 임시파일을 삭제합니다.: {item_path}")
            except Exception as e:
                print(f"삭제에 실패하였습니다. 수동으로 삭제하여 주세요. {item_path}: {e}")

  
def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Ignore keyboard interrupts to allow graceful shutdown
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    
def main():
    sys.excepthook = log_uncaught_exceptions 
    app = QApplication(sys.argv)

    # MenuGUI 인스턴스 생성 및 표시
    menu_gui = MenuGUI()
    menu_gui.show()
    
    # 프로그램 종료 시 쿠키 파일 및 이미지 파일 삭제
    atexit.register(cleanup_old_cookies)
    atexit.register(cleanup_old_images)
    atexit.register(cleanup_old_mei_folders)
    
    app.exec_()  # GUI 이벤트 루프 시작

if __name__ == '__main__':
    main()

