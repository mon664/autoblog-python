import os
import sys
import time
import urllib.request
import json
import pandas as pd
import random
import requests
import datetime
import hashlib
import hmac
import base64
from dotenv import get_key
from tqdm import tqdm

'''
Naver 검색 API 연동을 위한 클래스와 함수
'''
class Signature:
    @staticmethod
    def generate(timestamp, method, uri, secret_key):
        message = "{}.{}.{}".format(timestamp, method, uri)
        hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)

        hash.hexdigest()
        return base64.b64encode(hash.digest())

def get_request_header(method, uri):
    # 네이버 검색 광고 API Secrent key
    SECRET_KEY = get_key('.env', 'NAVER_SEARCH_SECRET')
    # 네이버 검색 광고 Customer ID
    CUSTOMER_ID = get_key('.env', 'CUSTOMER_ID')
    # 네이버 검색 광고 API Key
    API_KEY = get_key('.env', 'NAVER_SEARCH_KEY')
    timestamp = str(round(time.time() * 1000))
    # 네이버 인증을 위한 Signatuer 생성 
    signature = Signature.generate(timestamp, method, uri, SECRET_KEY)
    return {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': API_KEY,
        'X-Customer': str(CUSTOMER_ID),
        'X-Signature': signature
    }

class KeywordGenerator:
    _list: list = []
    def __init__(self):
        pass
    # 키워드 조사
    def getKeywords(self, keywords:list[str])->pd.DataFrame:        
        BASE_URL = 'https://api.naver.com'
        result = pd.DataFrame()
        # 네이버 검색 광고 키워드 도구의 API 를 사용하여 입력된 검색어의 연관 검색어를 조회
        for keyword in keywords:
            uri = '/keywordstool'
            method = 'GET'
            r = requests.get(
                BASE_URL + uri,
                params={'hintKeywords': keyword, 'showDetail': 1},
                headers=get_request_header(method, uri)
            )

            # keyword analysis process
            try:
                df = pd.DataFrame(r.json()['keywordList'])
                df['monthlyMobileQcCnt'] = df['monthlyMobileQcCnt'].apply(lambda x: int(str(x).replace('<', '').strip()))
                df['monthlyPcQcCnt'] = df['monthlyPcQcCnt'].apply(lambda x: int(str(x).replace('<', '').strip()))
                df = df[(df['monthlyMobileQcCnt'] >= 50) & (df['monthlyPcQcCnt'] >= 50)]
                df.rename(
                    {'compIdx': '경쟁정도',
                    'monthlyMobileQcCnt': '월간검색수_모바일',
                    'monthlyPcQcCnt': '월간검색수_PC',
                    'relKeyword': '연관키워드'},
                    axis=1,
                    inplace=True
                )
                df = df[['연관키워드', '월간검색수_PC', '월간검색수_모바일', '경쟁정도']]
                df['총검색수'] = df['월간검색수_PC'] + df['월간검색수_모바일']
                df = df.sort_values('총검색수', ascending=False)
                # self.tmp_df = pd.concat([self.tmp_df, df], axis=0)
                print(df)
                if df.size > 0:
                    # 네이버 검색 API를 활용하여 연관된 검색어를 좀 더 조사
                    result = self.getRelatedKeywords(df)
                    self._list.append({'keyword': keyword, 'df': result})
                else:
                    continue
                time.sleep(1)
            except Exception as e:
                print(str(e))
            # 입력된 키워드를 엑셀파일로 구성
            for detail in self._list:
                detail['df'].to_excel(os.getcwd().replace('\\', '/')+'/keywords/'+f'{keywords}.xlsx',sheet_name=detail['keyword'], index=False)
            
        return True
    # 네이버 검색 API로 연관 키워드를 더 조사하는 함수
    def getRelatedKeywords(self, df: pd.DataFrame)->pd.DataFrame:
        total_docs = []
        if not df.empty:
            # 네이버 검색 API 클라이언트 ID
            client_id = get_key('.env', 'NAVER_CLIENT_ID')
            # 네이버 검색 API 클라이언트 Secret 
            client_secret = get_key('.env','NAVER_CLIENT_SECRET')
            # '연관키워드' 개수 출력
            print("연관키워드 개수:", len(df['연관키워드']))
            for word in tqdm(df['연관키워드']):
                encText = urllib.parse.quote(word)
                url = "https://openapi.naver.com/v1/search/webkr.json?query=" + encText
                request = urllib.request.Request(url)
                request.add_header("X-Naver-Client-Id", client_id)
                request.add_header("X-Naver-Client-Secret", client_secret)
                response = urllib.request.urlopen(request)
                rescode = response.getcode()

                try:
                    if(rescode==200):
                        response_body = response.read()
                        text = response_body.decode('utf-8')

                        total_docs.append(json.loads(text)['total'])
                    else:
                        print("Error Code:" + rescode)
                except:
                    total_docs.append(0)
                time.sleep(1)

            df['총문서수'] = total_docs
            df['경쟁정도_ratio'] = round(df['총문서수'] / df['총검색수'],2)
            df.sort_values('경쟁정도_ratio', ascending=True)
          
        return df

