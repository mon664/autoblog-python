import queue
import os
import base64
import dotenv
import time
import requests
import re
from PIL import Image
from io import BytesIO
from typing import Dict
from openai import OpenAI


'''
OPEN AI Wapper 클래스. 현재는 GPT Asistant API를 사용중에 있음. 
GPT API 유료 결제 이후 Asistant 를 생성하고 생성 옵션을 작성해줘야 함. 
'''
class OpenAIWrapper:
    
    
    def __init__(self):
        self.file = '.env'
        self._api_key = dotenv.get_key(self.file, 'OPEN_AI_KEY')
        self._my_assistant_id = dotenv.get_key(self.file, 'MY_ASSISTANT_ID') 
        self._client = OpenAI(api_key=self._api_key, default_headers={"OpenAI-Beta": "assistants=v2"})
            
    def get_gpt_blog(self, keyword: str, use_assistant: bool = True) -> Dict[str, str]:
        if not self._api_key or not self._my_assistant_id:
            raise ValueError("API key or Assistant ID not found")


        try:
          
            response =  self.get_thread_response(keyword)
            print(response)
            title, tags, slug, content = self.parse_response(response)
            if dotenv.get_key(self.file, 'USE_GPT_IMAGE_CREATION') == 'True':
                img = self.generate_image(slug)
                return {
                    "title": title,
                    "tags": tags,
                    "slug": slug,
                    "content": content,
                    "img": img
                }
            else:
                   return {
                    "title": title,
                    "tags": tags,
                    "slug": slug,
                    "content": content
                }
        except Exception as e:
            raise e
            
    '''
    GPT Asistant API를 사용하여 게시글을 작성합니다. 
    '''
    def get_thread_response(self, keyword: str) -> str:
        thread = self._client.beta.threads.create()
        self._client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=keyword,
        )
        run = self._client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self._my_assistant_id
        )

        while True:
            run_status = self._client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            print('글 작성중...')
            if run_status.status in ["completed", "failed"]:
                if run_status.status == "failed":
                    raise Exception(run_status.last_error)
                break
            time.sleep(5)
        messages = self._client.beta.threads.messages.list(thread_id=thread.id)
        return messages.data[0].content[0].text.value
            
    def generate_image(self, prompt: str, n: int = 1, size: str = '1024x1024', quality='standard') -> BytesIO:
        """DALL·E를 사용하여 이미지를 생성하고 로컬 이미지로 변환. """
        response = self._client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )
        print('이미지 생성중..')
        image_url = response.data[0].url
        
        # 이미지 URL에서 이미지 데이터를 다운로드
        response = requests.get(image_url)
        image_data = BytesIO(response.content)
        # 이미지 사이즈 
        new_width = 256
        new_height = 256
        image = Image.open(BytesIO(response.content))

        resized_image = image.resize((new_width, new_height))

    
        # 이미지 파일 이름
        image_filename = f"{prompt}.png"
        # 이미지를 로컬 'images/' 디렉토리에 저장
        resized_image.save(f"images/{image_filename}")

        return f"images/{image_filename}"        
     
    def generate_text(self, prompt: str, model: str = "text-davinci-003", max_tokens: int = 100) -> str:
        """일반적인 텍스트 생성 API를 호출하여 주어진 프롬프트에 대한 텍스트를 생성합니다."""
        response = self.client.completions.create(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens
        )
        return response.choices[0].text.strip()
    
    def parse_response(self, response: str) -> tuple:
        """Parse the response from the OpenAI thread into structured data."""
        sections = response.split('제목:')
        title_content = sections[1].split('태그:')
        title = title_content[0].strip()
        tags_slug = title_content[1].split('slug:')
        tags = tags_slug[0].strip()
        slug_content = tags_slug[1].split('```html')
        slug = slug_content[0].strip()
        content = slug_content[1].replace('```', '').strip()
        return title, tags, slug, content
    
    def get_gpt_summary(self, review_content):
        try:
            print('GPT가 리뷰를 요약중입니다.')
            completion = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {
                        "role": "user",
                        "content": f"이 리뷰내용에서 중요한 부분만 추출하여 상품에 대한 분석을 리뷰어의 개인적이고 주관적인 정보(배송날짜, 구매의사등)는 제외하고 상품에 대한 정보만 이모지도 섞어서 200자 내로 리스트 형태로 새로 작성해줘. 리스트는 반드시! html <ul><li> 형태로 출력해줘. 너의 메세지는 제외하고 오로지 가공된 리스트만 출력해줘. : \n {review_content}"
                    }
                ]
            )
            res = completion.choices[0].message.content
            res = re.sub(r'```html|```', '', res).strip()
            return res
        except Exception as e:
            print(f"GPT 리뷰 요약 에러 발생: {e}")
            return ""
     
    
    def get_product_guide(self, product):
        
        try:
            print('GPT가 제품 선택 가이드를 작성 중입니다.')
            completion = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {
                        "role": "user",
                        "content": f"이 상품에 대한 전문적인 상품 구매 가이드를 어떤 기준으로 구매해야 좋은 제품을 구매 할 수 있는지, 이모지도 섞어서 태그제외 200자 내외의 리스트 형태로 새로 작성해줘. 리스트는 html <ul><li> 형태로 출력해줘. 너의 메세지는 제외하고 오로지 가공된 리스트만 출력해줘. : \n {product}"
                    }
                ]
            )
            res = completion.choices[0].message.content
            res = re.sub(r'```html|```', '', res).strip()
            return res
        except Exception as e:
            print(f"GPT 가이드 작성 에러 발생: {e}")
            return ""
        
    def get_product_description(self, product):
        
        try:
            print('GPT가 포스팅 소개구문을 작성 중입니다.')
            completion = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful blog specialist."},
                    {
                        "role": "user",
                        "content":  f"다음 상품 키워드를 활용해서 자연스럽고 설득력 있는 블로그 소개 멘트를 작성해줘. "
                        f"상품에 대한 설명이나 기능, 특징을 추측하거나 소개하지 마. "
                        f"단지 오늘 어떤 상품을 소개할지, 사람들이 많이 찾고 있다는 점, 지금 확인해보자는 안내 등으로 구성해줘. "
                        f"마치 쇼핑 전문 블로거가 쓴 것처럼 친근하면서도 분위기 있게 써줘. "
                        f"이모지도 적절히 활용하고, 500자 내외의 자연스러운 문장으로 구성해. "
                        f"출력은 HTML 코드블록 형태로 태그를 포함해서 출력해줘. "
                        f"태그 안에는 순수한 소개 문장만 들어가야 해. "
                        f"출력 외의 설명은 하지 말고, 완성된 소개 멘트만 보여줘. "
                        f"상품 키워드: {product}"
                    }
                ]
            )
            res = completion.choices[0].message.content
            # print(res)
            res = re.sub(r'```html|```', '', res).strip()
            return res
        except Exception as e:
            print(f"GPT 가이드 작성 에러 발생: {e}")
            return "" 
    def get_post_title(self, product, nth):
        try:
            print('GPT가 포스트 제목을 작성 중입니다.')
            completion = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful blog specialist."},
                    {
                        "role": "user",
                        "content": (
                            f"다음 상품 키워드와 상품수를 이용해 상품을 소개하는 블로그 제목을 만들어줘. "
                            f"제목은 매번 새로운 스타일로 작성하고, 예시처럼 반복하지 마. "
                            f"매번 다양하게 현실적으로 사람들이 많이 검색 할 만한 문구를 사용해줘. 1개의 제목이면 되"
                            f"(예: 트렌디한 상품명 탑5등) "
                            f"길지 않고 눈에 띄는 문구로 구성해. "
                            f"출력은 html 코드블록으로, 아무 태그도 포함하지 마. "
                            f"설명 없이 제목만 출력해. "
                            f"상품 키워드: {product} 상품수: {nth}"
                        )
                    }
                ]
            )

            res = completion.choices[0].message.content
            # print(res)
            # 코드 블록 안의 문자열만 추출 (```html ~ ```)
            res = re.sub(r'```html|```', '', res).strip()

            return res
        except Exception as e:
            print(f"GPT 가이드 작성 에러 발생: {e}")
            return ""
    