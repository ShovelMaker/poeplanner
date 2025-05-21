# src/guide.py
import configparser
import os

# API 키 파일 경로 (프로젝트 최상단에 있다고 가정)
API_KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api_keys.txt')

def load_api_key(service_name):
    """api_keys.txt 파일에서 지정된 서비스의 API 키를 로드한다."""
    if not os.path.exists(API_KEYS_FILE):
        print(f"API 키 파일({API_KEYS_FILE})을 찾을 수 없습니다. api_keys.example.txt를 복사하여 생성해주세요.")
        return None

    config = configparser.ConfigParser()
    config.read(API_KEYS_FILE)

    # api_keys.txt 파일 형식 예시:
    # [OPENAI]
    # API_KEY = your_openai_api_key_here
    # [GEMINI]
    # API_KEY = your_gemini_api_key_here

    if service_name.upper() in config:
        return config[service_name.upper()].get('API_KEY')
    else:
        print(f"{service_name} API 키를 찾을 수 없습니다. {API_KEYS_FILE} 파일을 확인해주세요.")
        return None

# --- ChatGPT 연동 함수 (예시) ---
def generate_guide_with_chatgpt(prompt, item_info=None):
    api_key = load_api_key('OPENAI')
    if not api_key:
        return "OpenAI API 키가 설정되지 않았습니다."

    # 여기에 openai 라이브러리를 사용한 API 호출 로직 추가
    # 예: import openai
    # openai.api_key = api_key
    # response = openai.ChatCompletion.create(...)
    # formatted_prompt = f"{prompt}\n\n아이템 정보:\n{item_info}" # 프롬프트 조합 예시

    # 임시 반환 (실제 API 호출 로직으로 대체 필요)
    return f"[ChatGPT 응답 예시]\n프롬프트: {prompt}\n아이템: {item_info}\n가이드 내용이 여기에 생성됩니다."

# --- Gemini 연동 함수 (예시) ---
def generate_guide_with_gemini(prompt, item_info=None):
    api_key = load_api_key('GEMINI')
    if not api_key:
        return "Gemini API 키가 설정되지 않았습니다."

    # 여기에 google-generativeai 라이브러리를 사용한 API 호출 로직 추가
    # 예: import google.generativeai as genai
    # genai.configure(api_key=api_key)
    # model = genai.GenerativeModel('gemini-pro') # 또는 다른 모델
    # response = model.generate_content(...)
    # formatted_prompt = f"{prompt}\n\n아이템 정보:\n{item_info}" # 프롬프트 조합 예시

    # 임시 반환 (실제 API 호출 로직으로 대체 필요)
    return f"[Gemini 응답 예시]\n프롬프트: {prompt}\n아이템: {item_info}\n가이드 내용이 여기에 생성됩니다."

if __name__ == '__main__':
    # api_keys.txt 파일 생성 및 키 입력 후 테스트
    # 예: OPENAI_API_KEY=... 또는 GEMINI_API_KEY=...
    # (실제 파일 내용은 주석 처리 없이 KEY = VALUE 형식이어야 함)

    print("--- OpenAI API 키 로드 테스트 ---")
    openai_key = load_api_key('OPENAI')
    if openai_key:
        print("OpenAI 키 로드 성공 (일부만 표시):", openai_key[:5] + "...")
        # 실제 가이드 생성 테스트
        # item_example = "이름: 마법사의 피\n옵션1: 플라스크 효과 지속시간 50% 증가\n옵션2: 사용 시 플라스크 충전량 20 감소"
        # guide = generate_guide_with_chatgpt("이 아이템을 얻었는데, 내 Cyclone Slayer 빌드에 어떻게 적용할 수 있을까?", item_example)
        # print(guide)
    else:
        print("OpenAI 키 로드 실패.")

    print("\n--- Gemini API 키 로드 테스트 ---")
    gemini_key = load_api_key('GEMINI')
    if gemini_key:
        print("Gemini 키 로드 성공 (일부만 표시):", gemini_key[:5] + "...")
        # 실제 가이드 생성 테스트
        # item_example = "이름: 별의 재\n옵션1: 모든 스킬 젬 레벨 +1\n옵션2: 모든 저항 최대치 +3%"
        # guide = generate_guide_with_gemini("이 목걸이를 주웠는데, 내 Arc Elementalist 빌드에 도움이 될까?", item_example)
        # print(guide)
    else:
        print("Gemini 키 로드 실패.")

    # api_keys.txt 파일 예시 (프로젝트 루트에 생성)
    # 파일명: api_keys.txt
    """
[OPENAI]
API_KEY = 여기에_실제_OPENAI_API_키_입력

[GEMINI]
API_KEY = 여기에_실제_GEMINI_API_키_입력
    """