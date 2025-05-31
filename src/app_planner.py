# src/app_planner.py
import sys
import os
import json 
from datetime import datetime
import configparser 
import shutil 

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTextBrowser, QMessageBox,
                             QComboBox, QFileDialog, QDialog, QDialogButtonBox, QTextEdit)
from PyQt5.QtCore import Qt, QCoreApplication, QObject, QThread, pyqtSignal
from PyQt5.QtPrintSupport import QPrinter

# --- utils.py에서 resource_path 함수 가져오기 ---
try:
    from utils import resource_path
except ImportError as e:
    print(f"경고: utils.py의 resource_path 함수 임포트 실패. 개발 환경 경로를 사용합니다. ({e})")
    def resource_path(relative_path_from_project_root):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relative_path_from_project_root))

# --- 다른 우리 모듈에서 함수 가져오기 ---
try:
    from guide import generate_guide_with_chatgpt, generate_guide_with_gemini, load_api_key
    from item_name_mapper import get_poedb_identifier
    from crawler import get_item_details_from_poedb, get_current_league_info_from_poedb 
except ImportError as e:
    print(f"필수 모듈 임포트 실패! 프로그램 실행 불가: {e}")
    # QApplication 생성 전이므로 QMessageBox 사용 불가, 터미널에만 출력 후 종료
    sys.exit(f"ImportError: {e}. Check console. src/ 폴더에 필요한 .py 파일이 있는지 확인하세요.")


# ---------------------------------------------------------------------
# 설정 파일 및 API 키 파일 경로 (resource_path 사용)
# ---------------------------------------------------------------------
CONFIG_FILE_PATH = resource_path('config.ini')
API_KEYS_FILE_PATH = resource_path('api_keys.txt') 

# ---------------------------------------------------------------------
# 설정 다이얼로그 클래스 정의
# ---------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, parent=None, initial_chatgpt_model="", initial_gemini_model=""):
        super().__init__(parent)
        self.setWindowTitle("LLM 모델 설정")
        self.setMinimumWidth(450)
        self.config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE_PATH):
            self.config.read(CONFIG_FILE_PATH, encoding='utf-8')
        else: 
            if 'LLM_MODELS' not in self.config: self.config.add_section('LLM_MODELS')
        
        layout = QVBoxLayout(self)
        chatgpt_hbox = QHBoxLayout(); lbl_chatgpt = QLabel("ChatGPT 모델 ID:"); self.edit_chatgpt_model = QLineEdit()
        self.edit_chatgpt_model.setPlaceholderText("예: gpt-4o-mini")
        self.edit_chatgpt_model.setText(self.config.get('LLM_MODELS', 'CHATGPT_MODEL', fallback=initial_chatgpt_model if initial_chatgpt_model else "gpt-4o-mini"))
        chatgpt_hbox.addWidget(lbl_chatgpt); chatgpt_hbox.addWidget(self.edit_chatgpt_model); layout.addLayout(chatgpt_hbox)
        gemini_hbox = QHBoxLayout(); lbl_gemini = QLabel("Gemini 모델 ID:"); self.edit_gemini_model = QLineEdit()
        self.edit_gemini_model.setPlaceholderText("예: models/gemini-1.5-flash-latest")
        self.edit_gemini_model.setText(self.config.get('LLM_MODELS', 'GEMINI_MODEL', fallback=initial_gemini_model if initial_gemini_model else "models/gemini-1.5-flash-latest"))
        gemini_hbox.addWidget(lbl_gemini); gemini_hbox.addWidget(self.edit_gemini_model); layout.addLayout(gemini_hbox)
        info_label = QLabel("<small>참고: 모델 ID 변경 내용은 '저장' 시 <b>config.ini</b> 파일에 반영됩니다.<br>"
                          "실제 LLM 호출에 사용되는 모델은 다음 가이드 생성부터 적용됩니다.<br>"
                          "UI의 LLM 선택 메뉴 표시는 이 창을 닫은 후 즉시 또는 프로그램 재시작 시 업데이트됩니다.</small>")
        info_label.setAlignment(Qt.AlignCenter); layout.addWidget(info_label)
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_settings); button_box.rejected.connect(self.reject); layout.addWidget(button_box)

    def accept_settings(self):
        if 'LLM_MODELS' not in self.config: self.config.add_section('LLM_MODELS')
        chatgpt_model_input = self.edit_chatgpt_model.text().strip(); 
        if not chatgpt_model_input: chatgpt_model_input = "gpt-4o-mini" 
        gemini_model_input = self.edit_gemini_model.text().strip()
        if not gemini_model_input: gemini_model_input = "models/gemini-1.5-flash-latest"
        self.config['LLM_MODELS']['CHATGPT_MODEL'] = chatgpt_model_input
        self.config['LLM_MODELS']['GEMINI_MODEL'] = gemini_model_input
        try:
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as configfile: self.config.write(configfile)
            if self.parent() and hasattr(self.parent(), 'settings_updated_actions'): self.parent().settings_updated_actions()
            QMessageBox.information(self, "저장 완료", f"설정이 {CONFIG_FILE_PATH}에 저장되었습니다.")
            super().accept() 
        except Exception as e: QMessageBox.critical(self, "저장 오류", f"설정 저장 중 오류 발생:\n{e}")

