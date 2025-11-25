"""
Langsam Songs Downloader
By Studio Oscar — Since 1931

A simple YouTube to MP3 streaming tool for family use.
No storage required - streams MP3 directly to browser.
"""

from flask import Flask, render_template, request, Response, jsonify
import subprocess
import re
import json
import os

app = Flask(__name__)

# --- Configuration ---
YOUTUBE_PATTERNS = [
    r'^(https?://)?(www\.)?(youtube\.com/watch\?v=)[\w-]+',
    r'^(https?://)?(www\.)?(youtu\.be/)[\w-]+',
    r'^(https?://)?(www\.)?(youtube\.com/shorts/)[\w-]+',
    r'^(https?://)?(www\.)?(youtube\.com/embed/)[\w-]+',
    r'^(https?://)?(music\.youtube\.com/watch\?v=)[\w-]+',
]
MAX_DURATION = 3600  # 1 hour max
AUDIO_QUALITY = '192'


# --- Routes ---

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/api/info')
def get_info():
    """Fetch video metadata"""
    url = request.args.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validate_url(url):
        return jsonify({'error': 'Please enter a valid YouTube link'}), 400
    
    try:
        info = get_video_info(url)
        
        # Check duration limit
        duration = info.get('duration', 0)
        if duration and duration > MAX_DURATION:
            return jsonify({
                'error': f'Video too long (max {MAX_DURATION // 60} minutes)'
            }), 400
        
        return jsonify({
            'title': info.get('title', 'Unknown'),
            'channel': info.get('uploader', info.get('channel', 'Unknown')),
            'duration': info.get('duration', 0),
            'thumbnail': get_best_thumbnail(info),
        })
    except Exception as e:
        error_msg = str(e)
        return jsonify({'error': error_msg}), 400


@app.route('/api/download')
def download():
    """Stream MP3 download"""
    url = request.args.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validate_url(url):
        return jsonify({'error': 'Invalid URL'}), 400
    
    try:
        # Get title for filename
        info = get_video_info(url)
        title = info.get('title', 'download')
        filename = sanitize_filename(title) + '.mp3'
        
        # RFC 5987 encoding for filename with special characters
        ascii_filename = filename.encode('ascii', 'ignore').decode()
        
        headers = {
            'Content-Type': 'audio/mpeg',
            'Content-Disposition': f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{filename}",
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        }
        
        return Response(
            stream_mp3(url),
            mimetype='audio/mpeg',
            headers=headers
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})


# --- Helper Functions ---

def validate_url(url):
    """Validate YouTube URL format"""
    if not url:
        return False
    
    for pattern in YOUTUBE_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False


def get_video_info(url):
    """Fetch video metadata using yt-dlp"""
    cmd = [
        'yt-dlp',
        '--dump-json',
        '--no-playlist',
        '--no-warnings',
        url
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = parse_ytdlp_error(result.stderr)
            raise Exception(error_msg)
        
        return json.loads(result.stdout)
    
    except subprocess.TimeoutExpired:
        raise Exception('Request timed out. Please try again.')
    except json.JSONDecodeError:
        raise Exception('Failed to parse video information')


def stream_mp3(url):
    """Stream MP3 audio directly to response"""
    cmd = [
        'yt-dlp',
        '-f', 'bestaudio/best',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', AUDIO_QUALITY,
        '-o', '-',
        '--no-playlist',
        '--no-warnings',
        '--quiet',
        url
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=8192
    )
    
    try:
        while True:
            chunk = process.stdout.read(8192)
            if not chunk:
                break
            yield chunk
    except GeneratorExit:
        # Client disconnected
        pass
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def parse_ytdlp_error(stderr):
    """Convert yt-dlp errors to user-friendly messages"""
    stderr_lower = stderr.lower()
    
    if 'video unavailable' in stderr_lower:
        return 'Video not found or unavailable'
    if 'private video' in stderr_lower:
        return 'This video is private'
    if 'sign in' in stderr_lower or 'age' in stderr_lower:
        return 'This video is age-restricted'
    if 'copyright' in stderr_lower:
        return 'Video unavailable due to copyright'
    if 'geo' in stderr_lower or 'country' in stderr_lower:
        return 'Video not available in your region'
    if 'removed' in stderr_lower or 'deleted' in stderr_lower:
        return 'This video has been removed'
    if 'live' in stderr_lower:
        return 'Live streams cannot be downloaded'
    if 'premiere' in stderr_lower:
        return 'This video is not yet available'
    if 'not a valid url' in stderr_lower:
        return 'Please enter a valid YouTube link'
    
    return 'Unable to process this video. Please try another.'


def sanitize_filename(title):
    """Clean title for use as filename"""
    if not title:
        return 'download'
    
    # Remove invalid characters for filenames
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    
    # Replace multiple spaces with single space
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Limit length (leaving room for .mp3 extension)
    cleaned = cleaned[:96]
    
    # Remove leading/trailing spaces and dots
    cleaned = cleaned.strip('. ')
    
    return cleaned or 'download'


def get_best_thumbnail(info):
    """Get the best available thumbnail URL"""
    # Try to get a good quality thumbnail
    thumbnails = info.get('thumbnails', [])
    
    if thumbnails:
        # Sort by preference (higher resolution first)
        for thumb in reversed(thumbnails):
            url = thumb.get('url', '')
            if url and ('maxresdefault' in url or 'hqdefault' in url):
                return url
        # Fallback to last thumbnail
        return thumbnails[-1].get('url', '')
    
    # Fallback to standard thumbnail field
    return info.get('thumbnail', '')


# --- Main ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )

