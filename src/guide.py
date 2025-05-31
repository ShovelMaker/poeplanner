# src/guide.py
import configparser
import os
import openai 
import google.generativeai as genai
from utils import resource_path

# API 키 파일 경로 (프로젝트 루트에 있는 api_keys.txt)
# API_KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'api_keys.txt')
API_KEYS_FILE = resource_path('api_keys.txt')

# config.ini 파일 경로는 이제 app_planner.py에서 관리하고, 모델 ID를 직접 받음

def load_api_key(service_name):
    # ... (이전과 동일한 API 키 로드 함수) ...
    if not os.path.exists(API_KEYS_FILE):
        print(f"API 키 파일({API_KEYS_FILE})을 찾을 수 없습니다...")
        return None
    config = configparser.ConfigParser()
    config.read(API_KEYS_FILE, encoding='utf-8')
    if service_name.upper() in config:
        key = config[service_name.upper()].get('API_KEY')
        if not key or "여기에_실제_" in key or key.strip() == "":
            print(f"{service_name} API 키가 설정되지 않았거나 유효하지 않습니다...")
            return None
        return key.strip()
    else:
        print(f"{service_name} API 키를 찾을 수 없습니다...")
        return None

# 이제 각 LLM 생성 함수는 사용할 model_id를 직접 인자로 받도록 수정!
def generate_guide_with_chatgpt(item_data, prompt_override=None, model_id_to_use=None):
    api_key = load_api_key('OPENAI')
    if not api_key: return "OpenAI API 키 오류..."
    
    # 사용할 모델 ID 결정 (인자로 받은 것 우선, 없으면 기본값)
    final_model_id = model_id_to_use if model_id_to_use else "gpt-3.5-turbo" # 기본값
    if not model_id_to_use:
        print(f"알림: ChatGPT 모델 ID가 지정되지 않아 기본 모델 '{final_model_id}'을 사용합니다.")

    try: client = openai.OpenAI(api_key=api_key)
    except Exception as e: return f"OpenAI 클라이언트 초기화 오류: {e}"

    prompt_to_use = prompt_override if prompt_override else _construct_default_prompt(item_data, "ChatGPT 내부 기본 프롬프트용 클래스 정보 (미지정)", "ChatGPT")
    
    try:
        print(f"\nOpenAI ({final_model_id}) API에 가이드 생성을 요청합니다...")
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful Path of Exile expert assistant for beginners, providing advice in Korean and using Markdown for formatting."},
                {"role": "user", "content": prompt_to_use}
            ],
            model=final_model_id # 전달받거나 설정된 모델 사용!
        )
        guide_text = chat_completion.choices[0].message.content
        print("OpenAI로부터 가이드 생성 완료!")
        return guide_text
    except Exception as e: return f"OpenAI API ({final_model_id}) 호출 중 오류: {e}"


def generate_guide_with_gemini(item_data, prompt_override=None, model_id_to_use=None):
    api_key = load_api_key('GEMINI')
    if not api_key: return "Gemini API 키 오류..."

    # 사용할 모델 ID 결정 (인자로 받은 것 우선, 없으면 기본값)
    final_model_id = model_id_to_use if model_id_to_use else "models/gemini-1.5-flash-latest" # 자네가 확인한 기본값으로!
    if not model_id_to_use:
        print(f"알림: Gemini 모델 ID가 지정되지 않아 기본 모델 '{final_model_id}'을 사용합니다.")
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(final_model_id) 
    except Exception as e: return f"Gemini 클라이언트/모델 ('{final_model_id}') 초기화 오류: {e}"

    prompt_to_use = prompt_override if prompt_override else _construct_default_prompt(item_data, "Gemini 내부 기본 프롬프트용 클래스 정보 (미지정)", "Gemini")

    try:
        print(f"\nGemini ({final_model_id}) API에 가이드 생성을 요청합니다...")
        response = model.generate_content(prompt_to_use)
        guide_text = response.text
        print("Gemini로부터 가이드 생성 완료!")
        return guide_text
    except genai.types.generation_types.BlockedPromptException as e:
        return f"Gemini API 요청 차단됨 ({final_model_id}): {e}"
    except Exception as e: return f"Gemini API ({final_model_id}) 호출 중 오류: {e}"


