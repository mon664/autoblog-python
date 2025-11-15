import os
import logging
import dotenv
import datetime
import time
import re
import sys
import random
import chromedriver_autoinstaller
import pyperclip
import logging
import requests
import json
import pickle
import string
import undetected_chromedriver as uc
from rapidfuzz import fuzz
from openAI import OpenAIWrapper
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, NoSuchWindowException,WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from pyshorteners.shorteners import tinyurl
from searchconsole import SearchConsoleIndexer
from typing import Optional

# --- Load Environment Variables ---
# Load from blogger.env relative to this file's location
script_dir = os.path.dirname(__file__)

# --- Configuration ---
# Use getenv which reads from loaded vars or system env
CLIENT_SECRETS_FILE = dotenv.get_key('blogger.env','GOOGLE_CLIENT_SECRETS_PATH') or 'client_secrets.json'
TOKEN_FILE = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/blogger']

# @TODO: .env 파일 공통 부분과 각 블로그 부분 분리하기. os.getenv 제거하기
class BloggerClient:
    """
    Handles authentication and interaction with the Google Blogger API v3.
    """
    def __init__(self, menu_gui):
        self.gui = menu_gui
        self.credentials = None
        self.service = None
        self.COUPANG_USERNAME = dotenv.get_key('.env','COUPANG_USERNAME')
        self.COUPANG_PASSWORD = dotenv.get_key('.env','COUPANG_PASSWORD')
        self.use_coupang_link_config = dotenv.get_key('blogger.env', 'USE_MY_COUPANG_LINKS') == 'True' # 쿠팡 링크 세팅 파일을 사용하는지.. 
        self.USE_COUPANG_IMAGE = dotenv.get_key('blogger.env','USE_COUPANG_IMAGE') == 'True'
        self.USE_COUPANG_REVIEW = dotenv.get_key('blogger.env','USE_COUPANG_REVIEW') == 'True'
        self.USE_COUPANG_AI_REVIEW = dotenv.get_key('blogger.env','USE_COUPANG_AI_REVIEW') == 'True'
        self.USE_COUPANG_AI_GUIDE = dotenv.get_key('blogger.env','USE_COUPANG_AI_GUIDE') == 'True'
        self.TEMPLATE_NAME = dotenv.get_key('blogger.env','TEMPLATE_NAME')
        self.USE_SEARCH_CONSOLE = dotenv.get_key('blogger.env','USE_SEARCH_CONSOLE')
        self.USE_ROCKET_SHIPPING = dotenv.get_key('blogger.env', 'USE_ROCKET_SHIPPING')
        self.USE_EXACT_SEARCH_MATCHING =  dotenv.get_key('blogger.env', 'USE_EXACT_SEARCH_MATCHING')
        self.COUPANG_PRODUCT_LIMIT = dotenv.get_key('blogger.env','COUPANG_PRODUCT_LIMIT')
        self.USE_CUSTOM_TITLE_BANNER = dotenv.get_key('blogger.env', 'USE_CUSTOM_TITLE_BANNER')
        self.USE_GPT_IMAGE_CREATION = dotenv.get_key('blogger.env','USE_GPT_IMAGE_CREATION')
        self.TITLE_BANNER_TEMPLATE_NAME =dotenv.get_key('blogger.env','TITLE_BANNER_TEMPLATE_NAME')
        self.USE_GPT_POST_TITLE = dotenv.get_key('blogger.env','USE_GPT_POST_TITLE')
        self.USE_GPT_POST_DESCRIPTION = dotenv.get_key('blogger.env','USE_GPT_POST_DESCRIPTION')
        self.USE_SHORT_URL = dotenv.get_key('.env','USE_SHORT_URL')
        self.BANNED_WORDS = dotenv.get_key('.env', 'BANNED_WORDS')
        self.KEEP_COUPANG_LOGIN = dotenv.get_key('.env', 'KEEP_COUPANG_LOGIN')
        # Ensure paths are relative to script dir or absolute
        global CLIENT_SECRETS_FILE, TOKEN_FILE
       
        logging.info(f"BloggerClient initialized. Secrets: {CLIENT_SECRETS_FILE}, Token: {TOKEN_FILE}")
        
        # GUI로부터 필요한 설정 값 가져오기
        self.selected_ch_id = self.gui.selected_ch_id
        self.selected_tistory_domain = self.gui.selected_tistory_domain
        self.selected_category = self.gui.selected_category
        self.selected_id = self.gui.selected_id
        self.selected_password = self.gui.selected_password
        self.keywords = self.gui.keywords
        self.use_naver = self.gui.use_naver
        self.selected_naver_category = self.gui.selected_naver_category
        self.multiple_post = False
        self.is_random = False
    
        if self.TEMPLATE_NAME == 'random':
            self.is_random = True
        if self.USE_COUPANG_AI_REVIEW or self.USE_COUPANG_AI_GUIDE:
            self.openai = OpenAIWrapper()
        self.next_schedule_time: Optional[datetime.datetime] = None
        self.search_fail = []
        
    
    def get_base_path(self):
        """
        실행 중인 스크립트 또는 .exe 파일이 위치한 디렉토리의 절대 경로를 반환.
        PyInstaller로 생성된 .exe 파일의 실제 위치를 기준.
        """
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # .exe 파일로 실행 중인 경우, .exe 파일 자체의 디렉토리를 반환
            # sys.executable은 .exe 파일의 경로를 가리킵니다.
            application_path = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # 일반 .py 스크립트로 실행 중인 경우, 스크립트 파일의 디렉토리를 반환
            application_path = os.path.dirname(os.path.abspath(__file__))
            
        return application_path

    def load_random_template_content(self, templates_dir_name='templates'):
        """
        실행 환경(스크립트 또는 .exe)을 고려하여, 
        실행 파일/스크립트와 같은 레벨 또는 하위에 위치한 지정된 이름의 디렉토리에서 
        조건을 만족하는 템플릿 파일 중 하나의 내용을 랜덤하게 로드합니다.

        Args:
            templates_dir_name (str): 실행 파일/스크립트 기준 상대적인 템플릿 디렉토리 이름.

        Returns:
            str or None: 랜덤하게 선택된 템플릿 파일의 내용. 
                        조건에 맞는 파일이 없거나 오류 발생 시 None 반환.
        """
        eligible_filenames = [] # 이제 파일 이름을 저장합니다.
    
        try:
            # 1. 기준 경로 가져오기
            base_path = self.get_base_path()
            
            # 2. 템플릿 디렉토리의 전체 경로 생성
            templates_full_path = os.path.join(base_path, templates_dir_name)

            if not os.path.isdir(templates_full_path):
                print(f"오류: 템플릿 디렉토리를 찾을 수 없습니다: {templates_full_path}", file=sys.stderr)
                print(f"      (.exe 파일과 같은 위치에 '{templates_dir_name}' 폴더가 있는지 확인하세요.)", file=sys.stderr)
                return None

            # templates 디렉토리 내의 모든 항목 이름 리스트 가져오기
            for item_name in os.listdir(templates_full_path):
                item_path = os.path.join(templates_full_path, item_name)

                # 1. 파일인지 확인
                # 2. 이름이 'description'으로 시작하지 않는지 확인
                if os.path.isfile(item_path) and not item_name.lower().startswith('description'):
                    # 조건을 만족하는 *파일 이름*을 리스트에 추가
                    eligible_filenames.append(item_name) 

            if not eligible_filenames:
                print(f"경고: '{templates_full_path}' 디렉토리에서 로드할 수 있는 템플릿 파일을 찾지 못했습니다.", file=sys.stderr)
                print(f"(description으로 시작하지 않고, 하위 폴더에 있지 않은 파일)", file=sys.stderr)
                return None

            # 조건을 만족하는 파일 리스트 중에서 무작위로 하나 선택
            random_template_filename = random.choice(eligible_filenames)
            print(f"선택된 템플릿 파일명 (확장자 포함): {random_template_filename}") # 디버깅용

             # 파일 이름에서 확장자 제거
            template_name_without_extension = os.path.splitext(random_template_filename)[0]
            
            # 확장자 없는 파일 이름 반환
            return template_name_without_extension

        except Exception as e:
            print(f"템플릿 로드 중 오류 발생: {e}", file=sys.stderr)
            return None
    
    def authenticate(self) -> bool:
        """Authenticates the user using OAuth 2.0."""
        self.credentials = None
        if os.path.exists(TOKEN_FILE):
            try:
                self.credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                logging.info("Loaded credentials from token file.")
            except Exception as e:
                logging.warning(f"Failed to load credentials from {TOKEN_FILE}: {e}. Need re-authentication.")
                self.credentials = None

        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    logging.info("Refreshing expired credentials...")
                    self.credentials.refresh(Request())
                    logging.info("Credentials refreshed successfully.")
                except Exception as e:
                    logging.warning(f"Failed to refresh credentials: {e}. Need re-authentication.")
                    self.credentials = None
            else:
                if not os.path.exists(CLIENT_SECRETS_FILE):
                    logging.error(f"Client secrets file not found at: {CLIENT_SECRETS_FILE}")
                    raise FileNotFoundError(f"Blogger 인증에 필요한 클라이언트 보안 비밀 파일 없음: {CLIENT_SECRETS_FILE}")

                try:
                    logging.info("Starting OAuth 2.0 flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
                    self.credentials = flow.run_local_server(port=0)
                    logging.info("OAuth 2.0 flow completed successfully.")
                except FileNotFoundError:
                     logging.error(f"Client secrets file not found at: {CLIENT_SECRETS_FILE}")
                     raise FileNotFoundError(f"클라이언트 보안 비밀 파일 '{CLIENT_SECRETS_FILE}'을(를) 찾을 수 없습니다. blogger.env 파일의 경로를 확인하세요.")
                except Exception as e:
                    logging.exception("Error during OAuth 2.0 flow.")
                    raise RuntimeError(f"Blogger 인증 중 오류 발생: {e}")

            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.credentials.to_json())
                logging.info(f"Credentials saved to {TOKEN_FILE}")
            except Exception as e:
                logging.error(f"Failed to save credentials to {TOKEN_FILE}: {e}")

        if self.credentials and self.credentials.valid:
            try:
                self.service = build('blogger', 'v3', credentials=self.credentials, cache_discovery=False)
                logging.info("Blogger API service built successfully.")
                return True
            except Exception as e:
                logging.exception("Failed to build Blogger API service.")
                self.service = None
                return False
        else:
            logging.error("Authentication failed: No valid credentials.")
            self.service = None
            return False

    def is_authenticated(self) -> bool:
        """Checks if the client is authenticated."""
        return self.service is not None and self.credentials is not None and self.credentials.valid

    # --- get_blogs (Keep as is) ---
    def get_blogs(self) -> list | None:
        if not self.is_authenticated():
            logging.error("Cannot get blogs: Not authenticated.")
            if not self.authenticate():
                 return None
        try:
            blogs = self.service.blogs().listByUser(userId='self').execute()
            logging.info(f"Fetched {len(blogs.get('items', []))} blogs for the user.")
            return blogs.get('items', [])
        except HttpError as error:
            logging.error(f"An API error occurred while fetching blogs: {error}")
            return None
        except Exception as e:
            logging.exception("An unexpected error occurred while fetching blogs.")
            return None

    def send_blogger_api(self, post_title: str, content_html: str, blog_id: str) -> None:
        """
        Generates title/content (placeholder) and sends the post to the Blogger API,
        handling scheduling if enabled in the GUI.
        """
        logging.info(f"Preparing post for Blog ID {blog_id}: '{post_title}'")
        # logging.debug(f"Generated Content (Placeholder): {content_html}") # Avoid logging potentially large HTML

        # Determine initial draft status based on user intent (before potential scheduling override)
        # If scheduling is OFF, this value is used.
        # If scheduling is ON, create_post will force it to True anyway.
        intended_is_draft = False # Set to True if you want default to be draft when not scheduling

        try:
            created_post = self.create_post(
                blog_id=blog_id,
                title=post_title,
                content_html=content_html,
                is_draft=intended_is_draft, # Pass the intended status
                labels=None # Optional: ["자동", "테스트"]
            )
            if created_post:
                post_url = created_post.get('url')
                post_status = created_post.get('status') # 'LIVE', 'DRAFT', 'SCHEDULED'
                logging.info(f"Blogger post {'created' if post_status != 'SCHEDULED' else 'scheduled'} successfully on blog {blog_id}. Status: {post_status}. URL: {post_url}")
                # Only submit to Search Console if it's live immediately (optional)
                if post_status == 'LIVE' and self.USE_SEARCH_CONSOLE == 'True' and post_url:
                     # Ensure HTTPS if needed by Search Console
                     secure_url = post_url.replace('http://', 'https://')
                     self.search_console.process_urls([secure_url])
                elif post_status == 'DRAFT':
                    logging.info(f"예약 포스팅은 서치콘솔 자동 등록을 지원하지 않습니다.")
            else:
                # This case might happen if authentication failed within create_post
                raise RuntimeError("Failed to create or schedule Blogger post (API or authentication failed).")

        except HttpError as http_err:
             logging.error(f"HTTP error during post creation/scheduling: {http_err}")
             error_content = http_err.content.decode() if http_err.content else '(No details)'
             # Consider specific error codes, e.g., 400 for bad request (maybe invalid date format)
             raise RuntimeError(f"Blogger API Error: {http_err.resp.status} {http_err.reason}\nDetails: {error_content}") from http_err
        except ValueError as ve:
             # Catch errors from parsing the schedule interval
             logging.error(f"Error processing schedule interval: {ve}")
             raise RuntimeError(f"Invalid schedule interval setting: {ve}") from ve
        except Exception as e:
             logging.exception("Error during send_blogger_api execution.")
             raise RuntimeError(f"An unexpected error occurred during Blogger processing: {e}") from e


    def create_post(self, blog_id: str, title: str, content_html: str, is_draft: bool = False, labels: list = None) -> Optional[dict]:
        """
        Creates or schedules a post on Blogger.
        """
        if not self.is_authenticated():
            logging.error("Cannot create post: Not authenticated.")
            if not self.authenticate():
                 return None
        if not blog_id:
            logging.error("Cannot create post: Blog ID is missing.")
            return None

        post_body = {
            'kind': 'blogger#post',
            'blog': {'id': blog_id},
            'title': title,
            'content': content_html,
        }
        if labels:
            post_body['labels'] = labels if isinstance(labels, list) else [labels]

        schedule_active = getattr(self.gui, 'use_scheduling', False) # Safely check attribute
        publish_time_str = None
        final_is_draft = is_draft # Start with the intended draft status

        if schedule_active:
            interval_str = getattr(self.gui, 'selected_schedule_interval', None) # e.g., "2시간마다"
            if not interval_str:
                logging.warning("Scheduling is enabled, but no interval is selected. Posting immediately.")
            else:
                try:
                    # Extract the number from the string (e.g., "2시간마다" -> 2)
                    match = re.match(r"(\d+)", interval_str)
                    if not match:
                        raise ValueError(f"Could not parse hours from interval string: '{interval_str}'")
                    interval_hours = int(match.group(1))
                    if interval_hours <= 0:
                         raise ValueError(f"Interval hours must be positive: {interval_hours}")

                    # --- Scheduling Logic ---
                    now = datetime.datetime.now(datetime.timezone.utc)
                    
                    schedule_base_time = now
                    if self.next_schedule_time and self.next_schedule_time > now:
                       schedule_base_time = self.next_schedule_time

                    publish_time = schedule_base_time + datetime.timedelta(hours=interval_hours)
                    
                    min_future_time = now + datetime.timedelta(minutes=1) # Ensure at least 1 min in future
                    if publish_time < min_future_time:
                        publish_time = min_future_time
                        logging.warning(f"Calculated schedule time was too close to now. Adjusted to: {publish_time.isoformat()}")


                    # Format for Blogger API (RFC 3339 UTC)
                    # Use isoformat and ensure 'Z' for UTC timezone indicator
                    publish_time_str = publish_time.isoformat(timespec='seconds').replace('+00:00', 'Z')

                    # next schedule time
                    self.next_schedule_time = publish_time

                    post_body['published'] = publish_time_str
                    final_is_draft = False # MUST be draft if 'published' is in the future
                    logging.info(f"Scheduling post for: {publish_time_str}")

                except ValueError as e:
                    logging.error(f"Invalid schedule interval '{interval_str}': {e}. Posting immediately.")
                   
                    final_is_draft = is_draft # Revert to original intent if scheduling fails
                    publish_time_str = None # Ensure 'published' is not in body
                    if 'published' in post_body: del post_body['published']
           


        # --- API Call ---
        try:
            action = "scheduling" if publish_time_str else ("creating draft" if final_is_draft else "publishing")
            logging.info(f"Attempting to {action} post on blog ID {blog_id}: '{title}'")

            # Ensure isDraft parameter matches final_is_draft decision
            created_post = self.service.posts().insert(
                blogId=blog_id,
                body=post_body,
                isDraft=final_is_draft # Use the final determined draft status
            ).execute()

            post_id = created_post.get('id')
            post_status = created_post.get('status') # LIVE, DRAFT, SCHEDULED
            logging.info(f"Successfully submitted post '{title}'. Final Status: {post_status}, ID: {post_id}")
            return created_post

        except HttpError as error:
            logging.error(f"An API error occurred while {action} post: {error}")
            # Reraise the error to be caught by the caller (send_blogger_api)
            raise error
        except Exception as e:
            logging.exception(f"An unexpected error occurred while {action} post.")
            # Reraise the error
            raise e
         
         
         
         
    def setChromium(self)->webdriver.Chrome:
        """Chrome 웹드라이버 설정"""
        chrome_ver = chromedriver_autoinstaller.get_chrome_version().split('.')[0]
        
        try:
            fake_options = webdriver.ChromeOptions()
            fake_driver = webdriver.Chrome(service=Service(os.getcwd().replace('\\', '/')+f'/driver/{chrome_ver}/chromedriver.exe'), options=fake_options)
        except:
            chromedriver_autoinstaller.install(False, os.getcwd().replace('\\', '/')+'/driver')
            fake_options = webdriver.ChromeOptions()
            fake_driver = webdriver.Chrome(service=Service(os.getcwd().replace('\\', '/')+f'/driver/{chrome_ver}/chromedriver.exe'), options=fake_options)
        
        user_agent = fake_driver.execute_script("return navigator.userAgent;")
        fake_driver.close()
        
        options = webdriver.ChromeOptions()
        print(f'사용자 크롬 버전: {chrome_ver}, User-Agent: {user_agent}')
        options.add_argument('user-agent=' + user_agent)
        options.add_argument('--log-level=3')
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        
        # 성능 최적화
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")  # 이미지 로딩 차단
        options.add_argument("--disable-javascript")  # JavaScript 차단 (가능한 경우)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
       
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(service=Service(os.getcwd().replace('\\', '/')+f'/driver/{chrome_ver}/chromedriver.exe'), options=options)
        driver.implicitly_wait(10)
        driver.maximize_window()
        return driver
    
    def getUndetectedChrome(self):
        return uc.Chrome() 
    # 단축 url 을 생성하는 함수
    def short(self, url):
        return tinyurl.Shortener().short(url)
      
        
        
    # url의 이미지를 로컬에 저장    
    def save_image(self, url):
        # 이미지 요청을 보내고 내용을 다운로드합니다.
        response = requests.get(url)
        random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self.image_filename = f"today_shopping_title_{random_string}.png"
        # 성공적으로 다운로드했다면 파일로 저장합니다.
        if response.status_code == 200:
            with open(self.image_filename, "wb") as file:
                file.write(response.content)
            print(f"이미지가 {self.image_filename}로 저장되었습니다.")
        else:
            print(f"이미지를 다운로드하지 못했습니다. 상태 코드: {response.status_code}")    
            
            
    def wait_for_page_load(self, driver, timeout=10):
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            print("페이지가 로드되었습니다.")
        except TimeoutException:
            print("페이지 로드 시간 초과")     
            
    def find_review_article(self, driver, attempts=3, timeout=10):
        for attempt in range(attempts):
            try:
                review_article = WebDriverWait(driver, timeout).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, '.sdp-review__article__list'))
                )
                print(f"리뷰 요소를 찾았습니다. 시도: {attempt + 1}")
                return review_article
            except TimeoutException:
                print(f"리뷰 요소를 찾지 못했습니다. 시도: {attempt + 1}")
                time.sleep(2)  # 잠시 대기 후 재시도
        return None
    
    
    def load_template(self, template_name, template_dic=None) -> str:
        """HTML 템플릿 파일을 로드합니다."""
        if template_dic is None:
            template_path = os.path.join('templates', f"{template_name}.html")
        else:
            template_path = os.path.join('templates',template_dic,f"{template_name}.html")

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"템플릿 파일이 없습니다: {template_path}")

        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
   
    def get_banner_template(self, description, forReview):
        banner_html = f"""<div class='review-wrap' style='display: flex;flex-wrap:wrap;'>"""
        banner_html = description + banner_html
        i = 1
        for index, pd in enumerate(forReview):
            # 리뷰 내용이 없는 것은 제외..
            if self.USE_COUPANG_REVIEW:
                try:
                    if not pd['review_article']:
                        continue
                except Exception as e:
                    continue
        
            # 원본 HTML 문자열
            link = pd['url']
            thumbnail = pd['thumbnail']
            name = pd['name'].replace('…','')
            origin_price = float(pd['origin_price'])
            sale_price = float(pd['sale_price'])
            review_count = pd['count']
            rating = pd['rating']
            nth = str(i)
            if i == 1:
                # 첫번째 상품 이미지를 로컬에 저장합니다.
                self.save_image(thumbnail)
            try:
                if self.USE_SHORT_URL == 'True':
                    link = self.short(link)
                else:
                    link = pd['url']
            except Exception as e:
                link = pd['url']
                print(str(e))
            
            # 배너 생성 시 이미지 사용 여부 확인
            if self.USE_COUPANG_IMAGE:
                image_tag = f"<img src='{pd['thumbnail']}' alt='{pd['name']}' class='product-image' style='max-width: 100%;height: auto;margin:0 auto'>"
            else:
                image_tag = ""  # 이미지 미사용 시 빈 문자열

            # 리뷰 사용 여부 결정
            if self.USE_COUPANG_REVIEW and pd['review_article']:
                if self.USE_COUPANG_AI_REVIEW:
                    # GPT 기반 요약을 생성
                    review_content = self.openai.get_gpt_summary(pd['review_article'])
                else:
                    review_content = pd['review_article']
            else:
                review_content = "<p style='width:100%;text-align:center'>상세 리뷰 내용은 제공되지 않습니다.</p>"
            
            # rating 은 0~5 사이의 소수점 값을 가짐
            # 별점의 width 값을 퍼센트로 계산 (5점 만점)
            width = (float(rating) / 5) * 100

            # rating_container에 별점 부분 채워진 이미지를 표현
            if rating == 0:
                rating_container = ''
                rating_message = ''
            else:    
                rounded_rating = round(rating)  # 반올림 처리
                full_stars = '★' * rounded_rating
                empty_stars = '☆' * (5 - rounded_rating)
                stars_html = f'<div style="font-size:20px; color:gold; text-align:center">{full_stars}{empty_stars}</div>'

                rating_container = f"""
                <div>
                    {stars_html}
                </div>
                <span style="margin:0 auto">리뷰 점수 {rating} 점</span>
                """
                rating_message = f"<b>{rating}</b>"
            if self.TEMPLATE_NAME == 'random':
                self.TEMPLATE_NAME = self.load_random_template_content()
            banner_html += self.load_template(self.TEMPLATE_NAME).format(
                nth=nth, name=name, link=link, image_tag=image_tag,
                origin_price=origin_price, sale_price=sale_price,
                review_count=review_count, rating=rating,
                rating_container=rating_container, rating_message=rating_message, review_content=review_content
            )  
            i += 1
            time.sleep(1)
        banner_html += "</div><div style='color:#a9a9a9'>이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</div>"  
        return banner_html
    
    def get_naver_shopping_trends(self, driver: webdriver.Chrome, search_keyword: str | None = None) -> list:
        '''
        이 함수는 기본적으로 네이버 베스트 쇼핑 키워드와 datalab의 카테고리별 인기 검색 키워드를 자동으로 가져오는 함수입니다. 아래 코드중 naver_shopping_list 에 넣는 키워드를 아래와 같이 양식만 맞추어 배열에 넣어준다면, 수동으로 작성하는 것도 가능합니다. 
            
        keyword = {
                    "from": 'naver',
                    "date": datetime.datetime.now(),
                    "name": name
        }
        
        naver_shopping_list.append(keyword)
        '''

        naver_shopping_list = []
    
        #특정 키워드가 있다면, 데이터 랩에서 검색
        if search_keyword is not None:
            url = "https://datalab.naver.com/"
            driver.get(url)
            # 카테고리 select box element가 존재하는지 확인
            select_box = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.select.depth._dropdown'))
            )
            # 카테고리 select box 옵션
            options = select_box.find_elements(By.CSS_SELECTOR, '.select_list.scroll_cst li')
            # select box의 카테고리 중 입력한 카테고리와 일치하는지 확인하여 해당 카테고리를 선택하기 위함 
            for option in options:
                a = option.find_element(By.CSS_SELECTOR, 'a')
                name = driver.execute_script('return arguments[0].innerHTML;',a)
                # 카테고리와 일치한다면 해당 카테고리를 클릭
                if name == search_keyword:
                    driver.execute_script('return arguments[0].click();',a)
                    driver.execute_script('return arguments[0].click();',a)
                    break
            time.sleep(5)
            keyword_list = driver.find_elements(By.CSS_SELECTOR, '.rank_scroll')
            # 카테고리별 검색 키워드를 가져옴
            titles = keyword_list[len(keyword_list) - 1].find_elements(By.CSS_SELECTOR, '.title')
            # 검색 키워드 별로 배열에 넣기 좋게 데이터를 가공함
            for li in titles:
                if li.text != '':
                    print(li.text)
                    keyword = {
                        "from": 'naver',
                        "date": datetime.datetime.now(),
                        "name": li.text
                    }
                    naver_shopping_list.append(keyword)
                else:
                    name = driver.execute_script('return arguments[0].textContent;', li)
                    keyword = {
                        "from": 'naver',
                        "date": datetime.datetime.now(),
                        "name": name
                    }
                    naver_shopping_list.append(keyword)
        else: 
            # 키워드를 선택하지 않았다면 아래의 인기 검색어 20개를 가져온다.    
            driver.get(url='https://snxbest.naver.com/keyword/best?categoryId=A&sortType=KEYWORD_POPULAR')
          
            keyword_list = driver.find_elements(By.XPATH, "/html/body/div/div[3]/div[2]/div/div[2]/ul/li")
            # 인기 상품 검색어를 가공하여 배열에 넣음
            for li in keyword_list:
          
                rank = li.find_elements(By.TAG_NAME, 'span')[0]
                product = rank.find_elements(By.TAG_NAME, 'strong')[1].text
       
                name = product.strip()
                # 배열에 넣을 데이터 양식
                keyword = {
                    "from": 'naver',
                    "date": datetime.datetime.now(),
                    "name": name
                }
                naver_shopping_list.append(keyword)
        return naver_shopping_list
    def coupang_login(self, driver: webdriver.Chrome):
        try:
            time.sleep(1)
            #쿠팡파트너스 사이트 입장 
            driver.get('https://partners.coupang.com/')
    
            # 쿠팡의 Selenium을 감지하기 위한 코드 무력화
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """ Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) """})
            # 페이지에서 로그인 버튼이 나타나길 기다림..
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, 'login-signup button:first-child'))
            )
            driver.execute_script("arguments[0].click();", login_btn)
            # 아이디 패스워드가 나타나길 기다림..
            time.sleep(3)
            pass_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'login-password-input'))
            )
            
            # 아이디와 비번의 경우 copy paste 로 입력. captcha가 뜨는 것을 방지. 
            # 쿠팡 비번을 복사
            # pyperclip.copy(dotenv.get_key('blogger.env','COUPANG_PASSWORD'))
        
            # actions = ActionChains(driver)
            # actions.move_to_element(pass_field)
            # actions.click()
            # # 비번 input 창에 붙여넣음
            # actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            # # 아이디도 마찬가지로 copy -> paste
            id_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'login-email-input'))
            )
        
            # pyperclip.copy(dotenv.get_key('blogger.env','COUPANG_USERNAME'))
            # actions = ActionChains(driver)
            # actions.move_to_element(id_field)
    
            # actions.click()
            # actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

            id_field.send_keys(self.COUPANG_USERNAME) # selenium의 일반적인 아이디 입력
            pass_field.send_keys(self.COUPANG_PASSWORD) # selenium의 일반적인 비번입력
            keep_login = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.member__checkbox__label'))
            )
            keep_login.click()
            # 로그인 버튼을 찾아서 로그인
            login_submit = WebDriverWait(driver, 10).until( 
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.login__button.login__button--submit._loginSubmitButton.login__button--submit-rds'))
            )
            time.sleep(1)
            login_submit.click()
        except NoSuchElementException:
            print('페이지의 HTML 구조가 변경 된 것 같습니다. 확인이 필요합니다.')
            exit(1)
            
    def get_coupang_partners(self, driver: webdriver.Chrome, naver_shopping_list: list | None = None, manual_keyword: str | None = None) -> list:
        '''
        쿠팡 파트너의 상품을 네이버 인기 쇼핑 키워드를 사용하거나 수동으로 입력받은 키워드를 사용하여 검색합니다. 
        '''
        product_details = []
        user_agent = driver.execute_script("return navigator.userAgent;")
          # 검색 페이지 
        if self.USE_ROCKET_SHIPPING == 'True':
            rocket = '"ROCKET"'
        else:
            rocket = ''
        cookie_file_path = f"cookies_coupang.pkl"
        if naver_shopping_list is not None and len(naver_shopping_list) > 0:
            if self.KEEP_COUPANG_LOGIN == 'True' and os.path.exists(cookie_file_path):
                driver.get('https://login.coupang.com/login/login.pang')
                # 쿠키 파일이 존재하면 쿠키를 로드
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """ Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) """})
                cookies = pickle.load(open(cookie_file_path, "rb"))
                for cookie in cookies:
                    driver.add_cookie(cookie)
                print(f'쿠팡 로그인 쿠키 로드 (파일: {cookie_file_path})')
                driver.get('https://partners.coupang.com/')
                time.sleep(1)
                driver.refresh()
               
            else:
                self.coupang_login(driver)
                time.sleep(1)  
                pickle.dump(driver.get_cookies(), open(cookie_file_path, "wb"))
                print(f'쿠팡 로그인 쿠키 저장 (파일: {cookie_file_path})')
                
          
            # 네이버 쇼핑 키워드를 기반으로 상품 정보를 검색
            for product_info in naver_shopping_list:
                driver.implicitly_wait(3) 
                # 쿠팡 파트너스의 검색창을 찾음
                search_input = WebDriverWait(driver,10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '.ant-input.ant-input-lg'))
                )
             
                # 상품을 우선 가져온다
                search_script = f"""
                    return await fetch('https://partners.coupang.com/api/v1/search', {{
                        method: 'POST', 
                        headers: {{
                            'User-Agent': '{user_agent}',
                            'Accept':'application/json',
                            'Content-Type':'application/json;charset=UTF-8'
                        }},
                        body: JSON.stringify({{
                            "page": {{"pageNumber":0, "size":72}},
                            "filter": "{product_info['name']}",
                            "deliveryTypes": [{rocket}] 
                        }})
                    }}).then(r => r.json());
                """
                json_search_data = driver.execute_script(search_script)
                x_token = None
                cookies = driver.get_cookies()
                x_token = next((cookie['value'] for cookie in cookies if cookie['name'] == 'AFATK'), None)
                if x_token:
                    with open('cookies_x_token.pkl', 'wb') as f:
                        pickle.dump(x_token, f)
                else:
                    if self.KEEP_COUPANG_LOGIN == 'True' and os.path.exists('cookies_x_token.pkl'):
                        with open('cookies_x_token.pkl', 'rb') as f:
                            x_token = pickle.load(f)
                            cookie = {}
                            cookie['name'] = 'AFATK'
                            cookie['value'] = x_token
                            cookie['domain'] = '.coupang.com'
                            cookie['path'] = '/'
                            cookie['expires'] = 0
                            driver.add_cookie(cookie)
                    else:
                        print('xtoken 없음')
        
                print('상품 검색중...')
            
                if json_search_data['data'] and json_search_data['data']['products']:
                    i = 0
                    for search_data in json_search_data['data']['products']:
                        if i == 1:
                            break
                         # 금지어 리스트로 분리
                        banned_words = [word.strip() for word in self.BANNED_WORDS.split(',')]
                        if self.USE_EXACT_SEARCH_MATCHING == 'True':
                            thresold = fuzz.partial_ratio(product_info['name'], search_data['title'])
                            if thresold < 65:
                                continue
                        if any(banned_word in product_info['name'] for banned_word in banned_words):
                            continue        
                        itemId = search_data['itemId']
                        productId = search_data['productId']
                        vendorItemId = search_data['vendorItemId']
                        image = search_data['image']
                        title = search_data['title']
                        # discountRate = search_data['discountRate']
                        originPrice = search_data['originPrice']
                        salesPrice = search_data['salesPrice']
                
                        url_script = f"""
                            return fetch('https://partners.coupang.com/api/v1/banner/iframe/url', {{
                                method: 'POST',
                                headers: {{
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json;charset=UTF-8',
                                    'X-Token': '{x_token}',
                                    'X-Sub-Id': '{self.selected_ch_id}'
                                }},
                                body: JSON.stringify({{
                                    "product": {{
                                        "type": "PRODUCT",
                                        "itemId": {itemId},
                                        "productId": {productId},
                                        "vendorItemId": {vendorItemId},
                                        "image": "{image}",
                                        "title": "{title}",
                                        "originPrice": {originPrice},
                                        "salesPrice": {salesPrice}
                                    }}
                                }})
                            }}).then(r => r.json());
                            """
                        url_data = driver.execute_script(url_script)
                        if url_data['data'] and url_data['data']['shortUrl']:
                            product_detail = {
                                "thumbnail": image.replace('212x212','500x500'), 
                                "name": title,
                                "url": url_data['data']['shortUrl'],
                                "search_keyword": product_info['name'],
                                "itemId": itemId,
                                "productId": productId,
                                "vendorItemId": vendorItemId,
                                "originPrice": originPrice,
                                "salesPrice": salesPrice
                            }
                            print('현재 제품:'+ product_detail['name']+ '\n' + '링크:' + product_detail['url'])
                            product_details.append(product_detail)
                            time.sleep(1)
                        i += 1
            return product_details
        elif manual_keyword is not None:
            if self.KEEP_COUPANG_LOGIN == 'True' and os.path.exists(cookie_file_path):
                driver.get('https://login.coupang.com/login/login.pang')
                # 쿠키 파일이 존재하면 쿠키를 로드
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """ Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) """})
                cookies = pickle.load(open(cookie_file_path, "rb"))
                for cookie in cookies:
                    driver.add_cookie(cookie)
                print(f'쿠팡 로그인 쿠키 로드 (파일: {cookie_file_path})')
                driver.get('https://partners.coupang.com/')
                time.sleep(1)
                driver.refresh()
               
            else:
                self.coupang_login(driver)
                time.sleep(1) 
                pickle.dump(driver.get_cookies(), open(cookie_file_path, "wb"))
                print(f'쿠팡 로그인 쿠키 저장 (파일: {cookie_file_path})')
            try:
                # 쿠팡 파트너스의 검색창을 찾음
                search_input = WebDriverWait(driver,10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '.ant-input.ant-input-lg'))
                )
                search_script = f"""
                    return await fetch('https://partners.coupang.com/api/v1/search', {{
                        method: 'POST', 
                        headers: {{
                            'User-Agent': '{user_agent}',
                            'Accept':'application/json',
                            'Content-Type':'application/json;charset=UTF-8'
                        }},
                        body: JSON.stringify({{
                            "page": {{"pageNumber":0, "size":72}},
                            "filter": "{manual_keyword}",
                            "deliveryTypes": [{rocket}]
                        }})
                    }}).then(r => r.json());
                """
                json_search_data = driver.execute_script(search_script)
                x_token = None
                cookies = driver.get_cookies()
                x_token = next((cookie['value'] for cookie in cookies if cookie['name'] == 'AFATK'), None)
                if x_token:
                    with open('cookies_x_token.pkl', 'wb') as f:
                        pickle.dump(x_token, f)
                else:
                    if self.KEEP_COUPANG_LOGIN == 'True' and os.path.exists('cookies_x_token.pkl'):
                        with open('cookies_x_token.pkl', 'rb') as f:
                            x_token = pickle.load(f)
                            cookie = {}
                            cookie['name'] = 'AFATK'
                            cookie['value'] = x_token
                            cookie['domain'] = '.coupang.com'
                            cookie['path'] = '/'
                            cookie['expires'] = 0
                            driver.add_cookie(cookie)
                            print('xtoken 쿠키 생성 완료')
                    else:
                        print('xtoken 없음')
                print('상품 검색중...')
                product_limit = int(self.COUPANG_PRODUCT_LIMIT)
                if json_search_data['data'] and json_search_data['data']['products']:
                    i = 0
                    for search_data in json_search_data['data']['products']:
                        if self.USE_EXACT_SEARCH_MATCHING == 'True':
                            thresold = fuzz.partial_ratio(manual_keyword, search_data['title'])
                            if thresold < 65:
                                continue 
                        if (i == product_limit and self.use_coupang_link_config is False):
                            break
                        itemId = search_data['itemId']
                        productId = search_data['productId']
                        vendorItemId = search_data['vendorItemId']
                        image = search_data['image']
                        title = search_data['title']
                        # discountRate = search_data['discountRate']
                        originPrice = search_data['originPrice']
                        salesPrice = search_data['salesPrice']
                
                        url_script = f"""
                            return fetch('https://partners.coupang.com/api/v1/banner/iframe/url', {{
                                method: 'POST',
                                headers: {{
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json;charset=UTF-8',
                                    'X-Token': '{x_token}',
                                    'X-Sub-Id': '{self.selected_ch_id}'
                                }},
                                body: JSON.stringify({{
                                    "product": {{
                                        "type": "PRODUCT",
                                        "itemId": {itemId},
                                        "productId": {productId},
                                        "vendorItemId": {vendorItemId},
                                        "image": "{image}",
                                        "title": "{title}",
                                        "originPrice": {originPrice},
                                        "salesPrice": {salesPrice}
                                    }}
                                }})
                            }}).then(r => r.json());
                            """
                        print('상품 링크 생성중..')
                        url_data = driver.execute_script(url_script)
                        if url_data['data'] and url_data['data']['shortUrl']:
                            product_detail = {
                                "thumbnail": image.replace('212x212', '500x500'), 
                                "name": title,
                                "url": url_data['data']['shortUrl'],
                                "search_keyword": title.replace(',', '-'),
                                "itemId": itemId,
                                "productId": productId,
                                "vendorItemId": vendorItemId,
                                "originPrice": originPrice,
                                "salesPrice": salesPrice
                            }
                            print('현재 제품:'+ product_detail['name']+ '\n' + '링크:' + product_detail['url'])
                            product_details.append(product_detail)
                            
                            time.sleep(1)
                        i += 1
                
            except Exception as e:
                print("에러: " + str(e))    
            # cookies = driver.get_cookies()  # 모든 쿠키 가져오기

            # for cookie in cookies:
            #     if "coupang" in cookie['domain']:  # 특정 도메인의 쿠키만 삭제
            #         driver.delete_cookie(cookie['name'])  

            return product_details
        
        
        else:
            raise Exception('네이버 데이터 없음')
    def get_coupang_reviews(self, driver, product_id, vendor_item_id):
        url_script = f"""
            return fetch("https://www.coupang.com/vm/products/{product_id}/brand-sdp/reviews/list?vendorItemId={vendor_item_id}", {{
                method: "GET"
            }}).then(response => response.json());
        """
        print("쿠팡 리뷰 데이터 요청 중..브라우저를 끄지 마세요.")
        reviews_data = driver.execute_script(url_script)
        return reviews_data
    '''
    쿠팡에서 위의 쿠팡파트너스 url로 각 제품의 리뷰 정보를 가져옴
    '''
    def get_coupang_products(self, driver: webdriver.Chrome, product_details: list, use_links: bool = False) -> tuple:
        driver.get('https://www.coupang.com/vm/products/8391705721/')
        forReview = []
        total_keywords = []
        if use_links == True:
            if os.path.exists(os.getcwd().replace('\\', '/') + '/product_links.json'):
                        # 파일이 존재할 경우 처리
                try:
                    with open(os.getcwd().replace('\\', '/') + '/product_links.json', 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        product_links = data.get("links", [])
                except json.JSONDecodeError:
                    print('product_links.json 파일안의 데이터가 옳바르지 않습니다.')
                    raise Exception('product_links.json invalid data')
                for link in product_links:
                    driver.get(link.split('?')[0])
                    time.sleep(3)
                    coupang_product = {}
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script("return typeof window.sdp !== 'undefined'")
                    )

                    script = """
                    return window.sdp ? { 
                        productId: window.sdp.productId, 
                        vendorItemId: window.sdp.vendorItemId, 
                        name: window.sdp.itemName, 
                        image: window.sdp.images ? window.sdp.images[0].origin : null, 
                        sale_price: window.sdp.quantityBase && window.sdp.quantityBase[0].moduleData ? window.sdp.quantityBase[0].moduleData[0].detailPriceBundle.finalPrice.bestPriceInfo.price : null, 
                        original_price: window.sdp.quantityBase && window.sdp.quantityBase[0].moduleData ? window.sdp.quantityBase[0].moduleData[0].detailPriceBundle.originalPrice.price : null 
                    } : null;
                    """
                    sdp_data = driver.execute_script(script)
                    print(sdp_data)
                    if sdp_data:
                        product_id = sdp_data.get("productId")
                        vendor_item_id = sdp_data.get("vendorItemId")
                        origin_price = sdp_data.get("original_price")
                        sale_price = sdp_data.get("sale_price")
                        name = sdp_data.get("name")
                        image = 'https:'+sdp_data.get("image")
                        coupang_product['thumbnail'] = image
                        coupang_product['name'] = name
                        coupang_product['url'] = link
                        coupang_product['origin_price'] = origin_price
                        coupang_product['sale_price'] = sale_price
                        print(f"Product ID: {product_id}, Vendor Item ID: {vendor_item_id}")
                        print('리뷰 가져오는중..')
                        review = self.get_coupang_reviews(driver, product_id, vendor_item_id)
                        review_arr = []
                        count = review['ratingCount']
                        rating = review['ratingAverage']
                        if review['reviews'] and len(review['reviews']) > 0:
                            i = 0
                            for rv in review['reviews']:
                                if rv['content']:
                                    i += 1
                                    review_arr.append(rv['content'])
                                    if i == 3:
                                        break
                                    
                        coupang_product['count'] = count
                        coupang_product['rating'] = rating
                        coupang_product['review_article'] = ' '.join(review_arr)       
                        if name not in total_keywords:
                            total_keywords.append(name) 
                    else:
                        print("sdp 데이터가 존재하지 않습니다.")
                      
                    forReview.append(coupang_product)
                    time.sleep(3)
                return (forReview, total_keywords)
            else:
                print('product_links.json 파일이 존재하지 않습니다.')
                raise Exception('product_links.json not exists')
        elif len(product_details) > 0:
        
            
            for coupang_product in product_details:
                time.sleep(random.uniform(1, 3))
                print('리뷰 가져오는중..')
                review = self.get_coupang_reviews(driver, coupang_product['productId'], coupang_product['vendorItemId'])
                review_arr = []
                count = review['ratingCount']
                rating = review['ratingAverage']
                if review['reviews'] and len(review['reviews']) > 0:
                    i = 0
                    for rv in review['reviews']:
                        if rv['content']:
                            i += 1
                            review_arr.append(rv['content'])
                            if i == 3:
                                break
                
                #네이버 쇼핑 트렌드 현재 검색어 출력..
                print(coupang_product['search_keyword'])
                if coupang_product['search_keyword'] not in total_keywords:
                    total_keywords.append(coupang_product['search_keyword'])
                # 쿠팡 가격 추적
                origin_price = coupang_product['originPrice']
                sale_price = coupang_product['salesPrice']
                if int(origin_price) != 0:
                    coupang_product['origin_price'] = origin_price
                else:
                    if int(sale_price) > 0:
                        coupang_product['origin_price'] = sale_price
                        
                if int(sale_price) != 0:
                    coupang_product['sale_price'] = sale_price
               


                coupang_product['count'] = count
                coupang_product['rating'] = rating
                coupang_product['review_article'] = ' '.join(review_arr)
                forReview.append(coupang_product)
                time.sleep(random.uniform(1, 3))
            return (forReview, total_keywords)
        
    def write_coupang_partners(self, driver: webdriver.Chrome, forReview:list, total_keywords: list, keyword: None|str = None):
        if len(forReview) > 0 and len(total_keywords) > 0:
            # 개별생성이 아닌 쿠팡 파트너 배너 모음 생성
            return self.coupang_partners_group_posting(driver, forReview, total_keywords, keyword)
        else:
            raise Exception('수집된 쿠팡 파트너스 상품이 없습니다.')
            
    def coupang_partners_group_posting(self, driver:webdriver.Chrome, forReview:list, total_keywords: list, keyword: None|str = None):
        today = datetime.date.today().strftime('%Y년 %m월 %d일')
        total_keywords_str = ', '.join(total_keywords)
        
        if keyword is not None:
            if self.use_naver is False:
                if self.USE_GPT_POST_DESCRIPTION == 'True':
                    # GPT를 사용하여 제품 설명을 생성
                    description = self.openai.get_product_description(keyword)
                    description += "<div style='color:#f29766;text-align:center;width:100%;'>이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</div>"
                else:
                    description = self.load_template('description_coupang').format(keyword=keyword) 
                if self.USE_COUPANG_AI_GUIDE:
                    guide = self.openai.get_product_guide(keyword)
                    description += f"<div class='guide' style='margin-bottom:30px;text-align:center'><h2>제품 선택 가이드</h2><div style='width:100%;text-align:left'>{guide}</div>"
            else:
                description = self.load_template('description_naver_category').format(keyword=keyword, total_keywords_str=total_keywords_str)
        else:
            description = self.load_template('description_naver_total').format(today=today, total_keywords_str=total_keywords_str)
        
        i = 1
        for index, pd in enumerate(forReview):
            # 리뷰 내용이 없는 것은 제외..
            if self.USE_COUPANG_REVIEW:
                try:
                    if not pd['review_article']:
                        continue
                except Exception as e:
                    continue
            nth = str(i)
            i += 1
        banner_html = self.get_banner_template(description, forReview)
       
        # 제목 작성 
        if keyword is not None:
            if self.use_naver is True:
                title = keyword+' 부분 인기 검색어:'+ ', '.join(total_keywords)
            else:
                # pre_fix, main, post_fix 구조 정의
                rand_pre_fix = [
                    "오늘의", "리뷰가 좋은", "가성비 좋은", "요즘 핫한", "가장 인기 있는",
                    "많이 찾는", "트렌디한", "후기가 좋은", "평점이 높은", "구매자들이 극찬한",
                    "믿고 보는", "가성비 최고", "품질 좋은", "사용자가 강력 추천하는", "지금 꼭 사야 할",
                    "놓치면 후회할", "실용적인",
                ]

                rand_post_fix = [
                    "추천 상품 TOP {nth}", "추천 상품 BEST {nth}", "추천 상품 {nth}", "추천 제품 {nth} 선", "인기 상품 탑 {nth}", "인기 상품 TOP {nth}", "베스트 셀러 탑 {nth}", "베스트 셀러 TOP {nth}"
                ]
                pre_fix = random.choice(rand_pre_fix)
                main_keyword = keyword
                post_fix = random.choice(rand_post_fix).replace('{nth}', str(nth))
                if self.USE_GPT_POST_TITLE == 'True':
                    full_title = self.openai.get_post_title(keyword, nth)
                else:
                    full_title = " ".join([pre_fix, main_keyword, post_fix]).strip()
                if  self.USE_CUSTOM_TITLE_BANNER == 'True':
                    html_content = self.load_template(self.TITLE_BANNER_TEMPLATE_NAME, 'title_banner').replace("{pre_fix}", pre_fix).replace("{main}", main_keyword).replace("{post_fix}", post_fix)
                    script = (
                        "var popup = window.open('', 'popup', 'width=500,height=500');"
                        "popup.document.write(`{}`);"
                        "popup.document.close();"
                    ).format(html_content.replace("`", "\\`"))  # HTML의 backtick(`) 이슈 방지
                    driver.execute_script(script)
                    
                    # Selenium으로 팝업 제어
                    driver.switch_to.window(driver.window_handles[-1])  # 새로 열린 창으로 전환
                    time.sleep(2)  # 팝업 렌더링 대기

                    # 배너 영역 캡처
                    banner = driver.find_element(By.TAG_NAME, "body")
                    random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    self.image_filename = f"today_shopping_title_{random_string}.png"
                    banner.screenshot(self.image_filename)

                    print(f"배너 이미지가 저장되었습니다: {self.image_filename}")

                    # 팝업 창 닫기
                    driver.close()

                    # 원래 창으로 돌아가기
                    driver.switch_to.window(driver.window_handles[0])
                title = full_title
        else:
            title = '오늘의 쇼핑 트렌드 검색어:'+', '.join(total_keywords)



       
        # 태그 작성
        tags = ','.join(total_keywords)
     
       
        
       
        # file_box.send_keys(os.getcwd().replace('\\', '/')+'/'+self.image_filename)
        content = banner_html
        return (title, tags, content)
        
    def write_blog(self, data:dict):
        if data is not None:
            title = data['title']
            content = data['content']
            tags = data['tags']
            if self.USE_GPT_IMAGE_CREATION == 'True':
                # file_box.send_keys(os.getcwd().replace('\\', '/')+'/'+data['img'])
                pass
            print('프로그램 종료시에는 반드시 이 터미널이 아닌 윈도우 프로그램창을 종료해주세요. ')
            return (title, tags, content)
    
    def process_auto_blogger(self, mode:str|None = None):
         # 1. Authenticate
        if not self.is_authenticated():
            logging.info("Not authenticated, attempting authentication...")
            if not self.authenticate():
                raise ConnectionError("Blogger authentication failed. Please check logs and configuration.")
        logging.info("Blogger client authenticated successfully.")
        if self.USE_SEARCH_CONSOLE == 'True':
            self.search_console = SearchConsoleIndexer()
            self.search_console.authenticate()
            logging.info("Search Console client authenticated successfully.")
        # 2. Get settings from MenuGUI
        blog_id = self.gui.selected_blogger_blog_id
        keywords = self.gui.keywords

        if not blog_id:
             raise ValueError("Target Blogger Blog ID not selected in the GUI.")
        if not keywords and mode != '1': # Keywords might not be needed for Coupang if using different logic
            # Adjust this condition based on your actual needs
             raise ValueError("Keywords not provided in the GUI for blog post mode.")
        keyword = None
     
        if mode == '1':  # 쿠파스 작성
            if self.gui.use_naver:  # 네이버 인기 검색어 사용
                keyword = None if self.gui.selected_naver_category == '전체' else self.gui.selected_naver_category
            else:
                if self.use_coupang_link_config:
                    print('product_links.json 설정 파일을 사용하여 링크를 대체합니다.')
                else:
                    keyword = self.gui.keywords  # 수동으로 입력한 쿠팡 파트너스 키워드
                    keyword = keyword.strip() if keyword is not None else keyword
                    if ',' in keyword:
                        keywords = keyword.split(',')
                        if len(keywords) > 1:
                            self.multiple_post = True
        else:  # 블로그 작성 모드
            keyword = self.gui.keywords
            keyword = keyword.strip() if keyword is not None else keyword
            if ',' in keyword:
                keywords = keyword.split(',')
                if len(keywords) > 1:
                    self.multiple_post = True
            
        if self.multiple_post is False and mode != 2:
            driver = self.setChromium() 
    
        if mode == '2':
            print('GPT 블로그 작성을 시작합니다.')
            openAiWrapper = OpenAIWrapper()
            if self.multiple_post is True:
                for keyword in keywords:
                    print('다중 키워드 입력 작업중 현재 키워드:' + keyword)
                    res = openAiWrapper.get_gpt_blog(keyword)
                    (title, tags, content) = self.write_blog(res)
                    self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
                    time.sleep(random.uniform(10, 20))
            else:
                res = openAiWrapper.get_gpt_blog(keyword)
                (title, tags, content) = self.write_blog(res)
                self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
          
        else:
            print(f"쿠팡 파트너스 블로그 작성을 시작합니다. 사용 템플릿: {self.TEMPLATE_NAME}" )
            if self.USE_COUPANG_REVIEW:
                if self.USE_COUPANG_AI_REVIEW:
                    print('리뷰 내용이 GPT 요약으로 대체됩니다.')
                else:
                    print('리뷰 내용이 기존 대로 나옵니다. 쿠팡 파트너스 저작권에 걸릴 수 있으니, 내용을 수정해 주시거나 편집해주세요.')
            else:
                print('쿠팡 파트너스의 저작권을 침해하지 않기 위해 리뷰 내용을 게시하지 않습니다.')
            if self.use_coupang_link_config:
                driver.close()
                driver = self.getUndetectedChrome()
                (forReview, total_keywords) = self.get_coupang_products(driver, product_details=[], use_links=True)
                driver.close()
                (title, tags, content) =self.write_coupang_partners(driver, forReview, total_keywords, keyword)
                self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
            
            else:
                if self.use_naver:
                    # 네이버 https://datalab.naver.com/ 의 검색 당일자 인기 제품 20개 카테고리 선택시 10개를 가져옵니다. 
                    naver_shopping_trends = self.get_naver_shopping_trends(driver, keyword)
                    product_details = self.get_coupang_partners(driver,naver_shopping_trends)
                    try:
                        (forReview, total_keywords) = self.get_coupang_products(driver, product_details)
                    except TypeError as e:
                        if 'cannot unpack non-iterable' in str(e):
                            driver.close()
                            raise Exception('검색 결과 없음: '+ keyword)
                    (title, tags, content) = self.write_coupang_partners(driver, forReview, total_keywords, keyword)
                    self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
                    
                else:
                    naver_shopping_trends = None
                    if self.multiple_post is True:
                        for keyword in keywords:
                            print('다중 키워드 입력 작업중 현재 키워드:' + keyword)
                            driver = self.setChromium()
                            keyword = keyword.strip()
                            product_details = self.get_coupang_partners(driver, naver_shopping_trends, keyword)
                            try:
                                (forReview, total_keywords) = self.get_coupang_products(driver, product_details)
                            except TypeError as e:
                                if 'cannot unpack non-iterable' in str(e):
                                    print('검색 결과 없음: '+ keyword)
                                    self.search_fail.append(keyword)
                                    driver.close()
                                    time.sleep(random.uniform(1, 3))
                                    continue
                            (title, tags, content) = self.write_coupang_partners(driver, forReview, total_keywords, keyword)
                            driver.close()
                            if self.is_random:
                                self.TEMPLATE_NAME = 'random'
                            self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
                            time.sleep(random.uniform(10, 20))
                    else:        
                        product_details = self.get_coupang_partners(driver,naver_shopping_trends, keyword)
                        try:
                            (forReview, total_keywords) = self.get_coupang_products(driver, product_details)
                        except TypeError as e:
                            if 'cannot unpack non-iterable' in str(e):
                                driver.close()
                                raise Exception('검색 결과 없음: '+ keyword)
                        time.sleep(random.uniform(1, 3))
                        (title, tags, content) = self.write_coupang_partners(driver, forReview, total_keywords, keyword)
                        driver.close()
                        self.send_blogger_api(title, content, self.gui.selected_blogger_blog_id)
            if len(self.search_fail) > 0:
                print("검색 결과 조회 실패 검색어: "+', '.join(self.search_fail))
            print('프로그램 종료시에는 반드시 이 터미널이 아닌 윈도우 프로그램창을 종료해주세요. ')
            return True

    def create_poster_image(self, driver, forReview):
        i = 1
        for index, pd in enumerate(forReview):
            # 리뷰 내용이 없는 것은 제외..
            if self.USE_COUPANG_REVIEW:
                try:
                    if not pd['review_article']:
                        continue
                except Exception as e:
                    continue
            nth = str(i)
            i += 1

