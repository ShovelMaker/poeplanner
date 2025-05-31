# src/item_name_mapper.py

# 아이템 이름 <-> poedb.tw URL 식별자 매핑 테이블
# 여기에 계속해서 주요 유니크 아이템들을 추가해주게.
# 키(key)는 가장 일반적이거나 대표적인 형태로 넣어두면,
# 아래 get_poedb_identifier 함수가 입력값과 키를 정규화해서 비교할 걸세.
ITEM_NAME_TO_POEDB_ID = {
    # 한글 이름 (대표적인 형태)
    "타뷸라 라사": "Tabula_Rasa",
    "카옴의 심장": "Kaoms_Heart",
    "복제된 카옴의 심장": "Replica_Kaoms_Heart",
    "별의 재": "Ashes_of_the_Stars",
    "헤드헌터": "Headhunter",
    "헤헌" : "Headhunter",
    "병에 담긴 믿음": "Bottled_Faith",
    "병믿": "Bottled_Faith",          # 아주 흔한 줄임말은 직접 추가
    "전창조": "Progenesis",
    "악몽": "Bitterdream",
    "목소리": "Voices",
    "마법사의 피": "Mageblood", # 이전 테스트에서 사용했던 '마법사의 피'도 추가
    "마피": "Mageblood",
    # 영어 이름 (대표적인 형태, 소문자 기준, 아포스트로피는 함수에서 처리)
    "tabula rasa": "Tabula_Rasa",
    "kaom's heart": "Kaoms_Heart",
    "replica kaom's heart": "Replica_Kaoms_Heart",
    "shavronne's wrappings": "Shavronnes_Wrappings",
    "mageblood": "Mageblood",
    "voices": "Voices",
    "ashes of the stars": "Ashes_of_the_Stars",
    "headhunter": "Headhunter",
    "bottled faith": "Bottled_Faith",
    "progenesis": "Progenesis",
    "bitterdream": "Bitterdream",
    # 자네가 필요하다고 생각하는 다른 아이템들을 이 목록에 계속 추가해주게!
}

def get_poedb_identifier(user_input_name):
    """
    사용자가 입력한 아이템 이름(한글 또는 영어)을 기반으로 
    poedb.tw URL에 사용될 식별자를 반환한다.
    입력값과 매핑 테이블의 키를 정규화(소문자, 아포스트로피 제거, 공백 제거)하여 비교한다.
    """
    if not user_input_name or not user_input_name.strip():
        return None # 비어있는 입력은 처리하지 않음

    # 1. 사용자 입력을 정규화: 소문자로 변경, 아포스트로피 제거, 모든 공백 제거
    normalized_input = user_input_name.lower().replace("'", "").replace(" ", "")

    # 2. 매핑 테이블의 키(key)들도 동일한 방식으로 정규화하여 입력값과 비교
    for key_in_map, poedb_id_value in ITEM_NAME_TO_POEDB_ID.items():
        normalized_key_in_map = key_in_map.lower().replace("'", "").replace(" ", "")
        if normalized_input == normalized_key_in_map:
            print(f"매핑 성공: 입력 '{user_input_name}' -> 정규화된 키와 일치 ('{normalized_key_in_map}') -> ID '{poedb_id_value}'")
            return poedb_id_value # 일치하는 것을 찾으면 바로 반환

    # 3. (선택적 확장) 매핑에 없을 경우, 입력값이 영어 이름일 때 간단한 자동 변환 규칙 시도
    #    주의: 이 규칙은 매우 단순하며, 모든 poedb.tw URL 명명 규칙을 커버하지 못할 수 있음.
    #    한글 입력은 이 자동 변환 규칙의 대상이 아님.
    is_likely_english_for_conversion = all(ord(char) < 128 for char in user_input_name.replace(" ", "").replace("'", ""))
    
    if is_likely_english_for_conversion:
        # 규칙 예: "The Pariah" -> "The_Pariah" (각 단어 첫 글자 대문자, 공백은 밑줄)
        # 또는 "mage blood" -> "Mage_Blood"
        # poedb.tw는 보통 아이템의 각 영어 단어 첫 글자를 대문자로 하고, 공백을 '_'로 대체하는 경향이 있음.
        # 아포스트로피는 보통 제거됨.
        words = user_input_name.replace("'", "").split() # 아포스트로피 제거 후 공백으로 단어 분리
        if words:
            # 각 단어의 첫 글자만 대문자로 하고 나머지는 소문자로 할지, 아니면 전체를 Capitalize 할지 poedb 규칙을 더 봐야함.
            # 여기서는 각 단어를 capitalize하고 '_'로 연결하는 일반적인 방식을 시도.
            potential_id = "_".join(word.capitalize() for word in words)
            print(f"알림: '{user_input_name}'에 대한 직접 매핑 없음. 영어 이름 변환 시도 -> '{potential_id}'")
            # 이 potential_id가 실제로 유효한지는 poedb.tw에 요청을 보내봐야 알 수 있음.
            # 우선은 변환된 형태를 반환하고, 크롤러가 실패하면 사용자가 알 수 있도록 함.
            return potential_id 

    # 모든 경우에 해당하지 않으면 식별자를 찾지 못한 것
    print(f"알림: '{user_input_name}'에 대한 poedb URL 식별자를 내부 매핑 및 자동 변환 규칙으로 찾지 못했습니다.")
    return None

if __name__ == '__main__':
    # 간단한 테스트 코드
    test_names = [
        "카옴의 심장",
        "카옴의심장",
        "kaom's heart",
        "KAOM'S HEART",
        "  kaom's  heart  ",
        "별의 재",
        "별의재",
        "Ashes of the Stars",
        "ashes of the stars",
        "병믿",
        "없는 아이템 이름",
        "Watcher's Eye", # 영어 자동 변환 테스트용
        "The Pariah"     # 영어 자동 변환 테스트용
    ]

    for name in test_names:
        identifier = get_poedb_identifier(name)
        if identifier:
            print(f"입력: '{name}'  =>  ID: '{identifier}'  (URL: https://poedb.tw/kr/{identifier})")
        else:
            print(f"입력: '{name}'  =>  ID를 찾지 못함")
        print("-" * 30)