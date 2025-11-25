"""
Langsam Songs Downloader
By Studio Oscar — Since 1931

A simple YouTube to MP3 streaming tool for family use.
Uses yt_dlp Python library with impersonate feature for better compatibility.
"""

import os
import sys
import re
import json
import logging
from flask import Flask, render_template, request, Response, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('langsam')

app = Flask(__name__)

# --- Configuration ---
MAX_DURATION = 7200  # 2 hours max
AUDIO_QUALITY = '192'

# yt-dlp options - following MeTube's approach
YTDLP_BASE_OPTIONS = {
    'quiet': True,
    'no_color': True,
    'no_warnings': True,
    'extract_flat': False,
    'noplaylist': True,
    'ignore_no_formats_error': True,
    'socket_timeout': 60,
    'retries': 3,
    'fragment_retries': 3,
}

# Try to enable impersonate feature if curl_cffi is available
try:
    import yt_dlp.networking.impersonate
    IMPERSONATE_AVAILABLE = True
    log.info("curl_cffi impersonate feature is available")
except ImportError:
    IMPERSONATE_AVAILABLE = False
    log.warning("curl_cffi not available - impersonate feature disabled")


def get_ytdlp_options(for_info=True):
    """Get yt-dlp options with impersonate if available"""
    opts = dict(YTDLP_BASE_OPTIONS)
    
    # Try impersonate feature (requires curl_cffi)
    if IMPERSONATE_AVAILABLE:
        try:
            opts['impersonate'] = yt_dlp.networking.impersonate.ImpersonateTarget.from_str('chrome')
            log.info("Using Chrome impersonation")
        except Exception as e:
            log.warning(f"Could not enable impersonate: {e}")
    
    if for_info:
        opts['extract_flat'] = False
    
    return opts


# --- Routes ---

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/api/info')
def get_info():
    """Fetch video metadata"""
    import yt_dlp
    
    url = request.args.get('url', '').strip()
    log.info(f"Fetching info for: {url}")
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validate_url(url):
        return jsonify({'error': 'Please enter a valid YouTube link'}), 400
    
    try:
        opts = get_ytdlp_options(for_info=True)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if not info:
            return jsonify({'error': 'Could not get video information'}), 400
        
        # Check duration limit
        duration = info.get('duration', 0) or 0
        if duration and duration > MAX_DURATION:
            return jsonify({
                'error': f'Video too long (max {MAX_DURATION // 60} minutes)'
            }), 400
        
        return jsonify({
            'title': info.get('title', 'Unknown'),
            'channel': info.get('uploader', info.get('channel', 'Unknown')),
            'duration': duration,
            'thumbnail': get_best_thumbnail(info),
        })
        
    except yt_dlp.utils.DownloadError as e:
        error_msg = parse_ytdlp_error(str(e))
        log.error(f"yt-dlp DownloadError: {e}")
        return jsonify({'error': error_msg}), 400
    except Exception as e:
        log.error(f"Unexpected error in get_info: {e}")
        return jsonify({'error': 'Unable to process this video'}), 400


@app.route('/api/download')
def download():
    """Stream MP3 download"""
    import yt_dlp
    import subprocess
    
    url = request.args.get('url', '').strip()
    log.info(f"Starting download for: {url}")
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validate_url(url):
        return jsonify({'error': 'Invalid URL'}), 400
    
    try:
        # Get title for filename
        opts = get_ytdlp_options(for_info=True)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        title = info.get('title', 'download') if info else 'download'
        filename = sanitize_filename(title) + '.mp3'
        
        # RFC 5987 encoding for filename with special characters
        ascii_filename = filename.encode('ascii', 'ignore').decode() or 'download.mp3'
        
        headers = {
            'Content-Type': 'audio/mpeg',
            'Content-Disposition': f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{filename}",
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        }
        
        def generate():
            """Stream MP3 using subprocess for better memory efficiency"""
            cmd = [
                'yt-dlp',
                '-f', 'bestaudio/best',
                '-x',
                '--audio-format', 'mp3',
                '--audio-quality', AUDIO_QUALITY,
                '-o', '-',
                '--no-playlist',
                '--quiet',
                '--no-warnings',
            ]
            
            # Add impersonate if available
            if IMPERSONATE_AVAILABLE:
                cmd.extend(['--impersonate', 'chrome'])
            
            cmd.append(url)
            
            log.info(f"Running command: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=8192
            )
            
            try:
                bytes_sent = 0
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        break
                    bytes_sent += len(chunk)
                    yield chunk
                
                log.info(f"Stream complete, sent {bytes_sent} bytes")
                
            except GeneratorExit:
                log.info("Client disconnected")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        return Response(
            generate(),
            mimetype='audio/mpeg',
            headers=headers
        )
        
    except Exception as e:
        log.error(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    import yt_dlp
    return jsonify({
        'status': 'ok',
        'yt_dlp_version': yt_dlp.version.__version__,
        'impersonate_available': IMPERSONATE_AVAILABLE,
    })


# --- Helper Functions ---

def validate_url(url):
    """Validate YouTube URL format - permissive"""
    if not url:
        return False
    url_lower = url.lower()
    return 'youtube.com' in url_lower or 'youtu.be' in url_lower


def parse_ytdlp_error(error_str):
    """Convert yt-dlp errors to user-friendly messages"""
    if not error_str:
        return 'Unable to process this video'
    
    error_lower = error_str.lower()
    
    if 'video unavailable' in error_lower:
        return 'Video not found or unavailable'
    if 'private video' in error_lower:
        return 'This video is private'
    if 'sign in' in error_lower or 'login' in error_lower:
        return 'This video requires sign-in. Try a different video.'
    if 'age' in error_lower and 'restrict' in error_lower:
        return 'Age-restricted video. Try a different video.'
    if 'copyright' in error_lower:
        return 'Video unavailable due to copyright'
    if 'removed' in error_lower or 'deleted' in error_lower:
        return 'This video has been removed'
    if 'premiere' in error_lower:
        return 'This video is not yet available'
    if 'geo' in error_lower or 'region' in error_lower:
        return 'Video not available in your region'
    if '403' in error_lower:
        return 'Access denied by YouTube'
    if '429' in error_lower:
        return 'Too many requests - please wait a moment'
    if 'no video formats' in error_lower:
        return 'No downloadable formats found'
    
    return 'Unable to process this video. Try a different one.'


def sanitize_filename(title):
    """Clean title for use as filename"""
    if not title:
        return 'download'
    
    # Remove invalid characters for filenames
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned[:96].strip('. ')
    
    return cleaned or 'download'


def get_best_thumbnail(info):
    """Get the best available thumbnail URL"""
    if not info:
        return ''
    
    thumbnails = info.get('thumbnails', [])
    if thumbnails:
        for thumb in reversed(thumbnails):
            url = thumb.get('url', '')
            if url and ('maxresdefault' in url or 'hqdefault' in url):
                return url
        return thumbnails[-1].get('url', '')
    
    return info.get('thumbnail', '')


# --- Main ---

if __name__ == '__main__':
    import yt_dlp
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    log.info(f"Starting Langsam Songs Downloader on port {port}")
    log.info(f"yt-dlp version: {yt_dlp.version.__version__}")
    log.info(f"Impersonate available: {IMPERSONATE_AVAILABLE}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
