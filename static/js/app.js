/**
 * Langsam Songs Downloader
 * By Studio Oscar — Since 1931
 * 
 * Client-side JavaScript for form handling and download management.
 * Birthday gift for grandpa!
 */

// === DOM Elements ===
const form = document.getElementById('download-form');
const urlInput = document.getElementById('url-input');
const clearBtn = document.getElementById('clear-btn');
const downloadBtn = document.getElementById('download-btn');
const songInfo = document.getElementById('song-info');
const status = document.getElementById('status');
const progress = document.getElementById('progress');
const inputHint = document.getElementById('input-hint');
const inputError = document.getElementById('input-error');

// === State ===
let isProcessing = false;

// === YouTube URL Patterns (very permissive for grandpa!) ===
const YOUTUBE_PATTERNS = [
    /youtube\.com\/watch/i,
    /youtu\.be\//i,
    /youtube\.com\/shorts\//i,
    /youtube\.com\/embed\//i,
    /youtube\.com\/v\//i,
    /music\.youtube\.com/i,
];

// === Initialize ===
document.addEventListener('DOMContentLoaded', init);

function init() {
    // Event listeners
    form.addEventListener('submit', handleSubmit);
    urlInput.addEventListener('input', handleInputChange);
    urlInput.addEventListener('paste', handlePaste);
    clearBtn.addEventListener('click', clearInput);
    
    // Auto-focus on desktop
    if (window.innerWidth > 768) {
        urlInput.focus();
    }
}

// === Event Handlers ===

function handleSubmit(e) {
    e.preventDefault();
    
    if (isProcessing) return;
    
    const url = urlInput.value.trim();
    
    if (!url) {
        showInputError('Please enter a YouTube link');
        return;
    }
    
    if (!validateUrl(url)) {
        showInputError('Please enter a valid YouTube link');
        return;
    }
    
    startDownload(url);
}

function handleInputChange() {
    const value = urlInput.value;
    
    // Show/hide clear button
    clearBtn.classList.toggle('visible', value.length > 0);
    
    // Clear error state on input
    clearInputError();
    
    // Hide status when user starts typing again
    if (value.length > 0) {
        hideStatus();
    }
}

function handlePaste(e) {
    // Small delay to get the pasted value
    setTimeout(() => {
        handleInputChange();
    }, 10);
}

function clearInput() {
    urlInput.value = '';
    urlInput.focus();
    clearBtn.classList.remove('visible');
    clearInputError();
    hideSongInfo();
}

// === Core Functions ===

function validateUrl(url) {
    // Check if URL contains any YouTube pattern
    return YOUTUBE_PATTERNS.some(pattern => pattern.test(url));
}

async function startDownload(url) {
    setProcessingState(true);
    hideStatus();
    hideSongInfo();
    showProgress('Fetching video info...', 5);
    
    try {
        // Step 1: Get video info (with retry)
        let info;
        let retries = 2;
        let lastError;
        
        while (retries >= 0) {
            try {
                info = await fetchVideoInfo(url);
                break; // Success!
            } catch (err) {
                lastError = err;
                retries--;
                if (retries >= 0) {
                    console.log(`Retry attempt, ${retries + 1} left...`);
                    showProgress('Retrying...', 10);
                    await sleep(1000);
                }
            }
        }
        
        if (!info) {
            throw lastError || new Error('Could not get video info');
        }
        
        showSongInfo(info);
        showProgress('Preparing download...', 30);
        
        // Check for long video warning
        if (info.duration > 900) { // > 15 minutes
            showInfo(
                'Long video detected',
                `This video is ${formatDuration(info.duration)}. Download may take a few minutes.`
            );
        }
        
        // Step 2: Trigger download
        showProgress('Downloading...', 60);
        
        // Start the actual download
        await triggerDownload(url, info.title);
        
        // Step 3: Success
        showProgress('Complete!', 100);
        
        setTimeout(() => {
            showSuccess('Download started!', 'Check your browser downloads.');
            hideProgress();
        }, 500);
        
        // Reset form after delay
        setTimeout(() => {
            resetForm();
        }, 4000);
        
    } catch (error) {
        console.error('Download error:', error);
        showError('Download failed', error.message || 'Please try again.');
        hideProgress();
        hideSongInfo();
    } finally {
        setProcessingState(false);
    }
}