# ---------------------------------------------------------------------
# 일꾼 클래스(GuideWorker) 정의 (사용자 노트 내용 프롬프트에 반영)
# ---------------------------------------------------------------------
class GuideWorker(QObject):
    finished = pyqtSignal(str, object) 
    progress = pyqtSignal(int, str)

    def __init__(self, item_query_text, selected_llm_type, 
                 selected_char_class, selected_ascendancy,
                 league_mode, league_season, 
                 chatgpt_model_id_to_use, gemini_model_id_to_use,
                 user_notes_text): # 사용자 노트 인자 추가!
        super().__init__()
        self.item_query = item_query_text; self.selected_llm = selected_llm_type
        self.character_class = selected_char_class; self.ascendancy_class = selected_ascendancy
        self.league_mode = league_mode; self.league_season = league_season
        self.chatgpt_model_id = chatgpt_model_id_to_use; self.gemini_model_id = gemini_model_id_to_use
        self.user_notes = user_notes_text # 사용자 노트 저장
        self.is_cancelled = False 

    def run(self):
        try:
            class_display_for_progress = self.character_class
            if self.ascendancy_class and self.ascendancy_class != "전직 선택 안함": class_display_for_progress += f" ({self.ascendancy_class})"
            elif self.character_class == "클래스 선택 안함": class_display_for_progress = "클래스 미지정"
            league_info_for_progress = f"{self.league_season} {self.league_mode}"
            self.progress.emit(5, f"'{self.item_query if self.item_query else '(아이템 없음)'}' (대상: {class_display_for_progress}, 리그: {league_info_for_progress}) 처리 요청 접수...")
            
            item_data_worker = None; llm_name_for_display_worker = self.selected_llm 
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return

            if self.item_query: 
                if self.item_query.startswith("http") and "poedb.tw" in self.item_query:
                    self.progress.emit(15, f"URL에서 '{self.item_query}' 정보 가져오는 중...")
                    item_data_worker = get_item_details_from_poedb(self.item_query)
                else:
                    self.progress.emit(10, f"'{self.item_query}' 아이템 이름으로 URL 식별자 찾는 중...")
                    poedb_id = get_poedb_identifier(self.item_query)
                    if poedb_id:
                        self.progress.emit(20, f"'{poedb_id}' 정보 poedb.tw에서 가져오는 중...")
                        item_data_worker = get_item_details_from_poedb(poedb_id)
                    else:
                        self.progress.emit(20, f"'{self.item_query}'에 대한 URL 식별자 찾기 실패.")
                        item_data_worker = {'name': self.item_query, 'type': '(정보 부족)', 'mods': ['(상세 옵션 정보 없음)'], 'url': None, 'notice': 'mapper_failed'}
            else: 
                item_data_worker = {'name': '(아이템 지정 안함)', 'type': '', 'mods': [], 'url': None, 'notice': 'no_item_specified'}
            
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return
            self.progress.emit(50, "정보 분석 완료, LLM 프롬프트 구성 중...")

            if not item_data_worker or (self.item_query and not item_data_worker.get('name')):
                self.finished.emit("error_crawl", f"'{self.item_query}'에 대한 아이템 정보를 가져오지 못했습니다.")
                return

            item_name_prompt = item_data_worker.get('name', '(아이템 지정 안함)')
            item_type_prompt = item_data_worker.get('type', '')
            mods_list_prompt = item_data_worker.get('mods', [])
            mods_string_prompt = "\n- ".join(mods_list_prompt) if mods_list_prompt and '(상세 옵션 정보 없음)' not in mods_list_prompt[0] else ("(상세 옵션 정보 없음)" if self.item_query else "(아이템 지정 안함)")
            
            class_context_prompt = f"'{self.character_class}' 클래스" if self.character_class and self.character_class != "클래스 선택 안함" else "특정 클래스/빌드를 염두에 두지 않고 있습니다."
            if self.character_class and self.character_class != "클래스 선택 안함" and self.ascendancy_class and self.ascendancy_class != "전직 선택 안함": 
                class_context_prompt = f"'{self.character_class}' 클래스의 '{self.ascendancy_class}' 전직 빌드" # 좀 더 명확하게
            
            league_context_prompt = f"현재 '{self.league_season}' 리그의 '{self.league_mode}' 환경에서 플레이하고 있습니다."

            # --- 사용자 노트 프롬프트에 추가! ---
            user_notes_section_for_prompt = ""
            if self.user_notes and self.user_notes.strip(): # 노트 내용이 있을 때만
                user_notes_section_for_prompt = f"""
                또한, 이 사용자는 다음과 같은 추가적인 노트나 구체적인 요청사항을 남겼습니다. 이 내용도 반드시 함께 고려하여 답변해주세요:
                --- 사용자 노트 시작 ---
                {self.user_notes}
                --- 사용자 노트 끝 ---
                """
            # --- ---

            prompt_for_llm_worker = ""; query_subject_worker = ""
            base_questions = """
            1. 이 아이템(또는 현재 제 상황)이 저 같은 초보자에게 그리고 제 클래스/전직 및 현재 리그 환경에 유용한가요?
            2. 만약 유용하다면, (아이템이 있다면 아이템을 포함하여) 제 클래스/전직 빌드 및 리그 환경에 어떻게 활용할 수 있을까요? 어떤 장점이 있나요?
            3. 현재 상황에서 특별히 주의해야 할 점이나 (특히 하드코어라면 생존 관련) 알아두면 좋은 팁이 있다면 알려주세요.
            4. 현재 제 상황(아이템, 클래스/전직, 리그)과 잘 어울리는, Path of Exile에 실제로 존재하는 다른 아이템(고유 아이템 이름이나 일반적인 아이템 유형)이나 주요 스킬 젬 이름을 2~3가지 추천해주고, 왜 그것들이 도움이 되는지 간략히 설명해주세요. 만약 구체적인 이름 추천이 어렵다면, 어떤 '종류'의 아이템이나 스킬이 도움이 될지 설명해주면 좋겠습니다.
            """
            if self.item_query: 
                query_subject_worker = f"아이템: '{item_name_prompt}' ({item_type_prompt}), 옵션: {mods_string_prompt}\n"
                prompt_for_llm_worker = f"당신은 Path of Exile 게임의 숙련된 전문가입니다. 초보 유저가 질문합니다.\n{query_subject_worker}저는 초보자이고, {league_context_prompt}에서 {class_context_prompt}를 키우려고 합니다.\n{user_notes_section_for_prompt}\n위 모든 정보(아이템, 사용자 상황, 사용자 노트)를 종합적으로 고려하여 다음 질문에 답변해주세요:\n{base_questions}\nMarkdown으로 친절하고 자세하게 답변해주세요."
            else: 
                query_subject_worker = "(특정 아이템 없이 일반 빌드 조언 요청)\n"
                prompt_for_llm_worker = f"당신은 Path of Exile 게임의 숙련된 전문가입니다. 초보 유저가 질문합니다.\n{query_subject_worker}저는 초보자이고, {league_context_prompt}에서 {class_context_prompt}를 키우려고 합니다. \n{user_notes_section_for_prompt}\n위 모든 정보(사용자 상황, 사용자 노트)를 종합적으로 고려하여 다음 질문에 답변해주세요. (특정 아이템에 대한 질문이 아닙니다.):\n{base_questions.replace('이 아이템', '제 상황')}\nMarkdown으로 친절하고 자세하게 답변해주세요." # "이 아이템" 부분을 "제 상황"으로 변경
            
            progress_message_llm = f"'{item_name_prompt if self.item_query else '(아이템 없음)'}' ({class_display_for_progress}, {league_info_for_progress}) 정보로 {llm_name_for_display_worker}에게 가이드 요청 중..."
            if item_data_worker.get('notice') == 'mapper_failed': progress_message_llm = f"'{item_data_worker.get('name', self.item_query)}' (상세정보 부족...) {llm_name_for_display_worker}에게 가이드 요청 중..."
            self.progress.emit(60, progress_message_llm)
            
            guide_text_worker = ""; 
            if self.selected_llm == "ChatGPT": guide_text_worker = generate_guide_with_chatgpt(item_data_worker, prompt_override=prompt_for_llm_worker, model_id_to_use=self.chatgpt_model_id)
            elif self.selected_llm == "Gemini": guide_text_worker = generate_guide_with_gemini(item_data_worker, prompt_override=prompt_for_llm_worker, model_id_to_use=self.gemini_model_id)
            else: self.finished.emit("error_llm_selection", f"내부 오류: 알 수 없는 LLM ({self.selected_llm})"); return
            
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return
            self.progress.emit(95, f"{llm_name_for_display_worker} 응답 수신 완료, 결과 표시 준비 중...")
            
            self.finished.emit("success", {'guide': guide_text_worker, 'item_info': item_data_worker, 
                                           'used_llm': llm_name_for_display_worker, 
                                           'char_class': self.character_class, 'ascendancy': self.ascendancy_class, 
                                           'league_mode': self.league_mode, 'league_season': self.league_season,
                                           'user_notes': self.user_notes }) # 사용자 노트도 결과에 포함
        except Exception as e:
            self.progress.emit(0, "오류 발생!"); self.finished.emit("error_unknown", f"가이드 생성 중 예기치 않은 오류 발생: {e}")


