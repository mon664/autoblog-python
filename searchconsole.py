import os
import json
import logging
import time
import random
import dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configuration ---
URL_FILE = 'index.json'
ENV_FILE = 'searchconsole.env'

# --- Load Environment Variables ---
dotenv.load_dotenv(dotenv_path=ENV_FILE)
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH')

# --- Logging Setup ---
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format,
                    handlers=[logging.FileHandler("index_submitter.log", encoding='utf-8'),
                              logging.StreamHandler()])

# --- Constants ---
INDEXING_API_SCOPE = ['https://www.googleapis.com/auth/indexing']
API_SERVICE_NAME = 'indexing'
API_VERSION = 'v3'
# API 호출 사이의 딜레이 (초) - 속도 제한 방지
DELAY_BETWEEN_REQUESTS = (1.5, 3.0) # 최소 1.5초, 최대 3.0초 랜덤 딜레이

class SearchConsoleIndexer:
    """
    Handles authentication using a Service Account and submits URLs
    to the Google Indexing API.
    """
    def __init__(self):
        self.credentials = None
        self.service = None

    def authenticate(self) -> bool:
        """Authenticates using the service account file."""
        logging.info("서비스 계정 인증을 시작합니다..")
        if not SERVICE_ACCOUNT_FILE:
            logging.error("서비스 계정이 설정되어 있지 않습니다. searchconsole.env (GOOGLE_SERVICE_ACCOUNT_PATH).")
            return False
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            logging.error(f"서비스 계정 json 파일이 존재하지 않습니다.: {SERVICE_ACCOUNT_FILE}")
            return False

        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=INDEXING_API_SCOPE)
            self.service = build(API_SERVICE_NAME, API_VERSION, credentials=self.credentials, cache_discovery=False)
            logging.info("인증에 성공하였습니다.")
            return True
        except Exception as e:
            logging.exception("인증에 실패하였습니다다.")
            self.credentials = None
            self.service = None
            return False

    def read_urls(self) -> list | None:
        """Reads the list of URLs from the JSON file."""
        logging.info(f"URL 을 읽습니다.: {URL_FILE}")
        if not os.path.exists(URL_FILE):
            logging.error(f"URL file not found: {URL_FILE}")
            return None
        try:
            with open(URL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            urls = data.get('urls')
            if urls is None:
                logging.error(f"'urls' 키가 존재하지 않습니다.: {URL_FILE}.")
                return None
            if not isinstance(urls, list):
                logging.error(f"'urls' 키가 존재하지 않습니다.: {URL_FILE}")
                return None
            logging.info(f"{len(urls)}개의의 URL 을 발견하였습니다.")
            return urls
        except json.JSONDecodeError:
            logging.error(f"파일의 포맷이 잘 못 되었습니다: {URL_FILE}.")
            return None
        except Exception as e:
            logging.exception(f"파일을 읽는데 실패하였습니다다: {URL_FILE}")
            return None

    def request_indexing(self, url: str) -> bool:
        """Submits a single URL for indexing."""
        if not self.service:
            logging.error("Indexing service is not available. Cannot request indexing.")
            return False

        content = {
            'url': url,
            'type': 'URL_UPDATED'  # Or 'URL_DELETED' if needed
        }
        logging.info(f"Submitting URL: {url}")
        try:
            response = self.service.urlNotifications().publish(body=content).execute()
            logging.info(f"API 응답 {url}: {response}")
            # 간단히 성공/실패만 반환 (응답 내용에 따라 더 상세한 확인 가능)
            return True
        except HttpError as error:
            status = error.resp.status
            reason = error.reason
            details = '(No details)'
            try:
                details = error.content.decode()
            except Exception:
                pass
            logging.error(f"API Error for {url}: Status {status} {reason}, Details: {details}")
            if status == 403:
                logging.error("Permission Denied (403). Ensure the service account has 'Owner' permission in Search Console for the property containing this URL. 권한이 없습니다. 서비스 계정이 Search Console에서 이 URL을 포함하는 속성에 대해 '소유자' 권한을 가지고 있는지 확인하세요.")
            elif status == 429:
                logging.error("Quota Exceeded (429). Too many requests. Try again later or check quotas in Google Cloud Console. 너무 많은 요청을 하였습니다. 요청은 하루 200개 제한되어 있습니다.")
            # 다른 오류 처리 추가 가능
            return False
        except Exception as e:
            logging.exception(f"Unexpected error submitting URL {url}.")
            return False

    def process_urls(self, urls: list) -> None:
        """Processes the list of URLs, submitting each for indexing with delays."""
        if not urls:
            logging.info("URL 이 비어있습니다.")
            return

        total_urls = len(urls)
        success_count = 0
        failure_count = 0

        logging.info(f"--- URL 등록을 시작합니다. (Total: {total_urls}) ---")

        for i, url in enumerate(urls):
            if not url or not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                logging.warning(f"잘못된 URL: {url}")
                failure_count += 1
                continue

            if self.request_indexing(url):
                success_count += 1
            else:
                failure_count += 1

            # 마지막 URL이 아니면 딜레이 추가
            if i < total_urls - 1:
                delay = random.uniform(DELAY_BETWEEN_REQUESTS[0], DELAY_BETWEEN_REQUESTS[1])
                logging.info(f"다음 응답까지 {delay:.2f} 초...")
                time.sleep(delay)

        logging.info(f"--- URL 등록 끝 ---")
        logging.info(f"전체 URL : {total_urls}")
        logging.info(f"등록 성공 : {success_count}")
        logging.info(f"등록 실패: {failure_count}")

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("========================================")
    logging.info(" Google Search Console Index 등록기기 ")
    logging.info("========================================")

    indexer = SearchConsoleIndexer()

    if indexer.authenticate():
        url_list = indexer.read_urls()
        if url_list is not None: # read_urls가 빈 리스트 [] 를 반환할 수도 있음
            indexer.process_urls(url_list)
        else:
            logging.error("Could not read URLs from file. Exiting.")
    else:
        logging.error("Authentication failed. Exiting.")

    logging.info("Script finished.")