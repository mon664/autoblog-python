import os
import sys
import dotenv
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QComboBox,
    QPushButton, QMessageBox, QLineEdit, QInputDialog, QGroupBox, QHBoxLayout,
    QDialog, QDialogButtonBox, QSizePolicy # Import QDialog and QDialogButtonBox for the interval pop-up
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from selenium.common.exceptions import (
    StaleElementReferenceException, TimeoutException, NoSuchElementException,
    NoSuchWindowException, WebDriverException
)

# --- Import external classes ---
# (Imports remain the same)
try:
    from tistory import Tistory
    from keyword_generator import KeywordGenerator
    from blogger import BloggerClient # Assuming file is Blogger.py
except ImportError as e:
    print(f"필수 모듈 임포트 오류: {e}. 해당 파이썬 파일이 있는지 확인하세요.")
    # Define dummy classes if needed
    class Tistory:
        def __init__(self, menu_gui): pass
        def process_auto_tistory(self, mode): pass
    class KeywordGenerator:
        def getKeywords(self, keys): return "키워드 분석 결과 예시"
    class BloggerClient:
        def __init__(self, menu_gui): pass
        def process_auto_blogger(self, mode):
            # Dummy implementation to show access to schedule interval
            interval = getattr(menu_gui, 'selected_schedule_interval', None)
            if interval:
                print(f"[Dummy BloggerClient] Received schedule interval: {interval}")
                # Here you would implement the actual scheduling logic
                return f"Blogger 작업 완료 (예약 간격: {interval})"
            else:
                print("[Dummy BloggerClient] No schedule interval specified.")
                return "Blogger 작업 완료 (즉시 발행)"
            # raise NotImplementedError("BloggerClient not loaded or dummy.")

# --- WorkerThread (No changes needed here) ---
class WorkerThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, menu_gui, client, writing_mode):
        super().__init__()
        self.menu_gui = menu_gui
        self.client = client
        self.writing_mode = writing_mode
        self.platform = menu_gui.selected_platform

    def run(self):
        success = False
        error_message = "알 수 없는 오류 발생"
        result_message = "작업이 성공적으로 완료되었습니다." # Default success message
        try:
            result = None
            if self.platform == "Tistory":
                if self.menu_gui.selected_mode in ["쿠파스 작성", "블로그 작성"]:
                    result = self.client.process_auto_tistory(self.writing_mode)
                else:
                    error_message = "Tistory: 지원하지 않는 작업 모드입니다."

            elif self.platform == "Google Blogger":
                if self.menu_gui.selected_mode in ["쿠파스 작성", "블로그 작성"]:
                    # The client itself now handles the scheduling logic internally
                    # based on menu_gui.selected_schedule_interval
                    result = self.client.process_auto_blogger(self.writing_mode)
                else:
                    error_message = "Blogger: 지원하지 않는 작업 모드입니다."
            else:
                error_message = "알 수 없는 플랫폼입니다."

            # 결과 처리
            if isinstance(result, bool) and result:
                success = True
                # Keep default success message
            elif isinstance(result, str) and "오류" not in result and "실패" not in result and "Error" not in result : # Assume string result is success message unless it indicates error
                success = True
                result_message = result # Use the message returned by the client
            elif isinstance(result, str): # Error message returned
                success = False
                error_message = result
            elif result is None and error_message == "알 수 없는 오류 발생": # Default success case
                 success = True

            # 최종 시그널 발생
            if success:
                self.finished.emit(result_message)
            else:
                self.error.emit(f"작업 실패: {error_message}")
        except (NoSuchWindowException, WebDriverException) as e:
             logging.error(f"브라우저 오류 발생: {e}")
             self.error.emit(f"브라우저 관련 오류가 발생했습니다. 브라우저가 닫혔거나 응답하지 않을 수 있습니다.\n{e}")
        except FileNotFoundError as e:
             logging.error(f"파일 찾기 오류: {e}")
             self.error.emit(f"필수 파일을 찾을 수 없습니다: {e}")
        except ConnectionError as e:
            logging.error(f"연결 오류: {e}")
            self.error.emit(f"연결 또는 인증 오류: {e}")
        except RuntimeError as e:
            logging.error(f"런타임 오류: {e}")
            self.error.emit(f"작업 실행 중 오류: {e}")
        except NotImplementedError as e: # Catch if dummy client is used
            logging.error(f"미구현 기능: {e}")
            self.error.emit(f"기능 미구현 오류: {e}")
        except Exception as e:
            logging.exception("WorkerThread에서 오류 발생")
            self.error.emit(f"작업 중 오류가 발생했습니다: {str(e)}")


