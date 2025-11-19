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
import ftplib
import io
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

# RaiDrive FTP 설정
FTP_CONFIG = {
    'host': '183.110.224.266',
    'port': 21,
    'username': 'xotjr105',
    'password': 'a6949689Q@@'
}

def upload_to_ftp(file_content, remote_filename, file_mode='binary'):
    """
    FTP 서버에 파일 업로드

    Args:
        file_content: 파일 내용 (bytes 또는 str)
        remote_filename: 원격 파일명
        file_mode: 전송 모드 ('binary' 또는 'ascii')

    Returns:
        업로드 성공 시 파일 URL, 실패 시 None
    """
    try:
        ftp = ftplib.FTP()
        ftp.connect(FTP_CONFIG['host'], FTP_CONFIG['port'])
        ftp.login(FTP_CONFIG['username'], FTP_CONFIG['password'])

        # 파일 내용을 bytes로 변환
        if isinstance(file_content, str):
            file_bytes = file_content.encode('utf-8')
        else:
            file_bytes = file_content

        # 파일 업로드
        if file_mode == 'binary':
            cmd = f'STOR {remote_filename}'
            ftp.storbinary(cmd, io.BytesIO(file_bytes))
        else:
            cmd = f'STOR {remote_filename}'
            ftp.storlines(cmd, io.StringIO(file_bytes.decode('utf-8')))

        ftp.quit()

        logger.info(f"FTP 업로드 성공: {remote_filename}")
        # FTP 접속 URL 반환 (웹 접근용)
        return f"ftp://{FTP_CONFIG['host']}/{remote_filename}"

    except Exception as e:
        logger.error(f"FTP 업로드 실패: {e}")
        return None

