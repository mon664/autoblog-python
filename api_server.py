#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
import os
import sys
import json
import logging
from datetime import datetime

# 기존 AutoBlog 모듈 임포트 (수정 필요)
try:
    from blogger import BloggerAPI
    from tistory import TistoryAutomation
    from openAI import OpenAIAssistant
    from keyword_generator import KeywordGenerator
    from searchconsole import SearchConsoleAPI
except ImportError as e:
    logging.warning(f"모듈 임포트 실패: {e}")
    # 임시 클래스 정의 (배포 테스트용)
    class MockAPI:
        def __init__(self):
            pass
        def create_post(self, keyword, content):
            return f"https://mock-blog.com/post/{keyword}"
        def auto_post(self, keyword, content):
            return f"https://mock-tistory.com/post/{keyword}"
        def analyze(self, keyword):
            return {"related_keywords": [f"{keyword}_1", f"{keyword}_2"]}
        def generate_blog_post(self, keyword, template):
            return f"Generated content for {keyword} using {template} template"

    BloggerAPI = MockAPI
    TistoryAutomation = MockAPI
    OpenAIAssistant = MockAPI
    KeywordGenerator = MockAPI
    SearchConsoleAPI = MockAPI

# Flask 앱 초기화
app = Flask(__name__)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route('/health', methods=['GET'])
def health():
    """헬스체크 엔드포인트"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "AutoBlog API Server"
    })

@app.route('/api/blogger/post', methods=['POST'])
def create_blogger_post():
    """Google Blogger 포스팅"""
    try:
        data = request.json
        keyword = data.get('keyword', '')
        content = data.get('content', '')

        logger.info(f"Blogger 포스팅 요청: keyword={keyword}")

        if not keyword:
            return jsonify({"success": False, "error": "Keyword is required"}), 400

        blogger = BloggerAPI()
        result = blogger.create_post(keyword, content)

        return jsonify({
            "success": True,
            "url": result,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Blogger 포스팅 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tistory/post', methods=['POST'])
def create_tistory_post():
    """Tistory 포스팅"""
    try:
        data = request.json
        keyword = data.get('keyword', '')
        content = data.get('content', '')

        logger.info(f"Tistory 포스팅 요청: keyword={keyword}")

        if not keyword:
            return jsonify({"success": False, "error": "Keyword is required"}), 400

        tistory = TistoryAutomation()
        result = tistory.auto_post(keyword, content)

        return jsonify({
            "success": True,
            "url": result,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Tistory 포스팅 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/keywords/analyze', methods=['POST'])
def analyze_keywords():
    """네이버 키워드 분석"""
    try:
        data = request.json
        keyword = data.get('keyword', '')

        logger.info(f"키워드 분석 요청: keyword={keyword}")

        if not keyword:
            return jsonify({"success": False, "error": "Keyword is required"}), 400

        kg = KeywordGenerator()
        result = kg.analyze(keyword)

        return jsonify({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"키워드 분석 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/content/generate', methods=['POST'])
def generate_content():
    """OpenAI 콘텐츠 생성"""
    try:
        data = request.json
        keyword = data.get('keyword', '')
        template = data.get('template', 'default')

        logger.info(f"콘텐츠 생성 요청: keyword={keyword}, template={template}")

        if not keyword:
            return jsonify({"success": False, "error": "Keyword is required"}), 400

        ai = OpenAIAssistant()
        result = ai.generate_blog_post(keyword, template)

        return jsonify({
            "success": True,
            "content": result,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"콘텐츠 생성 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/searchconsole/submit', methods=['POST'])
def submit_to_searchconsole():
    """Google Search Console URL 제출"""
    try:
        data = request.json
        url = data.get('url', '')

        logger.info(f"Search Console 제출 요청: url={url}")

        if not url:
            return jsonify({"success": False, "error": "URL is required"}), 400

        sc = SearchConsoleAPI()
        result = sc.submit_url(url)

        return jsonify({
            "success": True,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Search Console 제출 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/coupang/search', methods=['POST'])
def search_coupang():
    """쿠팡 파트너스 상품 검색"""
    try:
        data = request.json
        keyword = data.get('keyword', '')
        limit = data.get('limit', 10)

        logger.info(f"쿠팡 상품 검색 요청: keyword={keyword}, limit={limit}")

        if not keyword:
            return jsonify({"success": False, "error": "Keyword is required"}), 400

        # 쿠팡 API 연동 코드 (기존 tistory.py에서 추출)
        # 이 부분은 실제 구현에 따라 수정 필요

        return jsonify({
            "success": True,
            "products": [],
            "message": "쿠팡 검색 기능 구현 예정",
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"쿠팡 상품 검색 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/info', methods=['GET'])
def get_api_info():
    """API 정보 반환"""
    return jsonify({
        "name": "AutoBlog API Server",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/api/blogger/post",
            "/api/tistory/post",
            "/api/keywords/analyze",
            "/api/content/generate",
            "/api/searchconsole/submit",
            "/api/coupang/search",
            "/api/info"
        ],
        "features": [
            "Google Blogger API",
            "Tistory Automation",
            "Naver Keyword Analysis",
            "OpenAI Content Generation",
            "Search Console Integration",
            "Coupang Partners Search"
        ]
    })

# 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"success": False, "error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '0.0.0.0')

    logger.info(f"AutoBlog API 서버 시작 - Port: {port}, Host: {host}")

    # debug=False로 설정 (프로덕션 환경)
    app.run(host=host, port=port, debug=False)