async function fetchVideoInfo(url) {
    const response = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
    
    let data;
    try {
        data = await response.json();
    } catch (e) {
        throw new Error('Server error. Please try again.');
    }
    
    if (!response.ok) {
        throw new Error(data.error || 'Failed to fetch video info');
    }
    
    return data;
}

async function triggerDownload(url, title) {
    // Create a hidden link and trigger download
    const downloadUrl = `/api/download?url=${encodeURIComponent(url)}`;
    
    // Use iframe approach for better download handling
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = downloadUrl;
    document.body.appendChild(iframe);
    
    // Return a promise that resolves after a short delay
    // (actual download happens in the background)
    return new Promise((resolve) => {
        setTimeout(() => {
            // Clean up iframe after download starts
            setTimeout(() => {
                if (iframe.parentNode) {
                    document.body.removeChild(iframe);
                }
            }, 120000); // Keep iframe for 2 minutes to allow download
            resolve();
        }, 1500);
    });
}

// === State Management ===

function setProcessingState(processing) {
    isProcessing = processing;
    urlInput.disabled = processing;
    downloadBtn.disabled = processing;
    downloadBtn.classList.toggle('btn--loading', processing);
}

// === UI Updates ===

function showProgress(stage, percent) {
    progress.hidden = false;
    document.getElementById('progress-stage').textContent = stage;
    document.getElementById('progress-percent').textContent = `${percent}%`;
    document.getElementById('progress-fill').style.width = `${percent}%`;
}

function hideProgress() {
    progress.hidden = true;
    document.getElementById('progress-fill').style.width = '0%';
}

function showSongInfo(info) {
    const thumb = document.getElementById('song-thumb');
    const title = document.getElementById('song-title');
    const channel = document.getElementById('song-channel');
    const duration = document.getElementById('song-duration');
    
    thumb.src = info.thumbnail || '';
    thumb.onerror = () => { thumb.style.display = 'none'; };
    thumb.onload = () => { thumb.style.display = 'block'; };
    
    title.textContent = info.title || 'Unknown';
    title.title = info.title || ''; // Tooltip for long titles
    channel.textContent = info.channel || 'Unknown';
    duration.textContent = formatDuration(info.duration);
    
    songInfo.hidden = false;
}

function hideSongInfo() {
    songInfo.hidden = true;
}

function showStatus(type, title, message) {
    status.className = `status status--${type}`;
    document.getElementById('status-title').textContent = title;
    document.getElementById('status-message').textContent = message || '';
    status.hidden = false;
}

function hideStatus() {
    status.hidden = true;
}

function showSuccess(title, message) {
    showStatus('success', title, message);
}

function showError(title, message) {
    showStatus('error', title, message);
}

function showInfo(title, message) {
    showStatus('info', title, message);
}

function showInputError(message) {
    urlInput.classList.add('input-group__input--error');
    inputError.textContent = message;
    inputError.classList.add('visible');
    inputHint.style.display = 'none';
}

function clearInputError() {
    urlInput.classList.remove('input-group__input--error');
    inputError.classList.remove('visible');
    inputHint.style.display = '';
}

function resetForm() {
    hideStatus();
    hideProgress();
    hideSongInfo();
    clearInputError();
}

// === Utilities ===

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0:00';
    
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function sanitizeFilename(title) {
    if (!title) return 'download';
    return title
        .replace(/[<>:"/\\|?*\x00-\x1f]/g, '')
        .replace(/\s+/g, ' ')
        .substring(0, 100)
        .trim() || 'download';
}