def download_from_ftp(remote_filename):
    """
    FTP 서버에서 파일 다운로드

    Args:
        remote_filename: 다운로드할 파일명

    Returns:
        파일 내용 (bytes), 실패 시 None
    """
    try:
        ftp = ftplib.FTP()
        ftp.connect(FTP_CONFIG['host'], FTP_CONFIG['port'])
        ftp.login(FTP_CONFIG['username'], FTP_CONFIG['password'])

        # 파일 다운로드
        file_bytes = io.BytesIO()
        ftp.retrbinary(f'RETR {remote_filename}', file_bytes.write)
        ftp.quit()

        file_bytes.seek(0)
        logger.info(f"FTP 다운로드 성공: {remote_filename}")
        return file_bytes.getvalue()

    except Exception as e:
        logger.error(f"FTP 다운로드 실패: {e}")
        return None

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
        audio_url = data.get('audio_url', '')  # 오디오 파일 (선택사항)
        sync_audio = data.get('sync_audio', False)  # 오디오 싱크 활성화
        target_duration = data.get('target_duration', None)  # 목표 영상 길이
        total_duration = data.get('total_duration', None)  # 전체 영상 길이

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

        # 오디오 싱크를 위한 동적 영상 길이 계산
        if sync_audio and total_duration:
            # 오디오 길이에 맞춰 각 장면의 길이 계산
            scene_duration = max(1, total_duration / len(images))
            duration = scene_duration
            logger.info(f"Audio sync enabled: {len(images)} images, {total_duration}s total, {scene_duration:.2f}s per scene")
        elif target_duration:
            # 목표 길이에 맞춰 장면 길이 계산
            scene_duration = max(1, target_duration / len(images))
            duration = scene_duration
            logger.info(f"Target duration: {len(images)} images, {target_duration}s total, {scene_duration:.2f}s per scene")

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
                elif image_data.startswith('http'):
                    # URL 이미지 다운로드
                    try:
                        response = requests.get(image_data, timeout=10)
                        if response.status_code == 200:
                            # 파일 확장자 결정
                            content_type = response.headers.get('content-type', 'image/jpeg')
                            if 'jpeg' in content_type or 'jpg' in content_type:
                                file_extension = 'jpg'
                            elif 'png' in content_type:
                                file_extension = 'png'
                            elif 'webp' in content_type:
                                file_extension = 'webp'
                            else:
                                file_extension = 'jpg'  # 기본값

                            image_path = os.path.join(temp_dir, f'input_{i}.{file_extension}')

                            with open(image_path, 'wb') as f:
                                f.write(response.content)

                            image_paths.append(image_path)
                            logger.info(f"Downloaded image {i} from {image_data}")
                        else:
                            logger.error(f"Failed to download image {i}: HTTP {response.status_code}")
                    except Exception as e:
                        logger.error(f"Error downloading image {i}: {str(e)}")
                else:
                    logger.warning(f"Unsupported image format for image {i}: {image_data[:50]}...")

            # 이미지 처리 확인
            if not image_paths:
                return jsonify({
                    "success": False,
                    "error": f"이미지 처리 실패: {len(images)}개 중 0개만 처리됨"
                }), 400

            logger.info(f"Successfully processed {len(image_paths)} images")

            # 해상도 설정
            resolution_map = {
                'landscape': (1920, 1080),  # 16:9 가로
                'portrait': (1080, 1920),   # 9:16 세로 (숏츠)
                'square': (1080, 1080)      # 1:1 정사각형
            }
            width, height = resolution_map.get(resolution, (1920, 1080))

            # FFmpeg 명령어 생성
            video_only_path = os.path.join(temp_dir, 'video_only.mp4')
            output_path = os.path.join(temp_dir, 'output_with_audio.mp4')

            # 1. 먼저 이미지로 비디오만 생성
            input_params = []
            for i, path in enumerate(image_paths):
                input_params.extend(['-loop', '1', '-t', str(duration), '-i', path])

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

            # 계산된 총 영상 길이
            calculated_video_duration = len(images) * duration

            # 비디오만 생성하는 FFmpeg 명령어
            video_cmd = [
                'ffmpeg',
                *input_params,
                '-filter_complex', ';'.join(filter_complex),
                '-map', '[out]',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', str(crf),
                '-pix_fmt', 'yuv420p',
                '-r', str(fps),
                '-t', str(calculated_video_duration),
                video_only_path
            ]

            logger.info(f"Video-only FFmpeg command: {' '.join(video_cmd)}")
            result = subprocess.run(video_cmd, capture_output=True, text=True, check=True)

            # 2. 오디오가 있으면 오디오와 비디오 결합 (MoviePy 완전 통합)
            if audio_url:
                audio_path = os.path.join(temp_dir, 'audio.mp3')
                processed_audio_path = os.path.join(temp_dir, 'processed_audio.mp3')

                # 오디오 파일 저장
                if audio_url.startswith('data:audio'):
                    header, encoded = audio_url.split(',', 1)
                    with open(audio_path, 'wb') as f:
                        f.write(base64.b64decode(encoded))

                # 라이트웨이트 오디오 전처리 (Railway 최적화)
                try:
                    # 1단계: 기본 오디오 최적화만 (Railway 부하 감소)
                    audio_process_cmd = [
                        'ffmpeg',
                        '-i', audio_path,
                        '-vn',  # 비디오 없음
                        '-af',
                        # 필수적인 최소한의 처리만
                        'volume=2.0',  # 볼륨만 2배 증가 (단순하고 빠름)
                        '-ar', '44100',  # 표준 샘플 레이트
                        '-ac', '2',      # 스테레오
                        '-c:a', 'mp3',   # 가볍고 호환성 좋은 포맷
                        '-b:a', '128k',  # 적정 비트레이트 (용량 절약)
                        '-y',            # 덮어쓰기
                        processed_audio_path
                    ]

                    logger.info(f"Lightweight audio processing: {' '.join(audio_process_cmd)}")
                    process_result = subprocess.run(audio_process_cmd, capture_output=True, text=True, check=True, timeout=30)  # 30초 타임아웃

                    # 전처리된 오디오 사용
                    if os.path.exists(processed_audio_path):
                        audio_path = processed_audio_path
                        logger.info("Lightweight audio processing completed")

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Audio processing failed: {e}, using original audio")
                    # 전처리 실패 시 원본 오디오 사용 (실패 방지)

                # 오디오 길이 확인 및 로깅
                try:
                    # ffprobe로 오디오 길이 확인
                    probe_cmd = [
                        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', audio_path
                    ]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
                    if probe_result.returncode == 0:
                        audio_duration = float(probe_result.stdout.strip())
                        logger.info(f"Audio duration detected: {audio_duration:.2f}s")

                        # 오디오 싱크가 활성화된 경우, 비디오 길이를 오디오 길이에 정확히 맞춤
                        if sync_audio:
                            logger.info(f"Syncing video duration {calculated_video_duration:.2f}s to audio duration {audio_duration:.2f}s")
                except Exception as e:
                    logger.warning(f"Could not probe audio duration: {e}")

                # MoviePy 스타일 효율적 오디오+비디오 결합 FFmpeg 명령어
                audio_cmd = [
                    'ffmpeg',
                    '-i', video_only_path,  # 비디오 입력
                    '-i', audio_path,        # 오디오 입력
                    '-c:v', 'copy',          # 비디오 코덱 복사 (품질 유지)
                    '-c:a', 'aac',           # AAC 코덱 (호환성)
                    '-b:a', '192k',          # 적정 비트레이트 (품질/용량 균형)
                    '-ar', '44100',          # 표준 샘플 레이트 (안정성)
                    '-ac', '2',              # 스테레오
                    '-movflags', '+faststart',  # 웹 스트리밍 최적화
                ]

                if sync_audio:
                    # 오디오 싱크 모드: 오디오 길이에 맞춰 비디오 조정
                    audio_cmd.extend([
                        '-t', str(audio_duration) if 'audio_duration' in locals() else str(calculated_video_duration),
                        '-async', '1',  # 오디오 싱크 보정
                    ])
                else:
                    # 기본 모드: 더 짧은 쪽에 맞춤
                    audio_cmd.append('-shortest')

                audio_cmd.append(output_path)

                logger.info(f"Audio+Video FFmpeg command: {' '.join(audio_cmd)}")
                result = subprocess.run(audio_cmd, capture_output=True, text=True, check=True)
            else:
                # 오디오가 없으면 비디오만 출력
                import shutil
                shutil.move(video_only_path, output_path)

            # 결과 비디오를 base64로 변환
            with open(output_path, 'rb') as f:
                video_data = f.read()

            video_base64 = base64.b64encode(video_data).decode('utf-8')
            video_url = f"data:video/mp4;base64,{video_base64}"

            # FTP에 비디오 파일 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resolution_tag = f"{width}x{height}"
            audio_tag = "with_audio" if audio_url else "no_audio"
            ftp_filename = f"video_{timestamp}_{resolution_tag}_{audio_tag}.mp4"
            ftp_url = upload_to_ftp(video_data, ftp_filename, 'binary')

            # 최종 메타데이터 계산
            final_duration = audio_duration if audio_url and 'audio_duration' in locals() else calculated_video_duration
            scene_duration = final_duration / len(images) if len(images) > 0 else duration

            return jsonify({
                "success": True,
                "video_url": video_url,
                "ftp_url": ftp_url,  # FTP 저장 경로 추가
                "metadata": {
                    "duration": final_duration,
                    "calculated_video_duration": calculated_video_duration,
                    "audio_duration": audio_duration if audio_url and 'audio_duration' in locals() else None,
                    "scene_duration": scene_duration,
                    "fps": fps,
                    "sync_audio": sync_audio,
                    "images_count": len(images),
                    "resolution": f"{width}x{height}",
                    "resolution_type": resolution,
                    "quality": quality,
                    "file_size": len(video_data),
                    "image_count": len(images),
                    "has_audio": bool(audio_url),
                    "audio_included": audio_url != "",
                    "ftp_file": ftp_filename
                },
                "ffmpeg_log": result.stderr if audio_url else "Video generated without audio"
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
            # Google Cloud TTS API 사용
            try:
                GOOGLE_API_KEY = os.environ.get('GOOGLE_TTS_API_KEY')

                if GOOGLE_API_KEY:
                    # 한국어 목소리 매핑
                    voiceMap = {
                        'ko-KR-JennyNeural': 'ko-KR-Wavenet-D',  # 남성 목소리 (더 선명함)
                        'ko-KR-SunHiNeural': 'ko-KR-Wavenet-A', # 여성 목소리 (일반적)
                        'ko-KR-InJoonNeural': 'ko-KR-Wavenet-B', # 여성 목소리
                        'ko-KR-KyungSunNeural': 'ko-KR-Wavenet-C'  # 여성 목소리
                    }

                    selectedVoice = voiceMap.get(voice, 'ko-KR-Wavenet-A')
                    logger.info(f"Using Google TTS voice: {selectedVoice}")

                    # Google Cloud TTS API 호출
                    response = requests.post(
                        f'https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}',
                        headers={
                            'Content-Type': 'application/json',
                        },
                        json={
                            'input': {'text': text},
                            'voice': {
                                'languageCode': 'ko-KR',
                                'name': selectedVoice,
                                'ssmlGender': 'NEUTRAL'
                            },
                            'audioConfig': {
                                'audioEncoding': 'MP3',
                                'speakingRate': 0.9,
                                'pitch': 0.0,
                                'sampleRateHertz': 24000,
                                'volumeGainDb': 5.0  # 볼륨 증가
                            }
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        audio_content = data.get('audioContent', '')

                        if audio_content:
                            audio_data = base64.b64decode(audio_content)
                            with open(audio_path, 'wb') as f:
                                f.write(audio_data)
                else:
                    logger.warning("Google TTS API key not found, falling back to Edge TTS")
                    # Edge TTS로 음성 생성 (스레드에서 async 실행)
                    communicate = edge_tts.Communicate(text, voice)
                    future = executor.submit(run_async, communicate.save(audio_path))
                    future.result()  # 완료될 때까지 대기

            except Exception as e:
                logger.error(f"Google TTS error: {e}, falling back to Edge TTS")
                # Edge TTS로 음성 생성 (스레드에서 async 실행)
                communicate = edge_tts.Communicate(text, voice)
                future = executor.submit(run_async, communicate.save(audio_path))
                future.result()  # 완료될 때까지 대기

            # 오디오 파일을 base64로 변환
            with open(audio_path, 'rb') as f:
                audio_data = f.read()

            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            audio_url = f"data:audio/mp3;base64,{audio_base64}"

            # FTP에 오디오 파일 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_text = text[:50].replace(" ", "_").replace("/", "_").replace("\\", "_")
            ftp_filename = f"tts_{timestamp}_{safe_text}.mp3"
            ftp_url = upload_to_ftp(audio_data, ftp_filename, 'binary')

            return jsonify({
                "success": True,
                "audio_url": audio_url,
                "ftp_url": ftp_url,  # FTP 저장 경로 추가
                "metadata": {
                    "text": text,
                    "voice": voice,
                    "duration": len(audio_data),
                    "format": "mp3",
                    "ftp_file": ftp_filename,
                    "provider": "Google Cloud TTS" if os.environ.get('GOOGLE_TTS_API_KEY') else "Edge TTS"
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
    """사용 가능한 TTS 목소리 목록 (Google Cloud TTS + Edge TTS)"""
    try:
        # 한국어 목소리들 (Google TTS 매핑)
        voices = [
            {"id": "ko-KR-JennyNeural", "name": "Jenny (남성, WaveNet-D)", "language": "Korean"},
            {"id": "ko-KR-SunHiNeural", "name": "SunHi (여성, WaveNet-A)", "language": "Korean"},
            {"id": "ko-KR-InJoonNeural", "name": "InJoon (여성, WaveNet-B)", "language": "Korean"},
            {"id": "ko-KR-KyungSunNeural", "name": "KyungSun (여성, WaveNet-C)", "language": "Korean"},
            # 영어 목소리들
            {"id": "en-US-JennyNeural", "name": "Jenny (US Female)", "language": "English"},
            {"id": "en-US-GuyNeural", "name": "Guy (US Male)", "language": "English"},
            {"id": "en-US-AriaNeural", "name": "Aria (US Female)", "language": "English"},
            {"id": "en-GB-ryanNeural", "name": "Ryan (UK Male)", "language": "English"},
        ]

        return jsonify({
            "success": True,
            "voices": voices,
            "default_voice": "ko-KR-JennyNeural",
            "provider": "Google Cloud TTS" if os.environ.get('GOOGLE_TTS_API_KEY') else "Edge TTS"
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

# FTP 관리 API 엔드포인트들
@app.route('/api/ftp/upload', methods=['POST'])
def upload_file_to_ftp():
    """파일을 FTP 서버에 업로드"""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        # 파일 읽기
        file_content = file.read()

        # 파일명 생성 (타임스탬프 추가)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_filename = file.filename
        safe_filename = f"{timestamp}_{original_filename}"

        # FTP 업로드
        ftp_url = upload_to_ftp(file_content, safe_filename, 'binary')

        if ftp_url:
            return jsonify({
                "success": True,
                "ftp_url": ftp_url,
                "filename": safe_filename,
                "original_filename": original_filename,
                "file_size": len(file_content)
            })
        else:
            return jsonify({"success": False, "error": "FTP upload failed"}), 500

    except Exception as e:
        logger.error(f"FTP upload failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"FTP upload failed: {str(e)}"
        }), 500

@app.route('/api/ftp/files', methods=['GET'])
def list_ftp_files():
    """FTP 서버 파일 목록 조회"""
    try:
        ftp = ftplib.FTP()
        ftp.connect(FTP_CONFIG['host'], FTP_CONFIG['port'])
        ftp.login(FTP_CONFIG['username'], FTP_CONFIG['password'])

        # 파일 목록 가져오기
        files = []
        ftp.dir("", files.append)
        ftp.quit()

        # 파일 정보 파싱
        file_list = []
        for file_info in files:
            if file_info.strip():
                parts = file_info.split()
                if len(parts) >= 9 and not parts[0].startswith('d'):
                    filename = ' '.join(parts[8:])
                    file_list.append({
                        "filename": filename,
                        "info": file_info.strip()
                    })

        return jsonify({
            "success": True,
            "files": file_list,
            "total_count": len(file_list)
        })

    except Exception as e:
        logger.error(f"FTP list files failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"FTP list files failed: {str(e)}"
        }), 500

@app.route('/api/ftp/download/<filename>', methods=['GET'])
def download_from_ftp_file(filename):
    """FTP 서버에서 파일 다운로드"""
    try:
        file_bytes = download_from_ftp(filename)

        if file_bytes:
            # 파일 타입 감지
            if filename.endswith('.mp4'):
                mimetype = 'video/mp4'
            elif filename.endswith('.mp3'):
                mimetype = 'audio/mpeg'
            elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
                mimetype = 'image/jpeg'
            elif filename.endswith('.png'):
                mimetype = 'image/png'
            else:
                mimetype = 'application/octet-stream'

            return file_bytes, 200, {
                'Content-Type': mimetype,
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        else:
            return jsonify({"success": False, "error": "File not found or download failed"}), 404

    except Exception as e:
        logger.error(f"FTP download failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"FTP download failed: {str(e)}"
        }), 500