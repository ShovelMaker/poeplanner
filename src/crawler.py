# src/crawler.py
import requests
from bs4 import BeautifulSoup
import time

# poedb.tw 접속 시 사용할 기본 URL 및 헤더
BASE_POEDB_URL_KR = "https://poedb.tw/kr/"
HEADERS = {
    'User-Agent': 'PoEPlannerApp/0.1 (github.com/ShovelMaker/poeplanner; for a non-commercial build planning tool)'
}

def get_item_details_from_poedb(identifier_or_url):
    """
    poedb.tw에서 아이템 상세 정보를 가져온다.
    인자로 페이지 식별자(예: "Kaoms_Heart") 또는 전체 URL을 받을 수 있다.
    """
    target_url = ""
    if identifier_or_url.startswith("http"): # 완전한 URL이 직접 들어온 경우
        target_url = identifier_or_url
    else: # 페이지 식별자가 들어온 경우 (예: "Kaoms_Heart")
        target_url = BASE_POEDB_URL_KR + identifier_or_url
    
    print(f"poedb.tw 아이템 크롤링 대상 URL: {target_url}")
    try:
        time.sleep(1.5) # 서버 부하를 줄이기 위한 예의!
        response = requests.get(target_url, headers=HEADERS, timeout=10)
        response.raise_for_status() 

        soup = BeautifulSoup(response.content, 'lxml')

        item_data = {
            'name': None,
            'type': None,
            'mods': [],
            'url': target_url 
        }

        item_header_div = soup.find('div', class_='itemHeader doubleLine')
        if item_header_div:
            name_candidate_div = item_header_div.find('div', class_='itemName')
            if name_candidate_div and 'typeLine' not in name_candidate_div.get('class', []):
                name_span = name_candidate_div.find('span', class_='lc')
                if name_span:
                    item_data['name'] = name_span.text.strip()
            
            type_div = item_header_div.find('div', class_='itemName typeLine')
            if type_div:
                type_span = type_div.find('span', class_='lc')
                if type_span:
                    item_data['type'] = type_span.text.strip()
        else:
            page_title_tag = soup.find('title')
            if page_title_tag:
                page_title = page_title_tag.text.strip()
                item_data['name'] = page_title.split("::")[0].strip() if "::" in page_title else page_title

        stats_div = soup.find('div', class_='Stats') 
        if stats_div:
            for mod_div in stats_div.find_all('div', class_='explicitMod'):
                mod_span = mod_div.find('span', class_='secondary')
                mod_text = ""
                if mod_span:
                    mod_text = mod_span.text.strip()
                else:
                    mod_text = mod_div.text.strip() 
                mod_text = mod_text.replace('[1]', '').strip()
                if mod_text:
                    item_data['mods'].append(mod_text)
        
        if not item_data.get('name'):
             print(f"주의: {target_url} 에서 아이템 이름 정보를 추출하지 못했습니다.")
             return None 

        return item_data

    except requests.exceptions.Timeout:
        print(f"아이템 정보 요청 시간 초과: {target_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"poedb.tw 아이템 요청 중 오류 발생 ({target_url}): {e}")
        return None
    except Exception as e: 
        print(f"아이템 정보 파싱 중 알 수 없는 오류 발생 ({target_url}): {e}")
        return None

# --- 현재 리그 정보 가져오는 새 함수! ---
def get_current_league_info_from_poedb():
    """
    poedb.tw 홈페이지(또는 리그 페이지)를 크롤링하여 
    현재 진행 중인 주력 챌린지 리그의 이름과 버전을 가져온다.
    """
    poedb_main_url = "https://poedb.tw/kr/" 
    print(f"poedb.tw 현재 리그 정보 가져오기 시도: {poedb_main_url}")

    try:
        response = requests.get(poedb_main_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')

        league_cards = soup.find_all('div', class_='card mb-2')
        
        current_league_name = None
        current_league_version = None

        for card in league_cards:
            # "Running for" 텍스트와 GGG API 링크를 가진 <a> 태그를 현재 리그 지표로 사용
            active_league_link = card.find(
                lambda tag: tag.name == 'a' and 
                            "Running for" in tag.get_text(strip=True) and 
                            tag.has_attr('href') and 
                            'pathofexile.com/api/leagues/' in tag['href']
            )

            if active_league_link:
                header = card.find('h5', class_='card-header')
                if header:
                    if header.contents and header.contents[0].string:
                        current_league_name = header.contents[0].string.strip()
                    
                    small_tag = header.find('small', class_='float-end')
                    if small_tag and small_tag.string:
                        current_league_version = small_tag.string.strip()
                    
                    if current_league_name: # 이름이라도 찾았으면 성공
                        break 
        
        if current_league_name:
            print(f"poedb.tw에서 현재 리그 정보 찾음: {current_league_name} (버전: {current_league_version if current_league_version else 'N/A'})")
            return {"name": current_league_name, "version": current_league_version}
        else:
            print("알림: poedb.tw 홈페이지에서 현재 진행 중인 주력 리그 정보를 자동으로 찾지 못했습니다.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"poedb.tw ({poedb_main_url}) 접속 중 오류 발생: {e}")
        return None
    except Exception as e:
        print(f"poedb.tw 현재 리그 정보 파싱 중 알 수 없는 오류 발생: {e}")
        return None

# --- 이 파일을 직접 실행해서 각 함수를 테스트해볼 수 있도록 추가 ---
if __name__ == '__main__':
    print("--- crawler.py 직접 실행 테스트 ---")
    
    # 1. 아이템 상세 정보 크롤링 테스트
    # test_item_id_or_url = "Kaoms_Heart" 
    # test_item_id_or_url = "https://poedb.tw/kr/Mageblood" # URL 직접 테스트
    test_item_id_or_url = "마법사의 피" # item_name_mapper.py가 필요하므로, 여기서는 ID나 URL로 직접 테스트하는 것이 좋음
                                     # app_planner.py에서 mapper를 거친 ID를 이 함수에 넘겨주게 됨.
                                     # 여기서는 직접 ID "Mageblood"를 사용해보세.
    print(f"\n[테스트 1] 아이템 상세 정보 가져오기 (예: Mageblood)")
    item_details = get_item_details_from_poedb("Mageblood") # 직접 ID 사용
    if item_details:
        print(f"아이템 'Mageblood' 정보:")
        for key, value in item_details.items():
            print(f"  {key}: {value}")
    else:
        print(f"아이템 'Mageblood' 정보를 가져오지 못했습니다.")
    print("-" * 30)

    # 2. 현재 리그 정보 가져오기 테스트
    print("\n[테스트 2] 현재 리그 정보 가져오기")
    current_league = get_current_league_info_from_poedb()
    if current_league:
        print(f"  현재 리그 이름: {current_league.get('name')}")
        print(f"  현재 리그 버전: {current_league.get('version')}")
    else:
        print("  현재 리그 정보를 가져오지 못했습니다.")
    print("-" * 30)