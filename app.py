"""
Langsam Songs Downloader
By Studio Oscar — Since 1931

A simple YouTube to MP3 streaming tool for family use.
No storage required - streams MP3 directly to browser.
Birthday gift for grandpa!
"""

from flask import Flask, render_template, request, Response, jsonify
import subprocess
import re
import json
import os
import sys

app = Flask(__name__)

# --- Configuration ---
YOUTUBE_PATTERNS = [
    r'youtube\.com/watch',
    r'youtu\.be/',
    r'youtube\.com/shorts/',
    r'youtube\.com/embed/',
    r'youtube\.com/v/',
    r'music\.youtube\.com',
]
MAX_DURATION = 7200  # 2 hours max
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
    
    print(f"[INFO] Received URL: {url}", file=sys.stderr)
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validate_url(url):
        print(f"[ERROR] URL validation failed for: {url}", file=sys.stderr)
        return jsonify({'error': 'Please enter a valid YouTube link'}), 400
    
    try:
        info = get_video_info(url)
        
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
    except Exception as e:
        print(f"[ERROR] Exception in get_info: {str(e)}", file=sys.stderr)
        return jsonify({'error': str(e)}), 400


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
        
        return Response(
            stream_mp3(url),
            mimetype='audio/mpeg',
            headers=headers
        )
    except Exception as e:
        print(f"[ERROR] Exception in download: {str(e)}", file=sys.stderr)
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})


@app.route('/api/update-ytdlp')
def update_ytdlp():
    """Update yt-dlp to latest version"""
    try:
        result = subprocess.run(
            ['pip', 'install', '--upgrade', 'yt-dlp'],
            capture_output=True,
            text=True,
            timeout=120
        )
        return jsonify({
            'status': 'ok',
            'output': result.stdout,
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Helper Functions ---

def validate_url(url):
    """Validate YouTube URL format - very permissive"""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Simple check - just needs to contain youtube or youtu.be
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        print(f"[INFO] URL validated: {url}", file=sys.stderr)
        return True
    
    print(f"[WARN] URL did not match: {url}", file=sys.stderr)
    return False


def get_video_info(url):
    """Fetch video metadata using yt-dlp with multiple fallback approaches"""
    
    # Try different approaches in order
    approaches = [
        # Approach 1: Web client (most compatible)
        {
            'name': 'web client',
            'cmd': [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                '--no-warnings',
                '--extractor-args', 'youtube:player_client=web',
                url
            ]
        },
        # Approach 2: Android client
        {
            'name': 'android client',
            'cmd': [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                '--no-warnings',
                '--extractor-args', 'youtube:player_client=android',
                url
            ]
        },
        # Approach 3: iOS client  
        {
            'name': 'ios client',
            'cmd': [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                '--no-warnings',
                '--extractor-args', 'youtube:player_client=ios',
                url
            ]
        },
        # Approach 4: Minimal (let yt-dlp decide)
        {
            'name': 'minimal',
            'cmd': [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                url
            ]
        },
        # Approach 5: Force generic extractor
        {
            'name': 'force ipv4',
            'cmd': [
                'yt-dlp',
                '--dump-json',
                '--no-playlist',
                '--force-ipv4',
                url
            ]
        },
    ]
    
    last_error = None
    
    for approach in approaches:
        try:
            print(f"[INFO] Trying {approach['name']}...", file=sys.stderr)
            
            result = subprocess.run(
                approach['cmd'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            print(f"[DEBUG] Return code: {result.returncode}", file=sys.stderr)
            
            if result.returncode == 0 and result.stdout.strip():
                print(f"[INFO] {approach['name']} succeeded!", file=sys.stderr)
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    print(f"[WARN] JSON parse failed for {approach['name']}", file=sys.stderr)
                    continue
            else:
                stderr_preview = result.stderr[:500] if result.stderr else 'No stderr'
                print(f"[WARN] {approach['name']} failed: {stderr_preview}", file=sys.stderr)
                last_error = result.stderr
                
        except subprocess.TimeoutExpired:
            print(f"[WARN] {approach['name']} timed out", file=sys.stderr)
            last_error = "Request timed out"
        except Exception as e:
            print(f"[WARN] {approach['name']} exception: {e}", file=sys.stderr)
            last_error = str(e)
    
    # All approaches failed
    error_msg = parse_ytdlp_error(last_error) if last_error else "Could not fetch video"
    raise Exception(error_msg)


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
        url
    ]
    
    print(f"[INFO] Starting MP3 stream for: {url}", file=sys.stderr)
    
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
        print(f"[INFO] Stream complete, sent {bytes_sent} bytes", file=sys.stderr)
    except GeneratorExit:
        print(f"[INFO] Client disconnected", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Stream error: {e}", file=sys.stderr)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def parse_ytdlp_error(stderr):
    """Convert yt-dlp errors to user-friendly messages"""
    if not stderr:
        return 'Unable to process this video'
    
    stderr_lower = stderr.lower()
    
    # Check for specific errors
    if 'video unavailable' in stderr_lower:
        return 'Video not found or unavailable'
    if 'private video' in stderr_lower:
        return 'This video is private'
    if 'copyright' in stderr_lower:
        return 'Video unavailable due to copyright'
    if 'removed' in stderr_lower or 'deleted' in stderr_lower:
        return 'This video has been removed'
    if 'premiere' in stderr_lower:
        return 'This video is not yet available'
    if 'sign in' in stderr_lower:
        return 'This video requires sign in'
    if 'age' in stderr_lower:
        return 'Age-restricted video - trying bypass...'
    if 'http error 403' in stderr_lower:
        return 'Access denied by YouTube'
    if 'http error 429' in stderr_lower:
        return 'Too many requests - wait a moment'
    if 'unable to extract' in stderr_lower:
        return 'Could not extract video info'
    if 'no video formats' in stderr_lower:
        return 'No downloadable formats found'
    
    # Return a generic but helpful message
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
    if not info:
        return ''
    
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
    
    print(f"[INFO] Starting Langsam Songs Downloader on port {port}", file=sys.stderr)
    print(f"[INFO] Checking yt-dlp version...", file=sys.stderr)
    
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        print(f"[INFO] yt-dlp version: {result.stdout.strip()}", file=sys.stderr)
    except:
        print(f"[WARN] Could not get yt-dlp version", file=sys.stderr)
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
