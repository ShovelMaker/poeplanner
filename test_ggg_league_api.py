# src/app_planner.py
import sys
import os
import json 
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTextBrowser, QMessageBox,
                             QComboBox, QFileDialog, QTextEdit) # QTextEdit 추가!
from PyQt5.QtCore import Qt, QCoreApplication, QObject, QThread, pyqtSignal
from PyQt5.QtPrintSupport import QPrinter

# --- 다른 우리 모듈에서 함수 가져오기 ---
try:
    from guide import generate_guide_with_chatgpt, generate_guide_with_gemini, load_api_key
    from item_name_mapper import get_poedb_identifier
    from crawler import get_item_details_from_poedb, get_current_league_info_from_poedb 
except ImportError as e:
    print(f"필수 모듈 임포트 실패! 프로그램 실행 불가: {e}")
    sys.exit(f"ImportError: {e}. Check console for details. Required modules might be missing in src/.")

# ---------------------------------------------------------------------
# 일꾼 클래스(GuideWorker) 정의 (이전과 동일)
# ---------------------------------------------------------------------
class GuideWorker(QObject): # 이전 버전과 동일하게 유지
    finished = pyqtSignal(str, object) 
    progress = pyqtSignal(int, str)
    def __init__(self, item_query_text, selected_llm_type, 
                 selected_char_class, selected_ascendancy,
                 league_mode, league_season): 
        super().__init__(); self.item_query = item_query_text; self.selected_llm = selected_llm_type
        self.character_class = selected_char_class; self.ascendancy_class = selected_ascendancy
        self.league_mode = league_mode; self.league_season = league_season; self.is_cancelled = False 
    def run(self):
        # ... (이전 답변의 GuideWorker.run() 내용을 여기에 그대로 넣어주게 - 변경 없음)
        # (이전 전체 코드 답변에서 이 부분을 복사해서 사용하면 되네)
        try: # 이전 코드와 동일한 run 메소드 내용
            class_display_for_progress = self.character_class
            if self.ascendancy_class and self.ascendancy_class != "전직 선택 안함": class_display_for_progress += f" ({self.ascendancy_class})"
            elif self.character_class == "클래스 선택 안함": class_display_for_progress = "클래스 미지정"
            league_info_for_progress = f"{self.league_season} {self.league_mode}"
            self.progress.emit(5, f"'{self.item_query if self.item_query else '(아이템 없음)'}' (대상: {class_display_for_progress}, 리그: {league_info_for_progress}) 처리 요청 접수...")
            item_data = None; llm_name_for_display = self.selected_llm 
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return
            if self.item_query: 
                if self.item_query.startswith("http") and "poedb.tw" in self.item_query:
                    self.progress.emit(15, f"URL에서 '{self.item_query}' 정보 가져오는 중...")
                    item_data = get_item_details_from_poedb(self.item_query)
                else:
                    self.progress.emit(10, f"'{self.item_query}' 아이템 이름으로 URL 식별자 찾는 중...")
                    poedb_id = get_poedb_identifier(self.item_query)
                    if poedb_id:
                        self.progress.emit(20, f"'{poedb_id}' 정보 poedb.tw에서 가져오는 중...")
                        item_data = get_item_details_from_poedb(poedb_id)
                    else:
                        self.progress.emit(20, f"'{self.item_query}'에 대한 URL 식별자 찾기 실패.")
                        item_data = {'name': self.item_query, 'type': '(정보 부족)', 'mods': ['(상세 옵션 정보 없음)'], 'url': None, 'notice': 'mapper_failed'}
            else: 
                item_data = {'name': '(아이템 지정 안함)', 'type': '', 'mods': [], 'url': None, 'notice': 'no_item_specified'}
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return
            self.progress.emit(50, "정보 분석 완료, LLM 프롬프트 구성 중...")
            if not item_data or (self.item_query and not item_data.get('name')):
                self.finished.emit("error_crawl", f"'{self.item_query}'에 대한 아이템 정보를 가져오지 못했습니다.")
                return
            item_name_prompt = item_data.get('name', '(아이템 지정 안함)'); item_type_prompt = item_data.get('type', '')
            mods_list_prompt = item_data.get('mods', []); mods_string_prompt = "\n- ".join(mods_list_prompt) if mods_list_prompt and '(상세 옵션 정보 없음)' not in mods_list_prompt[0] else ("(상세 옵션 정보 없음)" if self.item_query else "(아이템 지정 안함)")
            class_context_prompt = f"'{self.character_class}' 클래스" if self.character_class and self.character_class != "클래스 선택 안함" else "특정 클래스 없음"
            if self.character_class and self.character_class != "클래스 선택 안함" and self.ascendancy_class and self.ascendancy_class != "전직 선택 안함": class_context_prompt += f"의 '{self.ascendancy_class}' 전직"
            league_context_prompt = f"'{self.league_season}' 리그 '{self.league_mode}' 환경"
            prompt_for_llm = ""; query_subject = ""
            if self.item_query: 
                query_subject = f"아이템: '{item_name_prompt}' ({item_type_prompt}), 옵션: {mods_string_prompt}\n"
                prompt_for_llm = f"당신은 Path of Exile 전문가입니다. 초보 유저 질문입니다.\n{query_subject}저는 초보자이고, {league_context_prompt}에서 {class_context_prompt} 빌드를 키우려고 합니다.\n1. 이 아이템이 제 상황에 유용한가요?\n2. 유용하다면, 어떻게 활용하고 장점은?\n3. 주의점이나 팁은?\n4. 이 아이템, 제 빌드/리그와 잘 어울리는 실제 PoE 아이템(유형/고유)이나 스킬 젬 2~3가지와 그 이유를 추천해주세요. (어려우면 '종류'로)\nMarkdown으로 친절하고 자세하게 답변해주세요."
            else: 
                query_subject = "(특정 아이템 없이 일반 빌드 조언 요청)\n"
                prompt_for_llm = f"당신은 Path of Exile 전문가입니다. 초보 유저 질문입니다.\n{query_subject}저는 초보자이고, {league_context_prompt}에서 {class_context_prompt} 빌드를 키우려고 합니다.\n1. 제 상황에 맞는 추천 빌드 방향은?\n2. 각 빌드 초반 핵심 스킬 젬은?\n3. 초반 목표로 할 만한 구하기 쉬운 아이템(유형/고유)은?\n4. 빌드 운영 시 주의점이나 팁은?\nMarkdown으로 친절하고 자세하게 답변해주세요."
            progress_message_llm = f"'{item_name_prompt if self.item_query else '(아이템 없음)'}' ({class_display_for_progress}, {league_info_for_progress}) 정보로 {llm_name_for_display}에게 가이드 요청 중..."
            if item_data.get('notice') == 'mapper_failed': progress_message_llm = f"'{item_data.get('name', self.item_query)}' (상세정보 부족...) {llm_name_for_display}에게 가이드 요청 중..."
            self.progress.emit(60, progress_message_llm)
            guide_text = ""; 
            if self.selected_llm == "ChatGPT": guide_text = generate_guide_with_chatgpt(item_data, prompt_override=prompt_for_llm)
            elif self.selected_llm == "Gemini": guide_text = generate_guide_with_gemini(item_data, prompt_override=prompt_for_llm)
            else: self.finished.emit("error_llm_selection", f"내부 오류: 알 수 없는 LLM ({self.selected_llm})"); return
            if self.is_cancelled: self.finished.emit("cancelled", "작업이 취소되었습니다."); return
            self.progress.emit(95, f"{llm_name_for_display} 응답 수신 완료, 결과 표시 준비 중...")
            self.finished.emit("success", {'guide': guide_text, 'item_info': item_data, 'used_llm': llm_name_for_display, 
                                           'char_class': self.character_class, 'ascendancy': self.ascendancy_class, 
                                           'league_mode': self.league_mode, 'league_season': self.league_season })
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
        self.current_selected_llm = ""; self.current_guide_text = ""
        self.current_user_notes = "" # 사용자 노트 저장을 위한 새 변수!
        self.fetched_current_league_name = "시즌"; self.fetched_current_league_version = ""
        try:
            league_info = get_current_league_info_from_poedb()
            if league_info and league_info.get("name"):
                self.fetched_current_league_name = league_info["name"]
                if league_info.get("version"): self.fetched_current_league_name += f" ({league_info['version']})"
                print(f"현재 리그 정보 로드 성공: {self.fetched_current_league_name}")
            else: print("알림: poedb.tw 현재 리그 정보 자동 로드 실패. 기본 '시즌'으로 설정.")
        except Exception as e: print(f"현재 리그 정보 로드 중 오류: {e}. 기본 '시즌'으로 설정.")
        self.initUI(); self.check_api_keys()

    def initUI(self):
        self.setWindowTitle(f'Path of Exile - LLM 빌드 가이드 플래너 (v1.3 - 사용자 노트!)') # 버전 업!
        self.setGeometry(150, 150, 800, 900) # 사용자 노트 공간 위해 높이 더 늘림

        main_vbox = QVBoxLayout()
        # ... (이전 UI 구성: top_controls_layout, mid_controls_hbox, action_buttons_hbox은 동일)
        top_controls_layout = QVBoxLayout()
        item_input_hbox = QHBoxLayout(); lbl_item_input = QLabel('아이템 이름/URL (선택):'); lbl_item_input.setFixedWidth(160)
        self.edit_item_input = QLineEdit(); self.edit_item_input.setPlaceholderText("아이템 지정 시 입력, 없으면 일반 가이드")
        self.edit_item_input.returnPressed.connect(self.generate_guide_action)
        item_input_hbox.addWidget(lbl_item_input); item_input_hbox.addWidget(self.edit_item_input); top_controls_layout.addLayout(item_input_hbox)
        class_asc_hbox = QHBoxLayout(); base_class_vbox = QVBoxLayout(); lbl_base_class_select = QLabel('기본 클래스:')
        self.combo_base_class = QComboBox(); self.combo_base_class.addItems(self.BASE_CLASSES)
        self.combo_base_class.currentTextChanged.connect(self.update_ascendancy_combo)
        base_class_vbox.addWidget(lbl_base_class_select); base_class_vbox.addWidget(self.combo_base_class); class_asc_hbox.addLayout(base_class_vbox)
        asc_class_vbox = QVBoxLayout(); lbl_asc_class_select = QLabel('전직 클래스:')
        self.combo_ascendancy_class = QComboBox(); self.combo_ascendancy_class.setEnabled(False)
        asc_class_vbox.addWidget(lbl_asc_class_select); asc_class_vbox.addWidget(self.combo_ascendancy_class); class_asc_hbox.addLayout(asc_class_vbox)
        self.update_ascendancy_combo(self.combo_base_class.currentText()) 
        top_controls_layout.addLayout(class_asc_hbox); main_vbox.addLayout(top_controls_layout)
        mid_controls_hbox = QHBoxLayout(); league_mode_vbox = QVBoxLayout(); lbl_league_mode = QLabel('리그 유형:')
        self.combo_league_mode = QComboBox(); self.combo_league_mode.addItems(self.LEAGUE_MODES); self.combo_league_mode.setCurrentText("소프트코어")
        league_mode_vbox.addWidget(lbl_league_mode); league_mode_vbox.addWidget(self.combo_league_mode); mid_controls_hbox.addLayout(league_mode_vbox)
        league_season_vbox = QVBoxLayout(); lbl_league_season = QLabel('리그 종류:')
        self.combo_league_season = QComboBox()
        dynamic_league_seasons = [f"{self.fetched_current_league_name} (현재)" if self.fetched_current_league_name != "시즌" else "시즌 (자동로드 실패)", "스탠다드"]
        self.combo_league_season.addItems(dynamic_league_seasons); self.combo_league_season.setCurrentIndex(0)
        league_season_vbox.addWidget(lbl_league_season); league_season_vbox.addWidget(self.combo_league_season); mid_controls_hbox.addLayout(league_season_vbox)
        llm_select_vbox = QVBoxLayout(); lbl_llm_select = QLabel('사용 LLM:'); self.combo_llm_select = QComboBox()
        self.combo_llm_select.addItem("ChatGPT"); self.combo_llm_select.addItem("Gemini") 
        llm_select_vbox.addWidget(lbl_llm_select); llm_select_vbox.addWidget(self.combo_llm_select); mid_controls_hbox.addLayout(llm_select_vbox)
        main_vbox.addLayout(mid_controls_hbox)
        io_buttons_hbox = QHBoxLayout(); self.btn_load_snapshot = QPushButton('스냅샷 불러오기 (.json)'); self.btn_load_snapshot.setFixedHeight(40); self.btn_load_snapshot.clicked.connect(self.load_snapshot_action); io_buttons_hbox.addWidget(self.btn_load_snapshot)
        self.btn_save_snapshot = QPushButton('현재 내용 스냅샷 저장'); self.btn_save_snapshot.setFixedHeight(40); self.btn_save_snapshot.clicked.connect(self.save_snapshot_action); self.btn_save_snapshot.setEnabled(False); io_buttons_hbox.addWidget(self.btn_save_snapshot)
        self.btn_save_pdf = QPushButton('현재 가이드 PDF로 저장'); self.btn_save_pdf.setFixedHeight(40); self.btn_save_pdf.clicked.connect(self.save_guide_as_pdf); self.btn_save_pdf.setEnabled(False); io_buttons_hbox.addWidget(self.btn_save_pdf)
        main_vbox.addLayout(io_buttons_hbox)
        self.btn_generate_guide = QPushButton('빌드 가이드 생성'); self.btn_generate_guide.setFixedHeight(50); self.btn_generate_guide.clicked.connect(self.generate_guide_action); main_vbox.addWidget(self.btn_generate_guide)

        # LLM 가이드 표시 영역 (이전과 동일)
        lbl_guide_output = QLabel('LLM 생성 가이드:'); main_vbox.addWidget(lbl_guide_output)
        self.browser_guide_output = QTextBrowser(); self.browser_guide_output.setPlaceholderText("아이템(선택), 클래스, 리그 등을 선택하고 버튼을 누르세요...")
        self.browser_guide_output.setOpenExternalLinks(True); main_vbox.addWidget(self.browser_guide_output, 1) # stretch factor 1

        # --- 사용자 노트 섹션 추가! ---
        lbl_user_notes = QLabel('나만의 빌드 노트:')
        main_vbox.addWidget(lbl_user_notes)
        self.edit_user_notes = QTextEdit() # 여러 줄 입력 가능한 QTextEdit 사용!
        self.edit_user_notes.setPlaceholderText("LLM 가이드에 대한 보충 설명, 나만의 아이디어, 수정 계획 등을 자유롭게 기록하세요...")
        self.edit_user_notes.setFixedHeight(150) # 노트 영역 초기 높이 지정 (나중에 stretch로 조절 가능)
        main_vbox.addWidget(self.edit_user_notes, 0) # stretch factor 0 (기본 크기 유지, 필요시 늘어남)
        # --- 사용자 노트 섹션 끝 ---

        self.setLayout(main_vbox); self.show()
    
    def update_ascendancy_combo(self, selected_base_class_text): # ... (이전과 동일) ...
        self.combo_ascendancy_class.clear(); base_class_key = selected_base_class_text.split(" (")[0]
        if base_class_key in self.ASCENDANCIES: self.combo_ascendancy_class.addItems(self.ASCENDANCIES[base_class_key]); self.combo_ascendancy_class.setEnabled(base_class_key != "클래스 선택 안함")
        else: self.combo_ascendancy_class.addItem("기본 클래스 오류"); self.combo_ascendancy_class.setEnabled(False)

    def check_api_keys(self): # ... (이전과 동일) ...
        pass # 이전 코드 그대로 사용

    def generate_guide_action(self): # 사용자 노트 초기화 로직 추가
        if self.thread and self.thread.isRunning(): QMessageBox.information(self, "알림", "이미 작업 진행 중"); return
        # ... (이전과 동일한 입력값 가져오기 및 유효성 검사) ...
        item_query = self.edit_item_input.text().strip()
        selected_llm_display_text = self.combo_llm_select.currentText(); llm_type_to_use = "ChatGPT" if "ChatGPT" in selected_llm_display_text else "Gemini"
        selected_base_class = self.combo_base_class.currentText(); selected_ascendancy = ""
        if self.combo_ascendancy_class.isEnabled() and self.combo_ascendancy_class.currentText() not in ["전직 선택 안함", "전직 정보 없음"]: selected_ascendancy = self.combo_ascendancy_class.currentText()
        selected_league_mode = self.combo_league_mode.currentText(); selected_league_season_display = self.combo_league_season.currentText()
        actual_league_name_for_worker = self.fetched_current_league_name.split(" (")[0] if "(현재)" in selected_league_season_display else ("시즌" if "자동로드 실패" in selected_league_season_display else selected_league_season_display)
        if selected_base_class == "클래스 선택 안함" and not item_query: QMessageBox.information(self, "선택 필요", "아이템 미입력 시, 최소 '기본 클래스' 선택 필요."); return
        
        # 새 가이드 생성 시 사용자 노트는 비워주는 것이 좋음 (또는 이전 노트 유지를 선택할 수도 있음)
        self.edit_user_notes.setPlainText("") # 사용자 노트 초기화
        self.current_user_notes = ""        # 내부 변수도 초기화

        self.btn_generate_guide.setEnabled(False); self.btn_save_pdf.setEnabled(False); self.btn_save_snapshot.setEnabled(False)
        # ... (이하 스레드 생성 및 시작 로직은 이전과 동일) ...
        query_display_name = f"'{item_query}'" if item_query else "(아이템 미지정)"
        class_info_for_msg = selected_base_class; 
        if selected_ascendancy: class_info_for_msg += f" ({selected_ascendancy})"
        if selected_base_class == "클래스 선택 안함": class_info_for_msg = "클래스 미지정"
        league_info_for_msg = f"{actual_league_name_for_worker} {selected_league_mode}"
        self.browser_guide_output.setMarkdown(f"{query_display_name} ({class_info_for_msg}, {league_info_for_msg}, {llm_type_to_use} 사용) 가이드 생성 요청 접수... (0%)") 
        QCoreApplication.processEvents()
        self.thread = QThread(); self.worker = GuideWorker(item_query, llm_type_to_use, selected_base_class, selected_ascendancy,selected_league_mode, actual_league_name_for_worker) 
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.update_guide_progress); self.worker.finished.connect(self.handle_guide_finished)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()


    def update_guide_progress(self, percentage, message_text): # ... (이전과 동일) ...
        self.browser_guide_output.setMarkdown(f"**{message_text} ({percentage}%)**\n\n(다른 작업을 계속할 수 있습니다...)")
        QCoreApplication.processEvents()

    def _populate_ui_from_snapshot_data(self, snapshot_data): # 사용자 노트 복원 추가
        try:
            inputs = snapshot_data.get("query_inputs", {})
            self.edit_item_input.setText(inputs.get("item_input_text", ""))
            self.combo_base_class.setCurrentText(inputs.get("base_class", self.BASE_CLASSES[0]))
            QCoreApplication.processEvents() 
            self.combo_ascendancy_class.setCurrentText(inputs.get("ascendancy_class", ""))
            self.combo_league_mode.setCurrentText(inputs.get("league_mode", self.LEAGUE_MODES[0]))
            loaded_league_season = inputs.get("league_season", self.fetched_current_league_name.split(" (")[0])
            season_to_select = ""; 
            for i in range(self.combo_league_season.count()):
                if loaded_league_season in self.combo_league_season.itemText(i): season_to_select = self.combo_league_season.itemText(i); break
            if season_to_select: self.combo_league_season.setCurrentText(season_to_select)
            else: self.combo_league_season.setCurrentIndex(0)
            llm_text = inputs.get("selected_llm", "ChatGPT")
            if "Gemini" in llm_text: self.combo_llm_select.setCurrentText("Gemini")
            else: self.combo_llm_select.setCurrentText("ChatGPT")

            self.current_item_query = inputs.get("item_input_text", "")
            self.current_item_data = snapshot_data.get("crawled_item_data", {})
            self.current_char_class = inputs.get("base_class", self.BASE_CLASSES[0])
            self.current_ascendancy = inputs.get("ascendancy_class", "")
            self.current_league_mode = inputs.get("league_mode", self.LEAGUE_MODES[0])
            self.current_league_season = loaded_league_season
            self.current_selected_llm = llm_text
            self.current_guide_text = snapshot_data.get("generated_guide_text_markdown", "")
            # --- 사용자 노트 복원! ---
            self.current_user_notes = snapshot_data.get("user_notes_text", "") # 저장된 노트 가져오기
            self.edit_user_notes.setPlainText(self.current_user_notes) # 노트 UI에 표시
            # --- 사용자 노트 복원 끝 ---

            self._display_loaded_guide()
            self.btn_save_pdf.setEnabled(bool(self.current_guide_text.strip()))
            self.btn_save_snapshot.setEnabled(bool(self.current_guide_text.strip()) or \
                                              (self.current_item_data and self.current_item_data.get('notice') == 'no_item_specified'))
            return True
        except Exception as e:
            QMessageBox.critical(self, "스냅샷 로드 오류", f"스냅샷 데이터로 UI 복원 중 오류:\n{e}")
            return False

    def _display_loaded_guide(self): # 사용자 노트는 별도로 표시되므로 이 함수는 수정 없음
        # ... (이전과 동일) ...
        # (이전 전체 코드 답변에서 이 부분을 복사해서 사용하면 되네)
        item_info = self.current_item_data; guide_text = self.current_guide_text; used_llm = self.current_selected_llm
        char_class_display = self.current_char_class; ascendancy_display = self.current_ascendancy
        league_mode_display = self.current_league_mode; league_season_display = self.current_league_season
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
        final_markdown_output = title_line + summary_body + f"\n---\n### {used_llm} 생성 가이드 (불러옴)\n---\n" + guide_text
        self.browser_guide_output.setMarkdown(final_markdown_output)


    def handle_guide_finished(self, status, result_data): # 사용자 노트 초기화 로직 추가
        # ... (current_xxx 변수들 업데이트 부분은 이전과 동일) ...
        item_name_for_title = self.worker.item_query if self.worker and self.worker.item_query else "(아이템 미지정)"
        if isinstance(result_data, dict):
            self.current_item_query = self.worker.item_query if self.worker else ""; self.current_item_data = result_data.get('item_info', {})
            self.current_char_class = result_data.get('char_class', "클래스 선택 안함"); self.current_ascendancy = result_data.get('ascendancy', "")
            self.current_league_mode = result_data.get('league_mode', "소프트코어"); self.current_league_season = result_data.get('league_season', "시즌")
            self.current_selected_llm = result_data.get('used_llm', "LLM"); self.current_guide_text = result_data.get('guide', "")
            item_name_for_title = self.current_item_data.get('name', item_name_for_title) if self.current_item_data else item_name_for_title
            self.current_user_notes = "" # 새 가이드 생성 시 사용자 노트는 비워주는 것이 좋음 (이전 스냅샷에서 불러온 노트가 있다면 그것도 초기화)
            self.edit_user_notes.setPlainText("") # UI의 노트 칸도 비움
        else: self.current_guide_text = ""; self.current_item_data = {}; self.current_user_notes = ""; self.edit_user_notes.setPlainText("")
        
        # ... (이하 _display_guide_content 호출 및 버튼 활성화/비활성화 로직은 이전과 동일) ...
        if status == "success":
            self._display_loaded_guide(); QMessageBox.information(self, "가이드 생성 완료", f"'{item_name_for_title}' 가이드 생성이 완료되었습니다.")
            self.btn_save_pdf.setEnabled(True); self.btn_save_snapshot.setEnabled(True)
        else: 
            # ... (오류 메시지 처리 부분은 이전과 동일) ...
            self.btn_save_pdf.setEnabled(False); self.btn_save_snapshot.setEnabled(False)
        self.btn_generate_guide.setEnabled(True); self.thread = None; self.worker = None


    def save_guide_as_pdf(self): # ... (이전과 동일) ...
        pass # 이전 코드 그대로 사용

    def save_snapshot_action(self): # 사용자 노트 저장 추가!
        # ... (저장할 내용 있는지 확인하는 로직은 이전과 유사) ...
        can_save = bool(self.current_guide_text.strip())
        if not can_save and self.current_item_data and self.current_item_data.get('notice') == 'no_item_specified' and self.current_char_class and self.current_char_class != "클래스 선택 안함":
            can_save = True
        if not can_save:
             QMessageBox.information(self, "저장할 내용 부족", "유효한 가이드 또는 (클래스 선택된) 일반 가이드 요청이 없어 스냅샷 저장 불가.")
             return

        # --- 사용자 노트 내용 가져오기! ---
        user_notes_to_save = self.edit_user_notes.toPlainText()
        # --- 사용자 노트 내용 가져오기 끝 ---

        snapshot_data = { 
            "snapshot_version": "1.3", # 버전업! (사용자 노트 추가)
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_inputs": { "item_input_text": self.current_item_query, "base_class": self.current_char_class,
                "ascendancy_class": self.current_ascendancy, "league_mode": self.current_league_mode,
                "league_season": self.current_league_season, "selected_llm": self.current_selected_llm  },
            "crawled_item_data": self.current_item_data if self.current_item_data else \
                                {'name': '(아이템 지정 안함)', 'type': '', 'mods': [], 'url': None, 'notice': 'no_item_specified'},
            "generated_guide_text_markdown": self.current_guide_text,
            "user_notes_text": user_notes_to_save # --- 사용자 노트 저장! ---
        }
        # ... (이하 파일 이름 생성 및 JSON 저장 로직은 이전과 동일) ...
        item_name = self.current_item_query.replace(" ", "_").replace("/", "_").replace(":", "_"); safe_item_name = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in item_name); safe_item_name = safe_item_name if safe_item_name else ("아이템없음" if self.current_item_query else "일반가이드")
        base_class = self.current_char_class.split(" (")[0]; base_class = "모든클래스" if base_class == "클래스 선택 안함" else base_class
        asc_class_raw = self.current_ascendancy; asc_class = "_" + asc_class_raw.split(" (")[0] if asc_class_raw and asc_class_raw not in ["전직 선택 안함", "전직 정보 없음", ""] else ""
        league_season_for_filename = self.current_league_season.split(" (")[0].replace(" ", "_") if self.current_league_season else "시즌"
        default_filename = f"{safe_item_name}_{base_class}{asc_class}_{league_season_for_filename}_{self.current_league_mode}_스냅샷.json"
        options = QFileDialog.Options(); file_path, _ = QFileDialog.getSaveFileName(self, "빌드 스냅샷 저장", default_filename, "JSON 파일 (*.json);;모든 파일 (*)", options=options)
        if file_path: 
            if not file_path.lower().endswith(".json"): file_path += ".json"
            try:
                with open(file_path, 'w', encoding='utf-8') as f: json.dump(snapshot_data, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "저장 완료", f"빌드 스냅샷 저장 완료:\n{file_path}")
            except Exception as e: QMessageBox.critical(self, "저장 오류", f"스냅샷 저장 중 오류 발생:\n{e}")
        else: QMessageBox.information(self, "저장 취소됨", "스냅샷 저장이 취소되었습니다.")

    def load_snapshot_action(self): # 사용자 노트 복원 부분은 _populate_ui_from_snapshot_data에서 처리됨
        # ... (이전과 동일) ...
        options = QFileDialog.Options(); file_path, _ = QFileDialog.getOpenFileName(self, "빌드 스냅샷 불러오기", "", "JSON 파일 (*.json);;모든 파일 (*)", options=options)
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f: snapshot_data = json.load(f)
                if not isinstance(snapshot_data, dict): QMessageBox.warning(self, "파일 형식 오류", "선택한 파일의 내용이 올바른 스냅샷 형식이 아닙니다."); return
                # 버전 체크 확장: "1.1", "1.2", "1.3" 모두 호환 가능하도록
                if snapshot_data.get("snapshot_version") not in ["1.1", "1.2", "1.3"]: 
                    QMessageBox.warning(self, "호환되지 않는 스냅샷", "선택한 스냅샷 파일의 버전이 호환되지 않거나 필수 정보가 누락되었습니다."); return
                if self._populate_ui_from_snapshot_data(snapshot_data): QMessageBox.information(self, "불러오기 완료", f"스냅샷을 성공적으로 불러왔습니다:\n{file_path}")
                else: print("스냅샷 데이터로 UI 복원 중 문제가 발생했습니다 (세부 오류는 함수 내부 확인).")
            except FileNotFoundError: QMessageBox.critical(self, "파일 오류", "선택한 파일을 찾을 수 없습니다.")
            except json.JSONDecodeError: QMessageBox.critical(self, "파일 오류", "선택한 파일이 올바른 JSON 형식이 아닙니다.")
            except Exception as e: QMessageBox.critical(self, "불러오기 오류", f"스냅샷 불러오는 중 오류 발생:\n{e}")
        else: QMessageBox.information(self, "불러오기 취소됨", "스냅샷 불러오기가 취소되었습니다.")

# ---------------------------------------------------------------------
# 프로그램 실행 부분 (이전과 동일)
# ---------------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # ... (이하 필수 파일 체크 로직은 이전과 동일) ...
    ex = PoEPlannerApp()
    sys.exit(app.exec_())