def _construct_default_prompt(item_data, class_context, llm_type_for_log):
    # ... (이전과 동일한 내부 기본 프롬프트 생성 헬퍼 함수) ...
    # (이 함수는 이제 app_planner.py에서 항상 prompt_override를 제공하므로 거의 사용되지 않음)
    item_name = item_data.get('name', '알 수 없는 아이템')
    item_type = item_data.get('type', '알 수 없는 유형')
    mods_list = item_data.get('mods', [])
    if mods_list and '(상세 옵션 정보 없음)' not in mods_list[0]:
        mods_string = "\n- ".join(mods_list)
    else:
        mods_string = "(상세 옵션 정보가 제공되지 않았습니다. 아이템 이름과 유형만으로 추론해주세요.)"
    prompt = f"""
    당신은 Path of Exile 게임의 숙련된 전문가입니다. 사용자가 질문합니다.
    아이템: '{item_name}' ({item_type}), 옵션: - {mods_string}
    대상 사용자: Path of Exile 초보자, 현재 {class_context}입니다.
    요청: 이 아이템에 대해 다음 질문에 답해주세요. (1. 유용성? 2. 활용법/장점? 3. 주의점/팁? 4. 어울리는 다른 실제 PoE 아이템/스킬 2~3가지와 이유? (어려우면 '종류'로))
    답변은 친절하고 자세하게, Markdown 형식을 사용해주세요.
    """
    print(f"알림: 내부 생성 기본 프롬프트를 사용하여 {llm_type_for_log}에 요청합니다. (class_context: {class_context})")
    return prompt

if __name__ == '__main__':
    print("--- Gemini 모델 목록 조회 시작 ---")
    
    # load_api_key 함수와 genai 모듈이 이 파일 상단에 import 되어 있어야 합니다.
    # 예:
    # import google.generativeai as genai
    # (load_api_key 함수는 이미 파일 내에 정의되어 있거나, 올바르게 import 되어야 함)
    # API_KEYS_FILE_PATH도 이 파일 내에서 올바르게 정의되어 있어야 load_api_key가 작동합니다.
    # (이전 전체 코드에서는 API_KEYS_FILE 전역 변수를 사용했었지)

    gemini_api_key = load_api_key('GEMINI') 
    
    available_gemini_models_list = [] # 변수 이름 중복 피하기
    if gemini_api_key:
        print(f"Gemini API 키 로드됨 (일부: {gemini_api_key[:5]}...). 사용 가능한 모델 목록을 조회합니다...")
        try:
            genai.configure(api_key=gemini_api_key) # API 키 설정
            print("\n[정보] 사용 가능한 Gemini 모델 (generateContent 메소드 지원):")
            found_any_models = False
            for m in genai.list_models():
                # generateContent 메소드를 지원하는 모델만 필터링해서 보여줌
                if 'generateContent' in m.supported_generation_methods:
                    print(f"  - 모델 이름: {m.name}")
                    available_gemini_models_list.append(m.name)
                    found_any_models = True
            if not found_any_models:
                print("  generateContent를 지원하는 사용 가능한 Gemini 모델을 찾지 못했습니다.")
            
            print("\n위에 나온 모델 이름 중 하나를 'config.ini' 파일의 GEMINI_MODEL 값으로 사용하거나,")
            print("프로그램 내 'LLM 모델 설정' 창에서 Gemini 모델 ID로 입력할 수 있습니다.")
            print("예를 들어, 'models/gemini-1.5-flash-latest' 등이 일반적입니다.")

        except Exception as e:
            print(f"  Gemini 모델 목록 조회 중 오류 발생: {e}")
    else:
        print("\n[!] Gemini API 키가 설정되지 않았거나 유효하지 않습니다. api_keys.txt 파일을 확인해주세요.")
        print("    Gemini 모델 목록 조회를 진행할 수 없습니다.")
    
    print("-" * 50)
    print("--- Gemini 모델 목록 조회 완료 ---")