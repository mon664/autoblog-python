#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
import os
import sys
import json
import logging
from datetime import datetime
import subprocess
import tempfile
import base64
import uuid
import asyncio
import edge_tts
from concurrent.futures import ThreadPoolExecutor

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
        def create_post(self, title, content, labels=None):
            return f"https://mock-blog.com/post/{title}"
        def auto_post(self, keyword, content):
            return f"https://mock-tistory.com/post/{keyword}"
        def analyze(self, keyword):
            return {"related_keywords": [f"{keyword}_1", f"{keyword}_2"]}
        def generate_blog_post(self, keyword, template):
            return f"Generated content for {keyword} using {template} template"
        def submit_url(self, url):
            return {"status": "submitted", "url": url}

    BloggerAPI = MockAPI
    TistoryAutomation = MockAPI
    OpenAIAssistant = MockAPI
    KeywordGenerator = MockAPI
    SearchConsoleAPI = MockAPI

# Flask 앱 초기화
app = Flask(__name__)

# 스레드 풀 executor
executor = ThreadPoolExecutor(max_workers=4)

# JSON 및 CORS 설정
app.config['JSON_AS_ASCII'] = False
app.config['JSON_SORT_KEYS'] = False

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
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

        # title과 content를 받음 (keyword는 선택)
        title = data.get('title', '')
        content = data.get('content', '')
        labels = data.get('labels', [])
        
        # title이 없으면 keyword 사용 (하위 호환성)
        if not title:
            title = data.get('keyword', '')

        logger.info(f"Blogger 포스팅 요청: title={title}")

        if not title or not content:
            return jsonify({
                "success": False, 
                "error": "Title and content are required"
            }), 400

        blogger = BloggerAPI()
        result = blogger.create_post(
            title=title,
            content=content,
            labels=labels
        )

        return jsonify({
            "success": True,
            "url": result,
            "post": {
                "title": title,
                "url": result
            },
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Blogger 포스팅 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tistory/post', methods=['POST'])
def create_tistory_post():
    """Tistory 포스팅"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

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
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

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
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

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
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400
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
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

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

@app.route('/api/test', methods=['POST'])
def test_post():
    """POST 요청 테스트 및 기능 엔드포인트"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400

        # 기능별 처리
        action = data.get('action', 'test')

        if action == 'blogger':
            # Blogger 기능
            title = data.get('title', 'Default Title')
            content = data.get('content', 'Default content')
            labels = data.get('labels', [])

            blogger = BloggerAPI()
            result = blogger.create_post(title=title, content=content, labels=labels)

            return jsonify({
                "success": True,
                "action": "blogger",
                "url": result,
                "post": {
                    "title": title,
                    "url": result
                },
                "timestamp": datetime.now().isoformat()
            })

        elif action == 'content':
            # Content Generation 기능
            keyword = data.get('keyword', 'Default keyword')
            template = data.get('template', 'default')

            ai = OpenAIAssistant()
            result = ai.generate_blog_post(keyword, template)

            return jsonify({
                "success": True,
                "action": "content",
                "content": result,
                "timestamp": datetime.now().isoformat()
            })

        elif action == 'keywords':
            # Keywords 기능
            keyword = data.get('keyword', 'Default keyword')

            kg = KeywordGenerator()
            result = kg.analyze(keyword)

            return jsonify({
                "success": True,
                "action": "keywords",
                "data": result,
                "timestamp": datetime.now().isoformat()
            })

        else:
            # 기본 테스트 응답
            return jsonify({
                "success": True,
                "message": "POST test successful",
                "received_data": data,
                "timestamp": datetime.now().isoformat()
            })

    except Exception as e:
        logger.error(f"Test POST 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ===========================
# 🎬 FFmpeg 비디오 처리 엔드포인트
# ===========================

@app.route('/api/video/generate', methods=['POST'])
def generate_video():
    """이미지 배열을 비디오로 변환 (서버 측 FFmpeg)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        images = data.get('images', [])
        duration = data.get('duration', 3)
        fps = data.get('fps', 30)
        quality = data.get('quality', 'medium')
        resolution = data.get('resolution', 'landscape')  # landscape, portrait, square

        if not images or len(images) == 0:
            return jsonify({"success": False, "error": "이미지가 필요합니다"}), 400

        # FFmpeg 설치 확인
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return jsonify({
                "success": False,
                "error": "FFmpeg가 설치되지 않았습니다"
            }), 500

        # 임시 디렉토리 생성
        temp_dir = tempfile.mkdtemp()

        try:
            # 이미지 파일 저장
            image_paths = []
            for i, image_data in enumerate(images):
                if image_data.startswith('data:image'):
                    # Base64 이미지 디코딩
                    header, encoded = image_data.split(',', 1)
                    file_extension = header.split('/')[1].split(';')[0]

                    image_path = os.path.join(temp_dir, f'input_{i}.{file_extension}')

                    with open(image_path, 'wb') as f:
                        f.write(base64.b64decode(encoded))

                    image_paths.append(image_path)

            # FFmpeg 명령어 생성
            output_path = os.path.join(temp_dir, 'output.mp4')

            # 입력 파라미터
            input_params = []
            for i, path in enumerate(image_paths):
                input_params.extend(['-loop', '1', '-t', str(duration), '-i', path])

            # 해상도 설정
            resolution_map = {
                'landscape': (1920, 1080),  # 16:9 가로
                'portrait': (1080, 1920),   # 9:16 세로 (숏츠)
                'square': (1080, 1080)      # 1:1 정사각형
            }
            width, height = resolution_map.get(resolution, (1920, 1080))

            # 필터 설정
            filter_complex = []
            filter_parts = []

            for i, path in enumerate(image_paths):
                # 선택된 해상도로 스케일 및 패딩
                filter_complex.append(f'[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]')
                filter_parts.append(f'[v{i}]')

            # 이미지 연결
            concat_filter = f'{"".join(filter_parts)}concat=n={len(image_paths)}:v=1[out]'
            filter_complex.append(concat_filter)

            # 품질 설정
            crf_map = {'low': 28, 'medium': 23, 'high': 18}
            crf = crf_map.get(quality, 23)

            # FFmpeg 명령어 실행
            cmd = [
                'ffmpeg',
                *input_params,
                '-filter_complex', ';'.join(filter_complex),
                '-map', '[out]',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', str(crf),
                '-pix_fmt', 'yuv420p',
                '-r', str(fps),
                '-t', str(len(images) * duration),
                output_path
            ]

            logger.info(f"FFmpeg command: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # 결과 비디오를 base64로 변환
            with open(output_path, 'rb') as f:
                video_data = f.read()

            video_base64 = base64.b64encode(video_data).decode('utf-8')
            video_url = f"data:video/mp4;base64,{video_base64}"

            return jsonify({
                "success": True,
                "video_url": video_url,
                "metadata": {
                    "duration": len(images) * duration,
                    "fps": fps,
                    "resolution": f"{width}x{height}",
                    "resolution_type": resolution,
                    "quality": quality,
                    "file_size": len(video_data),
                    "image_count": len(images)
                },
                "ffmpeg_log": result.stderr
            })

        finally:
            # 임시 파일 정리
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg execution failed: {e.stderr}")
        return jsonify({
            "success": False,
            "error": "FFmpeg 실행 실패",
            "details": e.stderr
        }), 500
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/video/info', methods=['GET'])
def ffmpeg_info():
    """FFmpeg 설치 정보 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, check=True)

        # FFmpeg 버전 정보 파싱
        first_line = result.stdout.split('\n')[0]

        return jsonify({
            "success": True,
            "installed": True,
            "version": first_line,
            "full_output": result.stdout,
            "server_info": {
                "platform": os.uname().sysname,
                "architecture": os.uname().machine
            }
        })

    except FileNotFoundError:
        return jsonify({
            "success": False,
            "installed": False,
            "error": "FFmpeg가 설치되지 않았습니다"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# Async 함수를 위한 헬퍼
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/api/tts/generate', methods=['POST'])
def generate_tts():
    """Edge TTS로 음성 파일 생성"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        text = data.get('text', '')
        voice = data.get('voice', 'ko-KR-JennyNeural')  # 기본 한국어 여성 목소리

        if not text:
            return jsonify({"success": False, "error": "Text is required"}), 400

        temp_dir = tempfile.mkdtemp()
        audio_path = os.path.join(temp_dir, 'tts_audio.mp3')

        try:
            # Edge TTS로 음성 생성 (스레드에서 async 실행)
            communicate = edge_tts.Communicate(text, voice)
            future = executor.submit(run_async, communicate.save(audio_path))
            future.result()  # 완료될 때까지 대기

            # 오디오 파일을 base64로 변환
            with open(audio_path, 'rb') as f:
                audio_data = f.read()

            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            audio_url = f"data:audio/mp3;base64,{audio_base64}"

            return jsonify({
                "success": True,
                "audio_url": audio_url,
                "metadata": {
                    "text": text,
                    "voice": voice,
                    "duration": len(audio_data),
                    "format": "mp3"
                }
            })

        finally:
            # 임시 파일 정리
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"TTS generation failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"TTS 생성 실패: {str(e)}"
        }), 500

@app.route('/api/tts/voices', methods=['GET'])
def get_tts_voices():
    """사용 가능한 Edge TTS 목소리 목록"""
    try:
        # 한국어 목소리들
        voices = [
            {"id": "ko-KR-JennyNeural", "name": "Jenny (여성)", "language": "Korean"},
            {"id": "ko-KR-SunHiNeural", "name": "SunHi (여성)", "language": "Korean"},
            {"id": "ko-KR-InJoonNeural", "name": "InJoon (남성)", "language": "Korean"},
            {"id": "ko-KR-KyungSunNeural", "name": "KyungSun (여성)", "language": "Korean"},
            # 영어 목소리들
            {"id": "en-US-JennyNeural", "name": "Jenny (US Female)", "language": "English"},
            {"id": "en-US-GuyNeural", "name": "Guy (US Male)", "language": "English"},
            {"id": "en-US-AriaNeural", "name": "Aria (US Female)", "language": "English"},
            {"id": "en-GB-ryanNeural", "name": "Ryan (UK Male)", "language": "English"},
        ]

        return jsonify({
            "success": True,
            "voices": voices,
            "default_voice": "ko-KR-JennyNeural"
        })

    except Exception as e:
        logger.error(f"Get TTS voices failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '0.0.0.0')

    logger.info(f"AutoBlog API 서버 시작 - Port: {port}, Host: {host}")

    # debug=False로 설정 (프로덕션 환경)
    app.run(host=host, port=port, debug=False)