# --- Schedule Interval Dialog ---
class ScheduleIntervalDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("예약 간격 선택")
        self.setModal(True) # Make it modal

        layout = QVBoxLayout(self)

        self.label = QLabel("포스팅 예약 간격을 선택하세요:", self)
        layout.addWidget(self.label)

        self.interval_combo = QComboBox(self)
        self.intervals = [f"{i}시간마다" for i in range(2, 9)] # 2시간부터 8시간까지
        self.interval_combo.addItems(self.intervals)
        layout.addWidget(self.interval_combo)

        # Standard buttons (OK, Cancel)
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttonBox.accepted.connect(self.accept) # Connect OK to accept
        self.buttonBox.rejected.connect(self.reject) # Connect Cancel to reject
        layout.addWidget(self.buttonBox)

        self.selected_interval = None

    def accept(self):
        self.selected_interval = self.interval_combo.currentText()
        super().accept() # Close dialog with QDialog.Accepted status

    def get_selected_interval(self):
        return self.selected_interval


class MenuGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoBlog v3 - Platform Selection")
        self.setGeometry(100, 100, 450, 600) # Increased height slightly for new option

        # --- Initial state variables ---
        self.selected_platform = None
        self.env_file_path = None
        self.worker = None

        # --- Variables to store user selections ---
        self.selected_mode = None
        self.use_naver = False
        # Tistory specific
        self.selected_id = None
        self.selected_password = None
        self.selected_tistory_domain = None
        self.selected_category = None
        self.pre_selected_id = None
        self.account_changed = False
        self.use_coupang_link_config = False
        # Blogger specific
        self.selected_blogger_blog_id = None
        self.use_scheduling = False # Added for Blogger scheduling
        self.selected_schedule_interval = None # Added for Blogger scheduling interval
        # Common
        self.selected_ch_id = None
        self.keywords = None
        self.selected_naver_category = None


        # --- Naver Categories (Keep as is) ---
        self.naver_categories = [
            {'cid': '0', 'name': '전체'},
            {'cid': '50000000', 'name': '패션의류'},
            {'cid': '50000001', 'name': '패션잡화'},
            {'cid': '50000002', 'name': '화장품/미용'},
            {'cid': '50000003', 'name': '디지털/가전'},
            {'cid': '50000004', 'name': '가구/인테리어'},
            {'cid': '50000005', 'name': '출산/육아'},
            {'cid': '50000006', 'name': '식품'},
            {'cid': '50000007', 'name': '스포츠/레저'},
            {'cid': '50000008', 'name': '생활/건강'},
            {'cid': '50000009', 'name': '여가/생활편의'},
            {'cid': '50000010', 'name': '면세점'},
            {'cid': '50005542', 'name': '도서'}
        ]

        # --- Central Widget and Layout ---
        self.widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.widget.setLayout(self.main_layout)
        self.setCentralWidget(self.widget)

        # --- Setup Initial Platform Selection UI ---
        self.setup_platform_selection_ui()
        # --- Setup Main UI (but keep hidden initially) ---
        self.setup_main_ui()


    def setup_platform_selection_ui(self):
        """Sets up the initial UI for selecting the platform."""
        self.platform_selection_group = QGroupBox("플랫폼 선택")
        platform_layout = QVBoxLayout()
        self.platform_selection_group.setLayout(platform_layout)

        platform_layout.addWidget(QLabel("사용할 블로그 플랫폼을 선택하세요:"))
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["", "Tistory", "Google Blogger"])
        platform_layout.addWidget(self.platform_combo)

        self.platform_confirm_button = QPushButton("플랫폼 선택 완료")
        self.platform_confirm_button.clicked.connect(self.confirm_platform)
        platform_layout.addWidget(self.platform_confirm_button)

        self.main_layout.addWidget(self.platform_selection_group)

    def confirm_platform(self):
        """Confirms the platform selection and transitions to the main UI."""
        selected = self.platform_combo.currentText()
        if not selected:
            QMessageBox.warning(self, "플랫폼 선택 필요", "작업을 진행할 블로그 플랫폼을 선택해주세요.")
            return

        self.selected_platform = selected # Set the platform
        if self.selected_platform == "Tistory":
            self.env_file_path = 'tistory.env'
        elif self.selected_platform == "Google Blogger":
            self.env_file_path = 'blogger.env'
        else:
            # Should not happen with current combo, but good practice
            QMessageBox.critical(self, "오류", "알 수 없는 플랫폼입니다.")
            return

        # Check for env file *after* setting the path
        if not os.path.exists(self.env_file_path):
            QMessageBox.critical(self, "파일 오류", f"설정 파일 '{self.env_file_path}'을(를) 찾을 수 없습니다.\n프로그램을 종료합니다.")
            sys.exit(1) # Exit if essential config file is missing

        logging.info(f"플랫폼 선택: {self.selected_platform}, 설정 파일: {self.env_file_path}")

        # Hide platform selection, show main UI
        self.platform_selection_group.hide()
        self.show_main_ui_elements()
        self.update_ui_for_platform() # This will now correctly show/hide groups and populate

    def setup_main_ui(self):
        """Sets up the main UI elements (mode, platform groups, buttons)
           These are initially hidden until a platform is confirmed.
        """
        # --- Mode Selection ---
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("1. 작업 모드 선택:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["키워드 분석", "쿠파스 작성", "블로그 작성"])
        self.mode_combo.setCurrentIndex(1) # Default to Coupas
        self.mode_combo.currentTextChanged.connect(self.update_visibility_based_on_mode)
        mode_layout.addWidget(self.mode_combo)
        self.main_layout.addLayout(mode_layout)
        self.mode_combo.parentWidget().findChild(QLabel).hide()
        self.mode_combo.hide()


        # --- Tistory Group Box ---
        self.tistory_group_box = QGroupBox("Tistory 설정")
        tistory_layout = QVBoxLayout()
        self.tistory_group_box.setLayout(tistory_layout)
        # *** Use unique names for Tistory widgets ***
        self.tistory_use_naver_combo = self.create_combo_box("네이버 인기 검색어 사용 (쿠파스):", ["예", "아니요"], tistory_layout)
        self.tistory_id_combo = self.create_combo_box("카카오 계정 선택:", [], tistory_layout)
        self.tistory_id_combo.currentTextChanged.connect(self.update_password)
        self.tistory_channel_combo = self.create_combo_box("쿠팡 채널 ID 선택 (쿠파스):", [], tistory_layout)
        self.tistory_domain_combo = self.create_combo_box("티스토리 도메인 선택:", [], tistory_layout)
        self.tistory_domain_combo.currentTextChanged.connect(self.update_category_combo)
        self.tistory_category_combo = self.create_combo_box("티스토리 카테고리 선택:", [], tistory_layout)
        self.main_layout.addWidget(self.tistory_group_box)
        self.tistory_group_box.hide() # Initially hide

        # --- Google Blogger Group Box ---
        self.blogger_group_box = QGroupBox("Google Blogger 설정")
        blogger_layout = QVBoxLayout()
        self.blogger_group_box.setLayout(blogger_layout)
        # *** Use unique names for Blogger widgets ***
        self.blogger_use_naver_combo = self.create_combo_box("네이버 인기 검색어 사용 (쿠파스):", ["예", "아니요"], blogger_layout)
        self.blogger_channel_combo = self.create_combo_box("쿠팡 채널 ID 선택 (쿠파스):", [], blogger_layout)
        self.blogger_blog_id_combo = self.create_combo_box("작업할 블로그 ID 선택:", [], blogger_layout)
        # *** Added: Blogger Scheduling Combo Box ***
        self.blogger_schedule_combo = self.create_combo_box("예약 포스팅 사용:", ["사용 안함", "사용"], blogger_layout)
        self.blogger_schedule_combo.setCurrentIndex(0) # Default to '사용 안함'
        self.main_layout.addWidget(self.blogger_group_box)
        self.blogger_group_box.hide() # Initially hide

        # --- Bottom Buttons (Start and Back) ---
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("작업 시작")
        self.start_button.clicked.connect(self.start_clicked)
        self.back_button = QPushButton("뒤로가기 (플랫폼 재선택)")
        self.back_button.clicked.connect(self.go_back_to_platform_selection)
        button_layout.addWidget(self.back_button)
        button_layout.addWidget(self.start_button)
        self.main_layout.addLayout(button_layout)
        self.start_button.hide() # Initially hide
        self.back_button.hide()  # Initially hide

    def show_main_ui_elements(self):
        """Helper function to show the main UI elements."""
        self.mode_combo.parentWidget().findChild(QLabel).show()
        self.mode_combo.show()
        # Group boxes are shown/hidden by update_ui_for_platform
        self.start_button.show()
        self.back_button.show()

    def hide_main_ui_elements(self):
        """Helper function to hide the main UI elements."""
        self.mode_combo.parentWidget().findChild(QLabel).hide()
        self.mode_combo.hide()
        self.tistory_group_box.hide()
        self.blogger_group_box.hide()
        self.start_button.hide()
        self.back_button.hide()

    def go_back_to_platform_selection(self):
        """Handles the 'Back' button click to return to platform selection."""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "작업 진행 중", "현재 작업이 실행 중입니다. 완료 후 다시 시도해주세요.")
            return
        self.hide_main_ui_elements()
        self.platform_selection_group.show()
        self.selected_platform = None # Reset platform
        self.env_file_path = None
        self.platform_combo.setCurrentIndex(0) # Reset combo box
        self.setWindowTitle("AutoBlog v3 - Platform Selection")
        logging.info("Returned to platform selection.")

    def update_ui_for_platform(self):
        """Updates the UI based on the selected platform."""
        if not self.selected_platform:
            logging.warning("update_ui_for_platform called with no platform selected.")
            return

        # Hide both group boxes first
        self.tistory_group_box.hide()
        self.blogger_group_box.hide()

        if self.selected_platform == "Tistory":
            self.setWindowTitle(f"AutoBlog v3 - Tistory Mode")
            self.tistory_group_box.show() # Show Tistory group
            self.update_combo_from_env(self.tistory_channel_combo, 'CHANNEL_ID', 'common')
            self.populate_tistory_combos() # Handles ID, Domain
            self.update_category_combo() # Handles Category based on Domain
            self.update_password() # Handles Password based on ID
        elif self.selected_platform == "Google Blogger":
            self.setWindowTitle(f"AutoBlog v3 - Blogger Mode")
            self.blogger_group_box.show() # Show Blogger group
            # *** Populate BLOGGER specific combos ***
            self.update_combo_from_env(self.blogger_channel_combo, 'CHANNEL_ID', 'common')
            self.populate_blogger_combos() # Handles Blog ID

        # Ensure visibility is updated based on the current mode for the *active* group
        self.update_visibility_based_on_mode()
        self.start_button.setEnabled(True)

    # --- Methods for populating combos ---
    def populate_tistory_combos(self):
        """Populates Tistory-specific combo boxes."""
        self.update_combo_from_env(self.tistory_id_combo, 'KAKAO_USERNAME')
        self.update_combo_from_env(self.tistory_domain_combo, 'TISTORY_DOMAINS')

    def populate_blogger_combos(self):
        """Populates Blogger-specific combo boxes."""
        self.update_combo_from_env(self.blogger_blog_id_combo, 'BLOGGER_BLOG_IDS')

    def update_combo_from_env(self, combo_box: QComboBox, env_key: str, type: None | str = None):
        """Loads options from .env file into a QComboBox."""
        combo_box.clear()
        original_env_path = self.env_file_path # Store original path
        if type == 'common':
            self.env_file_path = '.env' # Temporarily switch to common .env

        # Ensure env_file_path is set before trying to read
        if not self.env_file_path or not os.path.exists(self.env_file_path):
             logging.error(f"Cannot load env key '{env_key}'. Env file path not set or file missing: {self.env_file_path}")
             combo_box.setEnabled(False)
             combo_box.addItem("설정파일 오류") # Indicate error in combo
             if type == 'common': self.env_file_path = original_env_path # Restore path
             return

        try:
            options_str = dotenv.get_key(self.env_file_path, env_key)
            if options_str:
                options = [opt.strip() for opt in options_str.split(',') if opt.strip()]
                if options:
                    combo_box.addItems(options)
                    if combo_box.count() > 0:
                        combo_box.setCurrentIndex(0)
                    combo_box.setEnabled(True)
                else:
                    logging.warning(f"환경 변수 '{env_key}'에 유효한 값이 없습니다 in '{self.env_file_path}'.")
                    combo_box.addItem("옵션 없음")
                    combo_box.setEnabled(False)
            else:
                logging.warning(f"환경 변수 '{env_key}'를 '{self.env_file_path}'에서 찾을 수 없습니다.")
                combo_box.addItem("설정 없음")
                combo_box.setEnabled(False)
        except Exception as e:
            logging.error(f"환경 변수 '{env_key}' 로드 중 오류 발생 from '{self.env_file_path}': {e}")
            QMessageBox.warning(self, "설정 파일 오류", f"'{self.env_file_path}' 파일에서 '{env_key}' 설정을 읽는 중 오류가 발생했습니다.")
            combo_box.addItem("로드 오류")
            combo_box.setEnabled(False)
        finally:
             if type == 'common': self.env_file_path = original_env_path # Restore path

    def create_combo_box(self, label_text: str, options: list, layout: QVBoxLayout) -> QComboBox:
        # (Keep this helper function as is)
        h_layout = QHBoxLayout()
        lbl = QLabel(label_text)
        # Ensure label doesn't stretch unnecessarily, let combo take space
        lbl.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        h_layout.addWidget(lbl)
        combo = QComboBox()
        if options:
            combo.addItems(options)
        # Allow combo to expand horizontally
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h_layout.addWidget(combo)
        layout.addLayout(h_layout)
        # Store label reference with combo for easy access in visibility updates
        combo.setProperty("labelWidget", lbl)
        return combo


    # --- Methods for updating UI elements based on selections ---

    def update_category_combo(self):
        """Updates the Tistory category combo based on the selected domain."""
        if self.selected_platform != "Tistory": return
        selected_domain = self.tistory_domain_combo.currentText().strip()
        self.tistory_category_combo.clear()
        self.tistory_category_combo.setEnabled(False)

        if not selected_domain: return
        if not self.env_file_path: return

        try:
            all_categories_str = dotenv.get_key(self.env_file_path, 'TISTORY_CATEGORY')
            if not all_categories_str:
                logging.warning("TISTORY_CATEGORY 환경 변수가 설정되지 않았습니다.")
                self.tistory_category_combo.addItem("카테고리 설정 없음")
                return

            domain_category_pairs = all_categories_str.split('|')
            found_categories = False
            for item in domain_category_pairs:
                try:
                    domain, categories_str = item.split(":", 1)
                    if domain.strip() == selected_domain:
                        categories = [cat.strip() for cat in categories_str.split(',') if cat.strip()]
                        if categories:
                            self.tistory_category_combo.addItems(categories)
                            if self.tistory_category_combo.count() > 0:
                                self.tistory_category_combo.setCurrentIndex(0)
                                self.tistory_category_combo.setEnabled(True)
                            found_categories = True
                        break
                except ValueError:
                    logging.warning(f"TISTORY_CATEGORY 형식 오류 무시: '{item}'")
                    continue

            if not found_categories:
                logging.warning(f"선택된 도메인 '{selected_domain}'에 대한 카테고리 설정을 찾을 수 없습니다.")
                self.tistory_category_combo.addItem("해당 도메인 카테고리 없음")

        except Exception as e:
            logging.error(f"Tistory 카테고리 로드 중 오류 발생: {e}")
            QMessageBox.warning(self, "카테고리 로드 오류", f"'TISTORY_CATEGORY' 설정값을 읽는 중 오류가 발생했습니다.")
            self.tistory_category_combo.addItem("로드 오류")


    def update_visibility_based_on_mode(self):
        """Updates widget visibility based on the selected mode and platform."""
        selected_mode = self.mode_combo.currentText()

        def set_combo_visibility(combo, visible):
            if combo: # Check if widget exists
                combo.setVisible(visible)
                # Retrieve the associated label using the stored property
                label = combo.property("labelWidget")
                if label:
                    label.setVisible(visible)
                else: # Fallback if property wasn't set (shouldn't happen with create_combo_box)
                    parent_layout = combo.parentWidget()
                    if parent_layout and isinstance(parent_layout, QHBoxLayout):
                         # Try to find QLabel in the same layout (less reliable)
                         labels = parent_layout.findChildren(QLabel)
                         if labels:
                             labels[0].setVisible(visible)

        is_coupang_mode = (selected_mode == "쿠파스 작성")
        is_blog_mode = (selected_mode == "블로그 작성")
        is_keyword_mode = (selected_mode == "키워드 분석")
        is_writing_mode = is_coupang_mode or is_blog_mode

        # --- Tistory Visibility ---
        if self.selected_platform == "Tistory":
            self.tistory_group_box.setTitle("Tistory 설정" if not is_keyword_mode else "Tistory 설정 (키워드 분석 모드)")
            set_combo_visibility(self.tistory_id_combo, is_writing_mode)
            set_combo_visibility(self.tistory_domain_combo, is_writing_mode)
            set_combo_visibility(self.tistory_category_combo, is_writing_mode)
            set_combo_visibility(self.tistory_use_naver_combo, is_coupang_mode)
            set_combo_visibility(self.tistory_channel_combo, is_coupang_mode)

        # --- Blogger Visibility ---
        elif self.selected_platform == "Google Blogger":
            self.blogger_group_box.setTitle("Google Blogger 설정" if not is_keyword_mode else "Blogger 설정 (키워드 분석 모드)")
            set_combo_visibility(self.blogger_blog_id_combo, is_writing_mode)
            set_combo_visibility(self.blogger_use_naver_combo, is_coupang_mode)
            set_combo_visibility(self.blogger_channel_combo, is_coupang_mode)
            # *** Added: Show/hide scheduling combo for Blogger writing modes ***
            set_combo_visibility(self.blogger_schedule_combo, is_writing_mode)


    def update_password(self):
        """Updates the selected password based on the selected Tistory ID."""
        if self.selected_platform != "Tistory": return
        selected_id = self.tistory_id_combo.currentText().strip()
        self.selected_password = None

        if not selected_id: return
        if not self.env_file_path: return

        try:
            user_ids_str = dotenv.get_key(self.env_file_path, 'KAKAO_USERNAME')
            passwords_str = dotenv.get_key(self.env_file_path, 'KAKAO_PASSWORD')

            if not user_ids_str or not passwords_str:
                logging.warning("KAKAO_USERNAME 또는 KAKAO_PASSWORD 환경 변수가 .env 파일에 설정되지 않았습니다.")
                return

            user_ids = [id.strip() for id in user_ids_str.split(',') if id.strip()]
            passwords = [pwd.strip() for pwd in passwords_str.split(',') if pwd.strip()]

            if len(user_ids) != len(passwords):
                QMessageBox.warning(self, "설정 오류", "카카오 계정 개수와 비밀번호 개수가 .env 파일에서 일치하지 않습니다.")
                return

            try:
                idx = user_ids.index(selected_id)
                self.selected_password = passwords[idx]
                logging.info(f"'{selected_id}' 계정 비밀번호 로드 완료.")
            except ValueError:
                logging.warning(f"선택된 카카오 계정 '{selected_id}'에 해당하는 비밀번호를 .env 파일에서 찾을 수 없습니다.")
            except IndexError:
                logging.error(f"비밀번호 인덱스 오류 발생 (계정: {selected_id}). 계정/비번 개수 불일치 확인 필요.")

        except Exception as e:
            logging.error(f"Tistory 비밀번호 로드 중 오류 발생: {e}")
            QMessageBox.warning(self, "비밀번호 로드 오류", "카카오 계정 또는 비밀번호를 .env 파일에서 읽는 중 오류가 발생했습니다.")


    def prompt_naver_category(self) -> bool:
        # (Keep this function as is)
        categories = [category['name'] for category in self.naver_categories]
        category_name, ok = QInputDialog.getItem(self, "네이버 카테고리 선택",
                                                 "네이버 쇼핑 인기 검색어 카테고리를 선택하세요:",
                                                 categories, 0, False)
        if ok and category_name:
            self.selected_naver_category = category_name
            logging.info(f"네이버 카테고리 선택됨: {category_name}")
            return True
        else:
            # Don't show warning here, let the caller decide based on return value
            logging.info("네이버 카테고리 선택 취소됨.")
            self.selected_naver_category = None
            return False

    # --- Added: Prompt for Schedule Interval ---
    def prompt_schedule_interval(self) -> bool:
        """Shows a dialog to select the scheduling interval. Returns True if selected, False otherwise."""
        dialog = ScheduleIntervalDialog(self)
        result = dialog.exec_() # Show the dialog and wait

        if result == QDialog.Accepted:
            self.selected_schedule_interval = dialog.get_selected_interval()
            if self.selected_schedule_interval:
                 logging.info(f"예약 간격 선택됨: {self.selected_schedule_interval}")
                 return True
            else:
                 # Should not happen if dialog works correctly, but handle defensively
                 QMessageBox.warning(self, "오류", "예약 간격을 선택하지 못했습니다.")
                 self.selected_schedule_interval = None
                 return False
        else:
            # User cancelled the dialog
            logging.info("예약 간격 선택 취소됨.")
            QMessageBox.warning(self, "간격 미선택", "예약 포스팅을 사용하려면 간격을 선택해야 합니다.")
            self.selected_schedule_interval = None
            return False


    # --- show_completion_dialog, show_error_dialog (Keep as is) ---
    def show_completion_dialog(self, message: str):
        QMessageBox.information(self, "작업 완료", message)
        # Ensure buttons exist before enabling
        if hasattr(self, 'start_button') and self.start_button: self.start_button.setEnabled(True)
        if hasattr(self, 'back_button') and self.back_button: self.back_button.setEnabled(True)
        self.worker = None # Reset worker reference

    def show_error_dialog(self, error_message: str):
        QMessageBox.critical(self, "오류 발생", error_message)
        # Ensure buttons exist before enabling
        if hasattr(self, 'start_button') and self.start_button: self.start_button.setEnabled(True)
        if hasattr(self, 'back_button') and self.back_button: self.back_button.setEnabled(True)
        self.worker = None # Reset worker reference


    # --- start_clicked (Major updates here) ---
    def start_clicked(self):
        # Prevent double-clicks
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "작업 진행 중", "이미 작업이 실행 중입니다.")
            return
        if not self.start_button.isEnabled(): # Already disabled
             return

        # --- 1. Collect settings ---
        self.selected_mode = self.mode_combo.currentText()
        self.keywords = None
        self.selected_naver_category = None
        self.selected_schedule_interval = None # Reset schedule interval
        self.use_scheduling = False # Reset scheduling flag
        is_valid = True
        msg = "" # Error message

        # Determine if keyword input is needed
        needs_keyword_input = False
        if self.selected_mode == "키워드 분석":
            needs_keyword_input = True
        elif self.selected_mode == "블로그 작성":
             needs_keyword_input = True
        elif self.selected_mode == "쿠파스 작성":
             current_use_naver_combo = None
             if self.selected_platform == "Tistory":
                 current_use_naver_combo = self.tistory_use_naver_combo
             elif self.selected_platform == "Google Blogger":
                 current_use_naver_combo = self.blogger_use_naver_combo

             if current_use_naver_combo and current_use_naver_combo.currentText() == "아니요":
                 if self.selected_platform == "Tistory":
                      use_my_links = dotenv.get_key(self.env_file_path, 'USE_MY_COUPANG_LINKS') == 'True'
                      if not use_my_links:
                          needs_keyword_input = True
                 else:
                      needs_keyword_input = True

        # Prompt for keywords if needed
        if needs_keyword_input:
            prompt_title = "키워드 입력"
            prompt_label = "키워드를 콤마(,)로 구분하여 입력해주세요:" if self.selected_mode == "쿠파스 작성" else "키워드를 입력해주세요:"
            keywords_input, ok = QInputDialog.getText(self, prompt_title, prompt_label)

            if not ok or not keywords_input.strip():
                if self.selected_mode == "키워드 분석":
                     QMessageBox.warning(self, "키워드 필요", "키워드 분석을 위해서는 키워드를 입력해야 합니다.")
                     return
                QMessageBox.warning(self, "키워드 필요", "작업에 필요한 키워드를 입력해야 합니다.")
                return
            self.keywords = keywords_input.strip()
            logging.info(f"입력된 키워드: {self.keywords}")


        # --- Validate and collect platform-specific settings ---
        is_writing_mode = self.selected_mode in ["쿠파스 작성", "블로그 작성"]

        if self.selected_platform == "Tistory":
            self.update_password() # Ensure password is up to date
            self.use_naver = self.tistory_use_naver_combo.currentText() == "예"
            self.selected_id = self.tistory_id_combo.currentText().strip()
            self.selected_ch_id = self.tistory_channel_combo.currentText().strip()
            self.selected_tistory_domain = self.tistory_domain_combo.currentText().strip()
            self.selected_category = self.tistory_category_combo.currentText().strip()
            self.use_coupang_link_config = dotenv.get_key(self.env_file_path, 'USE_MY_COUPANG_LINKS') == 'True'

            if is_writing_mode:
                if not self.selected_id: is_valid = False; msg = "카카오 계정을 선택해주세요."
                elif not self.selected_password: is_valid = False; msg = f"선택된 계정({self.selected_id})의 비밀번호를 찾을 수 없습니다 (.env 확인 필요)."
                elif not self.selected_tistory_domain: is_valid = False; msg = "티스토리 도메인을 선택해주세요."
                elif not self.selected_category or "오류" in self.selected_category:
                    is_valid = False; msg = "유효한 티스토리 카테고리를 선택해주세요."
                elif self.selected_mode == "쿠파스 작성":
                    if self.use_naver:
                        # Prompt later if needed, just check selection here
                        pass
                    if not self.selected_ch_id or "없음" in self.selected_ch_id or "오류" in self.selected_ch_id:
                        is_valid = False; msg = "유효한 쿠팡 채널 ID를 선택해주세요."

            if is_valid and self.selected_mode == "쿠파스 작성":
                current_id = self.selected_id
                if self.pre_selected_id is None or self.pre_selected_id == current_id: self.account_changed = False
                else: self.account_changed = True
                self.pre_selected_id = current_id

        elif self.selected_platform == "Google Blogger":
            self.use_naver = self.blogger_use_naver_combo.currentText() == "예"
            self.selected_ch_id = self.blogger_channel_combo.currentText().strip()
            self.selected_blogger_blog_id = self.blogger_blog_id_combo.currentText().strip()
            self.use_scheduling = self.blogger_schedule_combo.currentText() == "사용" # Get schedule setting

            if is_writing_mode:
                if not self.selected_blogger_blog_id or "없음" in self.selected_blogger_blog_id or "오류" in self.selected_blogger_blog_id:
                    is_valid = False; msg = "작업할 유효한 Blogger 블로그 ID를 선택해주세요."
                elif self.selected_mode == "쿠파스 작성":
                    # Naver prompt later if needed
                    if not self.selected_ch_id or "없음" in self.selected_ch_id or "오류" in self.selected_ch_id:
                        is_valid = False; msg = "유효한 쿠팡 채널 ID를 선택해주세요."
                # No validation needed for scheduling combo itself here, handled later


        # --- Prompt for Naver Category if needed (AFTER basic validation) ---
        if is_valid and self.selected_mode == "쿠파스 작성" and self.use_naver:
             if not self.prompt_naver_category():
                  # User cancelled Naver category selection
                  is_valid = False # Mark as invalid to prevent proceeding
                  msg = "네이버 카테고리 선택이 필요합니다." # Optional message


        # --- Final Check and Show Error if Invalid ---
        if not is_valid:
            if msg:
                QMessageBox.warning(self, "설정 오류", msg)
            # No return here in case we need the finally block, buttons are handled there
            return # Stop execution


        # --- 2. Summary and Confirmation ---
        summary = f"--- 작업 설정 요약 ---\n\n"
        summary += f"플랫폼: {self.selected_platform}\n"
        summary += f"작업 모드: {self.selected_mode}\n"
        if self.keywords: summary += f"키워드: {self.keywords}\n"

        if self.selected_platform == "Tistory":
            if is_writing_mode:
                summary += f"카카오 계정: {self.selected_id}\n"
                summary += f"티스토리 도메인: {self.selected_tistory_domain}\n"
                summary += f"티스토리 카테고리: {self.selected_category}\n"
                if self.selected_mode == "쿠파스 작성":
                    summary += f"  네이버 인기 검색어 사용: {'예' if self.use_naver else '아니요'}\n"
                    if self.use_naver and self.selected_naver_category:
                        summary += f"    └ 네이버 카테고리: {self.selected_naver_category}\n"
                    summary += f"  내 쿠팡링크 설정 사용: {'예' if self.use_coupang_link_config else '아니요'}\n"
                    summary += f"  쿠팡 채널 ID: {self.selected_ch_id}\n"

        elif self.selected_platform == "Google Blogger":
            if is_writing_mode:
                summary += f"Blogger 블로그 ID: {self.selected_blogger_blog_id}\n"
                if self.selected_mode == "쿠파스 작성":
                    summary += f"  네이버 인기 검색어 사용: {'예' if self.use_naver else '아니요'}\n"
                    if self.use_naver and self.selected_naver_category:
                        summary += f"    └ 네이버 카테고리: {self.selected_naver_category}\n"
                    # Channel ID shown regardless of Naver use in Coupas mode
                    summary += f"  쿠팡 채널 ID: {self.selected_ch_id}\n"
                # Add scheduling info (without interval yet)
                summary += f"  예약 포스팅 사용: {'예' if self.use_scheduling else '사용 안함'}\n"


        confirm = QMessageBox.information(self, "실행 전 확인", summary + "\n\n위 설정으로 작업을 시작하시겠습니까?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if confirm == QMessageBox.No:
            logging.info("사용자가 작업을 취소했습니다.")
            return

        # --- 2.5 Prompt for Schedule Interval if needed ---
        if self.selected_platform == "Google Blogger" and is_writing_mode and self.use_scheduling:
             if not self.prompt_schedule_interval():
                 # User cancelled interval selection or it failed
                 # Buttons are left enabled as the task didn't start
                 return # Stop execution


        # --- 3. Execute Task ---
        self.start_button.setEnabled(False)
        self.back_button.setEnabled(False)
        logging.info(f"작업 시작: 플랫폼='{self.selected_platform}', 모드='{self.selected_mode}'")
        # Log final settings including interval if set
        final_settings_summary = summary # Start with previous summary
        if self.selected_schedule_interval:
             final_settings_summary += f"    └ 예약 간격: {self.selected_schedule_interval}\n"
        logging.info(f"최종 설정 요약:\n{final_settings_summary}")


        try:
            # --- Keyword Analysis Mode ---
            if self.selected_mode == "키워드 분석":
                key_list = [key.strip() for key in self.keywords.split(',') if key.strip()]
                if not key_list:
                    QMessageBox.warning(self,"키워드 오류","분석할 유효한 키워드가 없습니다.")
                    # Let finally block re-enable buttons
                else:
                    try:
                        result = KeywordGenerator().getKeywords(key_list)
                        logging.info(f"키워드 분석 완료: {result}")
                        QMessageBox.information(self, "키워드 분석 완료", f"분석 결과:\n{result}")
                    except Exception as e:
                        logging.exception("키워드 분석 중 오류 발생")
                        self.show_error_dialog(f"키워드 분석 중 오류가 발생했습니다: {e}")
                return # Exit after keyword analysis (finally block will run)

            # --- Writing Modes (Tistory/Blogger) ---
            client = None
            writing_mode = '1' if self.selected_mode == "쿠파스 작성" else '2'

            if self.selected_platform == "Tistory":
                client = Tistory(self) # Pass MenuGUI instance
            elif self.selected_platform == "Google Blogger":
                try:
                    client = BloggerClient(self) # Pass MenuGUI instance
                    # Client can now access self.menu_gui.selected_schedule_interval if needed
                except (FileNotFoundError, ConnectionError, RuntimeError, ImportError, Exception) as client_err:
                    logging.exception("Blogger 클라이언트 초기화 중 오류 발생")
                    self.show_error_dialog(f"Blogger 클라이언트 초기화 오류: {client_err}")
                    client = None

            # Start worker thread if client initialized successfully
            if client and writing_mode:
                self.worker = WorkerThread(self, client, writing_mode)
                self.worker.finished.connect(self.show_completion_dialog)
                self.worker.error.connect(self.show_error_dialog)
                # Connect signals to re-enable back button too (handled in dialog methods now)
                # self.worker.finished.connect(lambda: self.back_button.setEnabled(True)) # Done in show_completion_dialog
                # self.worker.error.connect(lambda: self.back_button.setEnabled(True)) # Done in show_error_dialog
                self.worker.start()
                logging.info(f"작업 스레드 시작 (Platform: {self.selected_platform}, Mode: {self.selected_mode})")
            elif not client:
                # Error dialog was already shown if client init failed or platform unknown
                logging.error(f"{self.selected_platform} 클라이언트가 없어 스레드를 시작할 수 없습니다.")
                # Let finally block re-enable buttons

        except Exception as e:
            logging.exception("start_clicked에서 예상치 못한 오류 발생 (스레드 시작 전 또는 키워드 분석)")
            self.show_error_dialog(f"작업 시작 처리 중 오류 발생: {str(e)}")
            # Let finally block re-enable buttons
        finally:
            # Re-enable buttons ONLY if the worker thread isn't running
            # (Worker signals handle re-enabling on completion/error)
            if not self.worker or not self.worker.isRunning():
                 # Check if buttons exist before trying to enable them
                 if hasattr(self, 'start_button') and self.start_button:
                     self.start_button.setEnabled(True)
                 if hasattr(self, 'back_button') and self.back_button:
                     self.back_button.setEnabled(True)