# ---------------------------------------------------------------------
# 메인 애플리케이션 클래스(PoEPlannerApp) 정의
# ---------------------------------------------------------------------
class PoEPlannerApp(QWidget):
    BASE_CLASSES = ["클래스 선택 안함", "머라우더", "듀얼리스트", "레인저", "섀도우", "위치", "템플러", "사이온"]
    ASCENDANCIES = { "머라우더": ["전직 선택 안함", "저거넛", "버서커", "치프틴"], "듀얼리스트": ["전직 선택 안함", "슬레이어", "글래디에이터", "챔피언"], "레인저": ["전직 선택 안함", "데드아이", "레이더", "패스파인더"], "섀도우": ["전직 선택 안함", "어쌔신", "사보추어", "트릭스터"], "위치": ["전직 선택 안함", "네크로맨서", "엘리멘탈리스트", "오컬티스트"], "템플러": ["전직 선택 안함", "인퀴지터", "하이로펀트", "가디언"], "사이온": ["전직 선택 안함", "어센던트"], "클래스 선택 안함": ["전직 정보 없음"] }
    LEAGUE_MODES = ["소프트코어", "하드코어"]

    def __init__(self):
        super().__init__()
        self.thread = None; self.worker = None 
        self.current_item_query = ""; self.current_item_data = {}; self.current_char_class = ""
        self.current_ascendancy = ""; self.current_league_mode = ""; self.current_league_season = ""
        self.current_selected_llm = ""; self.current_guide_text = ""; self.current_user_notes = ""
        self._ensure_config_files_exist() 
        self.chatgpt_model_id = ""; self.gemini_model_id = "" 
        self._load_app_config()
        self.fetched_current_league_name = "시즌"; 
        try:
            league_info = get_current_league_info_from_poedb()
            if league_info and league_info.get("name"):
                self.fetched_current_league_name = league_info["name"]
                if league_info.get("version"): self.fetched_current_league_name += f" ({league_info['version']})"
        except: pass 
        self.initUI(); self.check_api_keys()

    def _ensure_config_files_exist(self): # 이전과 동일
        example_config_path = resource_path('config.example.ini')
        if not os.path.exists(CONFIG_FILE_PATH) and os.path.exists(example_config_path):
            try: shutil.copy2(example_config_path, CONFIG_FILE_PATH); print(f"알림: '{CONFIG_FILE_PATH}' 생성됨...")
            except Exception as e: print(f"경고: '{CONFIG_FILE_PATH}' 자동 생성 실패: {e}")
        elif not os.path.exists(CONFIG_FILE_PATH) and not os.path.exists(example_config_path): print(f"경고: 설정 파일 및 예시 파일 모두 없음...")
        example_api_keys_path = resource_path('api_keys.example.txt')
        if not os.path.exists(API_KEYS_FILE_PATH) and os.path.exists(example_api_keys_path):
            try: shutil.copy2(example_api_keys_path, API_KEYS_FILE_PATH); print(f"알림: '{API_KEYS_FILE_PATH}' 생성됨...")
            except Exception as e: print(f"경고: '{API_KEYS_FILE_PATH}' 자동 생성 실패: {e}")
        elif not os.path.exists(API_KEYS_FILE_PATH) and not os.path.exists(example_api_keys_path): print(f"경고: API 키 파일 및 예시 파일 모두 없음...")
        
    def _load_app_config(self): # 이전과 동일
        config = configparser.ConfigParser(); default_chatgpt_model = "gpt-4o-mini"; default_gemini_model = "models/gemini-1.5-flash-latest"
        self.chatgpt_model_id = default_chatgpt_model; self.gemini_model_id = default_gemini_model
        if os.path.exists(CONFIG_FILE_PATH):
            config.read(CONFIG_FILE_PATH, encoding='utf-8')
            if 'LLM_MODELS' in config:
                self.chatgpt_model_id = config['LLM_MODELS'].get('CHATGPT_MODEL', default_chatgpt_model).strip()
                self.gemini_model_id = config['LLM_MODELS'].get('GEMINI_MODEL', default_gemini_model).strip()
                if not self.chatgpt_model_id: self.chatgpt_model_id = default_chatgpt_model
                if not self.gemini_model_id: self.gemini_model_id = default_gemini_model
        print(f"앱 설정 로드: ChatGPT 모델='{self.chatgpt_model_id}', Gemini 모델='{self.gemini_model_id}'")
        if hasattr(self, 'combo_llm_select'): self.combo_llm_select.setItemText(0, f"ChatGPT ({self.chatgpt_model_id})"); self.combo_llm_select.setItemText(1, f"Gemini ({self.gemini_model_id})")
    
    def settings_updated_actions(self): # 이전과 동일
        self._load_app_config(); print("LLM 모델 설정이 앱에 다시 로드되었습니다.")

    def open_settings_dialog(self): # 이전과 동일
        dialog = SettingsDialog(self, initial_chatgpt_model=self.chatgpt_model_id, initial_gemini_model=self.gemini_model_id)
        dialog.exec_() 

    def initUI(self): # 이전 버전(v1.5)과 동일 (사용자 노트 UI는 이미 있었음)
        self.setWindowTitle(f'Pathcrafter AI (LLM 빌드 가이드 플래너 v1.6 - 노트 LLM 연동)') # 이름 변경! 버전 업!
        self.setGeometry(150, 150, 800, 900) 
        main_vbox = QVBoxLayout(); top_controls_layout = QVBoxLayout()
        item_input_hbox = QHBoxLayout(); lbl_item_input = QLabel('아이템 이름/URL (선택):'); lbl_item_input.setFixedWidth(160)
        self.edit_item_input = QLineEdit(); self.edit_item_input.setPlaceholderText("아이템 지정 시 입력, 없으면 일반 가이드")
        self.edit_item_input.returnPressed.connect(self.generate_guide_action)
        item_input_hbox.addWidget(lbl_item_input); item_input_hbox.addWidget(self.edit_item_input); top_controls_layout.addLayout(item_input_hbox)
        class_asc_hbox = QHBoxLayout(); base_class_vbox = QVBoxLayout(); lbl_base_class_select = QLabel('기본 클래스:')
        self.combo_base_class = QComboBox(); self.combo_base_class.addItems(self.BASE_CLASSES); self.combo_base_class.currentTextChanged.connect(self.update_ascendancy_combo); base_class_vbox.addWidget(lbl_base_class_select); base_class_vbox.addWidget(self.combo_base_class); class_asc_hbox.addLayout(base_class_vbox)
        asc_class_vbox = QVBoxLayout(); lbl_asc_class_select = QLabel('전직 클래스:'); self.combo_ascendancy_class = QComboBox(); self.combo_ascendancy_class.setEnabled(False); asc_class_vbox.addWidget(lbl_asc_class_select); asc_class_vbox.addWidget(self.combo_ascendancy_class); class_asc_hbox.addLayout(asc_class_vbox); self.update_ascendancy_combo(self.combo_base_class.currentText()) 
        top_controls_layout.addLayout(class_asc_hbox); main_vbox.addLayout(top_controls_layout)
        mid_controls_hbox = QHBoxLayout(); league_mode_vbox = QVBoxLayout(); lbl_league_mode = QLabel('리그 유형:'); self.combo_league_mode = QComboBox(); self.combo_league_mode.addItems(self.LEAGUE_MODES); self.combo_league_mode.setCurrentText("소프트코어"); league_mode_vbox.addWidget(lbl_league_mode); league_mode_vbox.addWidget(self.combo_league_mode); mid_controls_hbox.addLayout(league_mode_vbox)
        league_season_vbox = QVBoxLayout(); lbl_league_season = QLabel('리그 종류:')
        self.combo_league_season = QComboBox()
        dynamic_league_seasons = [f"{self.fetched_current_league_name} (현재)" if self.fetched_current_league_name != "시즌" else "시즌 (자동로드 실패)", "스탠다드"]
        self.combo_league_season.addItems(dynamic_league_seasons); self.combo_league_season.setCurrentIndex(0)
        league_season_vbox.addWidget(lbl_league_season); league_season_vbox.addWidget(self.combo_league_season); mid_controls_hbox.addLayout(league_season_vbox)
        llm_select_vbox = QVBoxLayout(); lbl_llm_select = QLabel('사용 LLM:'); self.combo_llm_select = QComboBox()
        self.combo_llm_select.addItem(f"ChatGPT ({self.chatgpt_model_id})") 
        self.combo_llm_select.addItem(f"Gemini ({self.gemini_model_id})")   
        llm_select_vbox.addWidget(lbl_llm_select); llm_select_vbox.addWidget(self.combo_llm_select); mid_controls_hbox.addLayout(llm_select_vbox)
        main_vbox.addLayout(mid_controls_hbox)
        bottom_buttons_hbox = QHBoxLayout(); self.btn_settings = QPushButton('LLM 모델 설정'); self.btn_settings.setFixedHeight(40); self.btn_settings.clicked.connect(self.open_settings_dialog); bottom_buttons_hbox.addWidget(self.btn_settings)
        self.btn_load_snapshot = QPushButton('스냅샷 불러오기'); self.btn_load_snapshot.setFixedHeight(40); self.btn_load_snapshot.clicked.connect(self.load_snapshot_action); bottom_buttons_hbox.addWidget(self.btn_load_snapshot)
        self.btn_save_snapshot = QPushButton('현재 내용 스냅샷 저장'); self.btn_save_snapshot.setFixedHeight(40); self.btn_save_snapshot.clicked.connect(self.save_snapshot_action); self.btn_save_snapshot.setEnabled(False); bottom_buttons_hbox.addWidget(self.btn_save_snapshot)
        self.btn_save_pdf = QPushButton('가이드 PDF로 저장'); self.btn_save_pdf.setFixedHeight(40); self.btn_save_pdf.clicked.connect(self.save_guide_as_pdf); self.btn_save_pdf.setEnabled(False); bottom_buttons_hbox.addWidget(self.btn_save_pdf)
        main_vbox.addLayout(bottom_buttons_hbox)
        self.btn_generate_guide = QPushButton('빌드 가이드 생성'); self.btn_generate_guide.setFixedHeight(50); self.btn_generate_guide.clicked.connect(self.generate_guide_action); main_vbox.addWidget(self.btn_generate_guide)
        lbl_guide_output = QLabel('LLM 생성 가이드:'); main_vbox.addWidget(lbl_guide_output)
        self.browser_guide_output = QTextBrowser(); self.browser_guide_output.setPlaceholderText("아이템(선택), 클래스, 리그 등을 선택하고 버튼을 누르세요...")
        self.browser_guide_output.setOpenExternalLinks(True); main_vbox.addWidget(self.browser_guide_output, 1)
        lbl_user_notes = QLabel('나만의 빌드 노트:'); main_vbox.addWidget(lbl_user_notes)
        self.edit_user_notes = QTextEdit(); self.edit_user_notes.setPlaceholderText("LLM 가이드에 대한 보충 설명, 아이디어, 수정 계획 등을 기록하세요...") 
        self.edit_user_notes.setFixedHeight(150); main_vbox.addWidget(self.edit_user_notes, 0)
        self.setLayout(main_vbox); self.show()

    def update_ascendancy_combo(self, selected_base_class_text): # 이전과 동일
        self.combo_ascendancy_class.clear(); base_class_key = selected_base_class_text.split(" (")[0]
        if base_class_key in self.ASCENDANCIES: self.combo_ascendancy_class.addItems(self.ASCENDANCIES[base_class_key]); self.combo_ascendancy_class.setEnabled(base_class_key != "클래스 선택 안함")
        else: self.combo_ascendancy_class.addItem("기본 클래스 오류"); self.combo_ascendancy_class.setEnabled(False)

    def check_api_keys(self): # 이전과 동일
        chatgpt_key = load_api_key('OPENAI'); gemini_key = load_api_key('GEMINI'); missing_keys = []
        if not chatgpt_key: missing_keys.append("OpenAI")
        if not gemini_key: missing_keys.append("Gemini")
        if missing_keys: QMessageBox.warning(self, "API 키 설정 오류", f"{', '.join(missing_keys)} API 키가 설정되지 않았거나 유효하지 않습니다...\n{API_KEYS_FILE_PATH} 파일을 확인해주세요...\n해당 LLM 기능이 제한될 수 있습니다.")
        
    def generate_guide_action(self): # 사용자 노트 내용 GuideWorker에게 전달!
        if self.thread and self.thread.isRunning(): QMessageBox.information(self, "알림", "이미 작업 진행 중"); return
        item_query = self.edit_item_input.text().strip()
        selected_llm_display_text = self.combo_llm_select.currentText(); llm_type_to_use = "ChatGPT" if "ChatGPT" in selected_llm_display_text else "Gemini"
        chatgpt_model_to_use = self.chatgpt_model_id; gemini_model_to_use = self.gemini_model_id
        selected_base_class = self.combo_base_class.currentText(); selected_ascendancy = ""
        if self.combo_ascendancy_class.isEnabled() and self.combo_ascendancy_class.currentText() not in ["전직 선택 안함", "전직 정보 없음"]: selected_ascendancy = self.combo_ascendancy_class.currentText()
        selected_league_mode = self.combo_league_mode.currentText(); selected_league_season_display = self.combo_league_season.currentText()
        actual_league_name_for_worker = self.fetched_current_league_name.split(" (")[0] if "(현재)" in selected_league_season_display else ("시즌" if "자동로드 실패" in selected_league_season_display else selected_league_season_display)
        if selected_base_class == "클래스 선택 안함" and not item_query: QMessageBox.information(self, "선택 필요", "아이템 미입력 시, 최소 '기본 클래스' 선택 필요."); return
        
        user_notes_content = self.edit_user_notes.toPlainText().strip() # 사용자 노트 내용 가져오기!

        self.btn_generate_guide.setEnabled(False); self.btn_save_pdf.setEnabled(False); self.btn_save_snapshot.setEnabled(False)
        
        query_display_name = f"'{item_query}'" if item_query else "(아이템 미지정)"; class_info_for_msg = selected_base_class; 
        if selected_ascendancy: class_info_for_msg += f" ({selected_ascendancy})"
        if selected_base_class == "클래스 선택 안함": class_info_for_msg = "클래스 미지정"
        league_info_for_msg = f"{actual_league_name_for_worker} {selected_league_mode}"
        current_model_id_for_display = chatgpt_model_to_use if llm_type_to_use == "ChatGPT" else gemini_model_to_use
        self.browser_guide_output.setMarkdown(f"{query_display_name} ({class_info_for_msg}, {league_info_for_msg}, {llm_type_to_use}: {current_model_id_for_display} 사용) 가이드 생성 요청 접수... (0%)") 
        QCoreApplication.processEvents()

        self.thread = QThread()
        self.worker = GuideWorker(item_query, llm_type_to_use, 
                                  selected_base_class, selected_ascendancy,
                                  selected_league_mode, actual_league_name_for_worker,
                                  chatgpt_model_to_use, gemini_model_to_use,
                                  user_notes_content) # 사용자 노트 내용 전달!
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.update_guide_progress); self.worker.finished.connect(self.handle_guide_finished)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()

    def update_guide_progress(self, percentage, message_text): # 이전과 동일
        self.browser_guide_output.setMarkdown(f"**{message_text} ({percentage}%)**\n\n(다른 작업을 계속할 수 있습니다...)")
        QCoreApplication.processEvents()

    def _populate_ui_from_snapshot_data(self, snapshot_data): # 이전과 동일 (user_notes_text 복원 포함)
        try:
            inputs = snapshot_data.get("query_inputs", {}); self.edit_item_input.setText(inputs.get("item_input_text", "")); self.combo_base_class.setCurrentText(inputs.get("base_class", self.BASE_CLASSES[0])); QCoreApplication.processEvents(); self.combo_ascendancy_class.setCurrentText(inputs.get("ascendancy_class", "")); self.combo_league_mode.setCurrentText(inputs.get("league_mode", self.LEAGUE_MODES[0]))
            loaded_league_season = inputs.get("league_season", self.fetched_current_league_name.split(" (")[0]); season_to_select = ""; 
            for i in range(self.combo_league_season.count()):
                if loaded_league_season in self.combo_league_season.itemText(i): season_to_select = self.combo_league_season.itemText(i); break
            if season_to_select: self.combo_league_season.setCurrentText(season_to_select)
            else: self.combo_league_season.setCurrentIndex(0)
            saved_llm_name = inputs.get("selected_llm", "ChatGPT")
            if saved_llm_name == "Gemini": self.combo_llm_select.setCurrentIndex(1) 
            else: self.combo_llm_select.setCurrentIndex(0)
            self.current_item_query = inputs.get("item_input_text", ""); self.current_item_data = snapshot_data.get("crawled_item_data", {}); self.current_char_class = inputs.get("base_class", self.BASE_CLASSES[0]); self.current_ascendancy = inputs.get("ascendancy_class", ""); self.current_league_mode = inputs.get("league_mode", self.LEAGUE_MODES[0]); self.current_league_season = loaded_league_season; self.current_selected_llm = saved_llm_name; self.current_guide_text = snapshot_data.get("generated_guide_text_markdown", "")
            self.current_user_notes = snapshot_data.get("user_notes_text", ""); self.edit_user_notes.setPlainText(self.current_user_notes) 
            self._display_loaded_guide(); self.btn_save_pdf.setEnabled(bool(self.current_guide_text.strip())); self.btn_save_snapshot.setEnabled(bool(self.current_guide_text.strip()) or (self.current_item_data and self.current_item_data.get('notice') == 'no_item_specified')); return True
        except Exception as e: QMessageBox.critical(self, "스냅샷 로드 오류", f"스냅샷 UI 복원 오류:\n{e}"); return False

    def _display_loaded_guide(self): # 이전과 동일
        item_info = self.current_item_data; guide_text = self.current_guide_text; used_llm = self.current_selected_llm; char_class_display = self.current_char_class; ascendancy_display = self.current_ascendancy; league_mode_display = self.current_league_mode; league_season_display = self.current_league_season; item_name_display = item_info.get('name', self.current_item_query if self.current_item_query else "(아이템 미지정)"); class_full_display = char_class_display
        if ascendancy_display and ascendancy_display not in ["전직 선택 안함", "전직 정보 없음", ""]: class_full_display += f" ({ascendancy_display})"
        elif char_class_display == "클래스 선택 안함": class_full_display = "클래스 미지정"
        league_full_display = f"{league_season_display} {league_mode_display}" if league_season_display and league_mode_display else "리그 정보 없음"; title_line = f"### [{item_name_display}] 아이템 정보 (대상: {class_full_display}, 리그: {league_full_display})\n"
        if item_info.get('notice') == 'no_item_specified': title_line = f"### 일반 빌드 가이드 (대상: {class_full_display}, 리그: {league_full_display})\n"
        elif item_info.get('url') and item_info.get('url') != '#': title_line = f"### 조회된 아이템: [{item_name_display}]({item_info.get('url')}) (대상: {class_full_display}, 리그: {league_full_display})\n"
        summary_body = f"**유형:** {item_info.get('type', '(알 수 없음)')}\n" if item_info.get('notice') != 'no_item_specified' else ""
        if item_info.get('mods') and not (len(item_info['mods']) == 1 and '(상세 옵션 정보 없음)' in item_info['mods'][0]):
            summary_body += "**주요 옵션:**\n"; 
            for mod in item_info['mods'][:3]: summary_body += f"- {mod}\n"
            if len(item_info['mods']) > 3: summary_body += "- ... (등등)\n"
        elif item_info.get('notice') == 'mapper_failed': summary_body += "**알림:** 아이템 상세 정보를 찾지 못해, 이름 기반으로 추론합니다.\n"
        elif item_info.get('notice') == 'no_item_specified' and self.current_item_query: summary_body = f"**알림:** '{self.current_item_query}' 아이템 정보를 찾을 수 없었습니다.\n"
        elif item_info.get('notice') == 'no_item_specified': summary_body = "**알림:** 특정 아이템 없이 일반적인 빌드 가이드를 요청한 결과입니다.\n"
        final_markdown_output = title_line + summary_body + f"\n---\n### {used_llm} 생성 가이드 (스냅샷에서 불러옴)\n---\n" + guide_text; self.browser_guide_output.setMarkdown(final_markdown_output)

    def handle_guide_finished(self, status, result_data): # 새 가이드 생성 시 노트 초기화
        item_name_for_title = self.worker.item_query if self.worker and self.worker.item_query else "(아이템 미지정)"
        if isinstance(result_data, dict):
            self.current_item_query = self.worker.item_query if self.worker else ""; self.current_item_data = result_data.get('item_info', {})
            self.current_char_class = result_data.get('char_class', "클래스 선택 안함"); self.current_ascendancy = result_data.get('ascendancy', "")
            self.current_league_mode = result_data.get('league_mode', "소프트코어"); self.current_league_season = result_data.get('league_season', "시즌")
            self.current_selected_llm = result_data.get('used_llm', "LLM"); self.current_guide_text = result_data.get('guide', "")
            item_name_for_title = self.current_item_data.get('name', item_name_for_title) if self.current_item_data else item_name_for_title
            # 새 가이드가 생성되었으므로, 이전 스냅샷에서 불러온 노트가 아닌, 현재 UI의 (비워진) 노트를 current_user_notes로.
            # generate_guide_action에서 이미 UI와 current_user_notes를 비웠으므로, 여기서는 특별히 할 일 없음.
            # 만약 worker가 user_notes를 반환한다면 (지금은 안함), 여기서 self.current_user_notes = result_data.get('user_notes', "") 로 설정 가능.
        else: self.current_guide_text = ""; self.current_item_data = {}; # self.current_user_notes는 유지될 수 있음.
        
        if status == "success": # 성공 시 UI 업데이트 로직 (이전과 동일)
            # ... (이전 handle_guide_finished의 success 블록 코드를 여기에 넣어주게)
            # ... (단, _display_loaded_guide 호출 대신 직접 final_markdown_output 구성)
            char_class_display = self.current_char_class; ascendancy_display = self.current_ascendancy; league_mode_display = self.current_league_mode; league_season_display = self.current_league_season; used_llm = self.current_selected_llm; guide_text = self.current_guide_text; item_info = self.current_item_data
            item_name_display = item_info.get('name', self.current_item_query if self.current_item_query else "(아이템 미지정)")
            class_full_display = char_class_display
            if ascendancy_display and ascendancy_display not in ["전직 선택 안함", "전직 정보 없음", ""]: class_full_display += f" ({ascendancy_display})"
            elif char_class_display == "클래스 선택 안함": class_full_display = "클래스 미지정"
            league_full_display = f"{league_season_display} {league_mode_display}" if league_season_display and league_mode_display else "리그 정보 없음"
            title_line = f"### [{item_name_display}] 아이템 정보 (대상: {class_full_display}, 리그: {league_full_display})\n"
            if item_info.get('notice') == 'no_item_specified': title_line = f"### 일반 빌드 가이드 (대상: {class_full_display}, 리그: {league_full_display})\n"
            elif item_info.get('url') and item_info.get('url') != '#': title_line = f"### 조회된 아이템: [{item_name_display}]({item_info.get('url')}) (대상: {class_full_display}, 리그: {league_full_display})\n"
            summary_body = f"**유형:** {item_info.get('type', '(알 수 없음)')}\n" if item_info.get('notice') != 'no_item_specified' else ""
            if item_info.get('mods') and not (len(item_info['mods']) == 1 and '(상세 옵션 정보 없음)' in item_info['mods'][0]):
                summary_body += "**주요 옵션:**\n"; 
                for mod in item_info['mods'][:3]: summary_body += f"- {mod}\n"
                if len(item_info['mods']) > 3: summary_body += "- ... (등등)\n"
            elif item_info.get('notice') == 'mapper_failed': summary_body += "**알림:** 아이템 상세 정보를 찾지 못해, 이름 기반으로 추론합니다.\n"
            elif item_info.get('notice') == 'no_item_specified' and self.current_item_query: summary_body = f"**알림:** '{self.current_item_query}' 아이템 정보를 찾을 수 없었습니다.\n"
            elif item_info.get('notice') == 'no_item_specified': summary_body = "**알림:** 특정 아이템 없이 일반적인 빌드 가이드를 요청한 결과입니다.\n"
            final_markdown_output = title_line + summary_body + f"\n---\n### {used_llm} 생성 가이드 (완료!)\n---\n" + guide_text
            self.browser_guide_output.setMarkdown(final_markdown_output)
            QMessageBox.information(self, "가이드 생성 완료", f"'{item_name_for_title}' 가이드 생성이 완료되었습니다.")
            self.btn_save_pdf.setEnabled(True); self.btn_save_snapshot.setEnabled(True)

        else: # 실패 또는 취소 시
            self.btn_save_pdf.setEnabled(False); self.btn_save_snapshot.setEnabled(False)
            # ... (오류 메시지 final_markdown_output 구성은 이전과 동일)
        self.btn_generate_guide.setEnabled(True); self.thread = None; self.worker = None

    def save_guide_as_pdf(self): # ... (이전과 동일) ...
        pass
    def save_snapshot_action(self): # 사용자 노트 저장 추가! (이전과 동일)
        user_notes_to_save = self.edit_user_notes.toPlainText() # 현재 UI의 노트 내용을 가져옴!
        # ... (나머지 스냅샷 데이터 구성 및 저장은 이전 v1.3 코드와 동일하게 user_notes_to_save 포함)
        can_save = bool(self.current_guide_text.strip()); 
        if not can_save and self.current_item_data and self.current_item_data.get('notice') == 'no_item_specified' and self.current_char_class and self.current_char_class != "클래스 선택 안함": can_save = True
        if not can_save: QMessageBox.information(self, "저장할 내용 부족", "유효한 가이드 또는 (클래스 선택된) 일반 가이드 요청이 없어 스냅샷 저장 불가."); return
        snapshot_data = { "snapshot_version": "1.3", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "query_inputs": { "item_input_text": self.current_item_query, "base_class": self.current_char_class, "ascendancy_class": self.current_ascendancy, "league_mode": self.current_league_mode, "league_season": self.current_league_season, "selected_llm": self.current_selected_llm  }, "crawled_item_data": self.current_item_data if self.current_item_data else {'name': '(아이템 지정 안함)', 'type': '', 'mods': [], 'url': None, 'notice': 'no_item_specified'}, "generated_guide_text_markdown": self.current_guide_text, "user_notes_text": user_notes_to_save }; item_name = self.current_item_query.replace(" ", "_").replace("/", "_").replace(":", "_"); safe_item_name = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in item_name); safe_item_name = safe_item_name if safe_item_name else ("아이템없음" if self.current_item_query else "일반가이드"); base_class = self.current_char_class.split(" (")[0]; base_class = "모든클래스" if base_class == "클래스 선택 안함" else base_class; asc_class_raw = self.current_ascendancy; asc_class = "_" + asc_class_raw.split(" (")[0] if asc_class_raw and asc_class_raw not in ["전직 선택 안함", "전직 정보 없음", ""] else ""; league_season_for_filename = self.current_league_season.split(" (")[0].replace(" ", "_") if self.current_league_season else "시즌"; default_filename = f"{safe_item_name}_{base_class}{asc_class}_{league_season_for_filename}_{self.current_league_mode}_스냅샷.json"; options = QFileDialog.Options(); file_path, _ = QFileDialog.getSaveFileName(self, "빌드 스냅샷 저장", default_filename, "JSON 파일 (*.json);;모든 파일 (*)", options=options)
        if file_path: 
            if not file_path.lower().endswith(".json"): file_path += ".json"
            try:
                with open(file_path, 'w', encoding='utf-8') as f: json.dump(snapshot_data, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "저장 완료", f"빌드 스냅샷 저장 완료:\n{file_path}")
            except Exception as e: QMessageBox.critical(self, "저장 오류", f"스냅샷 저장 중 오류 발생:\n{e}")
        else: QMessageBox.information(self, "저장 취소됨", "스냅샷 저장이 취소되었습니다.")


    def load_snapshot_action(self): # 이전과 동일 (_populate_ui_from_snapshot_data가 노트 복원)
        # ... (이전 전체 코드 답변에서 이 부분을 복사해서 사용하면 되네)
        options = QFileDialog.Options(); file_path, _ = QFileDialog.getOpenFileName(self, "빌드 스냅샷 불러오기", "", "JSON 파일 (*.json);;모든 파일 (*)", options=options)
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f: snapshot_data = json.load(f)
                if not isinstance(snapshot_data, dict): QMessageBox.warning(self, "파일 형식 오류", "선택한 파일의 내용이 올바른 스냅샷 형식이 아닙니다."); return
                supported_versions = ["1.1", "1.2", "1.3"] 
                if snapshot_data.get("snapshot_version") not in supported_versions: QMessageBox.warning(self, "호환되지 않는 스냅샷", f"선택한 스냅샷 버전({snapshot_data.get('snapshot_version')})이 호환되지 않거나 필수 정보가 누락되었습니다.\n지원 버전: {', '.join(supported_versions)}"); return
                if self._populate_ui_from_snapshot_data(snapshot_data): QMessageBox.information(self, "불러오기 완료", f"스냅샷을 성공적으로 불러왔습니다:\n{file_path}")
                else: print("스냅샷 데이터로 UI 복원 중 문제가 발생했습니다 (세부 오류는 함수 내부 확인).")
            except FileNotFoundError: QMessageBox.critical(self, "파일 오류", "선택한 파일을 찾을 수 없습니다.")
            except json.JSONDecodeError: QMessageBox.critical(self, "파일 오류", "선택한 파일이 올바른 JSON 형식이 아닙니다.")
            except Exception as e: QMessageBox.critical(self, "불러오기 오류", f"스냅샷 불러오는 중 오류 발생:\n{e}")
        else: QMessageBox.information(self, "불러오기 취소됨", "스냅샷 불러오기가 취소되었습니다.")

# ---------------------------------------------------------------------
# 프로그램 실행 부분 (수정된 부분!)
# ---------------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 필수 .py 모듈들은 파일 상단 try-except import에서 실패 시 이미 sys.exit() 처리됨.
    # 여기서는 프로그램 실행에 필요한 .example 설정 파일들이 PyInstaller로 잘 포함되었는지,
    # 또는 개발 환경의 프로젝트 루트에 있는지 확인하는 정도로 변경.
    # 실제 .txt/.ini 파일 생성 및 사용은 PoEPlannerApp 내부에서 처리.
    initial_setup_ok = True
    try:
        # from utils import resource_path # utils.py는 이미 파일 상단에서 임포트 시도됨
        # resource_path 함수가 여기서 사용 가능하다고 가정.
        # 만약 utils.py 임포트가 실패했다면, 프로그램은 이미 위에서 종료되었을 것임.
        
        example_files_to_check = {
            "API 키 예시 파일": resource_path('api_keys.example.txt'),
            "설정 예시 파일": resource_path('config.example.ini')
        }
        missing_example_files_for_bundle = []
        for name, path in example_files_to_check.items():
            if not os.path.exists(path):
                missing_example_files_for_bundle.append(f"- {name} (예상 경로: {path})")
        
        if missing_example_files_for_bundle:
            error_message = "프로그램 실행에 필요한 예시 설정 파일들을 찾을 수 없습니다:\n\n" + \
                            "\n".join(missing_example_files_for_bundle) + \
                            "\n\nPyInstaller로 빌드 시 이 파일들이 '--add-data' 옵션으로 " \
                            "정확한 경로와 이름(예: 'api_keys.example.txt;.' )으로 포함되었는지 확인해주세요.\n" \
                            "개발 환경이라면 프로젝트 루트에 해당 .example 파일들이 있는지 확인해주세요."
            QMessageBox.critical(None, "예시 설정 파일 없음", error_message)
            initial_setup_ok = False 
    except NameError: # resource_path 같은 함수가 정의되지 않았을 경우 (utils.py 임포트 실패 등)
        QMessageBox.critical(None, "초기화 오류", "프로그램 실행에 필요한 기본 함수(resource_path)를 찾을 수 없습니다.\nutils.py 파일이 올바른 위치에 있는지 확인해주세요.")
        initial_setup_ok = False
    except Exception as e:
        QMessageBox.critical(None, "시작 오류", f"프로그램 시작 전 파일 확인 중 예외 발생: {e}")
        initial_setup_ok = False

    if not initial_setup_ok:
        sys.exit(1)

    try:
        ex = PoEPlannerApp()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"프로그램 실행 중 심각한 오류 발생: {e}")
        # import traceback
        # traceback.print_exc() # 개발 시 상세 오류 확인
        QMessageBox.critical(None, "실행 오류", f"프로그램 실행 중 예상치 못한 오류가 발생했습니다:\n{e}\n\n프로그램을 종료합니다.")
        sys.exit(1)