// HTML escaping utility function
export function escapeHtml(unsafe) {
    return unsafe
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Enhanced SSE utility function for proper handling
export function safeEventSource(url, options = {}) {
    try {
        if (options.method === 'POST' && options.body) {
            return createPostEventSource(url, options);
        }
        // Use fetch-based approach for GET requests to support headers
        return createGetEventSource(url, options);
    } catch (error) {
        console.error('Error creating EventSource:', error);
        throw error;
    }
}

export function formatVendorName(vendor) {
    if (!vendor) return 'Unknown';
    return vendor.charAt(0).toUpperCase() + vendor.slice(1).toLowerCase();
}

// Fetch-based EventSource for GET requests to support headers
function createGetEventSource(url, options) {
    const token = localStorage.getItem('accessToken');
    const headers = {
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
        ...options.headers,
    };

    // The native EventSource does not support custom headers.
    // We must use a fetch-based polyfill.
    // This is a simplified implementation.
    
    const customEventSource = {
        _controller: new AbortController(),
        close: function() {
            this._controller.abort();
        },
        addEventListener: function(type, listener) {
            this[`on${type}`] = listener;
        },
        onopen: null,
        onmessage: null,
        onerror: null,
    };

    fetch(url, { headers, signal: customEventSource._controller.signal })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            if (customEventSource.onopen) customEventSource.onopen();

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            function push() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        return;
                    }
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    lines.forEach(line => {
                        if (line.startsWith('data:')) {
                            const data = line.substring(5).trim();
                            if (customEventSource.onmessage) {
                                customEventSource.onmessage({ data });
                            }
                        }
                    });
                    push();
                }).catch(err => {
                    if (err.name !== 'AbortError') {
                        if (customEventSource.onerror) {
                            customEventSource.onerror(err);
                        }
                    }
                });
            }
            push();
        })
        .catch(err => {
            if (customEventSource.onerror) {
                customEventSource.onerror(err);
            }
        });

    return customEventSource;
}


// Special handling for POST requests with SSE
function createPostEventSource(url, options) {
    return new Promise((resolve, reject) => {
        const token = localStorage.getItem('accessToken');
        
        // Use fetch to send POST data, but handle as SSE stream
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/event-stream',
                'Cache-Control': 'no-cache',
                ...options.headers
            },
            body: options.body
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            if (!response.body) {
                throw new Error('ReadableStream not supported');
            }
            
            // Create a custom EventSource-like object
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            const eventSourceLike = {
                readyState: 1, // OPEN
                url: url,
                withCredentials: false,
                close: function() {
                    this.readyState = 2; // CLOSED
                    reader.cancel();
                },
                addEventListener: function(type, listener) {
                    this[`on${type}`] = listener;
                },
                onopen: null,
                onmessage: null,
                onerror: null
            };
            
            // Start reading the stream
            function pump() {
                return reader.read().then(({ done, value }) => {
                    if (done) {
                        eventSourceLike.readyState = 2; // CLOSED
                        return;
                    }
                    
                    // Decode the chunk
                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6);
                            if (data.trim() && eventSourceLike.onmessage) {
                                eventSourceLike.onmessage({
                                    data: data,
                                    type: 'message',
                                    target: eventSourceLike
                                });
                            }
                        }
                    }
                    
                    return pump();
                }).catch(error => {
                    console.error('Stream reading error:', error);
                    eventSourceLike.readyState = 2; // CLOSED
                    if (eventSourceLike.onerror) {
                        eventSourceLike.onerror({ error });
                    }
                });
            }
            
            // Trigger onopen if defined
            if (eventSourceLike.onopen) {
                eventSourceLike.onopen({ type: 'open' });
            }
            
            // Start pumping data
            pump();
            
            resolve(eventSourceLike);
        })
        .catch(error => {
            console.error('Fetch error:', error);
            reject(error);
        });
    });
}

// Enhanced showToast function with better error handling
export function showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) {
        console.error('Toast container not found!');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 100);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (container.contains(toast)) {
                container.removeChild(toast);
            }
        }, 500);
    }, duration);
}

// Updated safeFetch function with better error handling
export async function safeFetch(url, options = {}) {
    try {
        const token = localStorage.getItem('accessToken');
        const defaultHeaders = {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` })
        };
        
        const response = await fetch(url, {
            ...options,
            headers: { ...defaultHeaders, ...options.headers }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }
        
        // Handle different response types
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        } else {
            return await response.text();
        }
        
    } catch (error) {
        console.error('Fetch error:', error);
        const errorMessage = error instanceof Error ? error.message : JSON.stringify(error);
        showToast(errorMessage, 'error');
        throw error;
    }
}

// JWT token decoder function
export function decodeToken(token) {
    try {
        if (!token) return null;
        
        const parts = token.split('.');
        if (parts.length !== 3) return null;
        
        const payload = parts[1];
        const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
        return JSON.parse(decoded);
    } catch (error) {
        console.error('Error decoding token:', error);
        return null;
    }
}

// Professional loading state management - no fade effects!
export function showSkeletonLoader(containerId, rowCount = 3) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const skeletonHTML = Array(rowCount).fill().map(() => 
        '<div class="skeleton-loader wide"></div>'
    ).join('');
    
    container.innerHTML = `<div class="skeleton-container">${skeletonHTML}</div>`;
}

export function hideSkeletonLoader(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const skeleton = container.querySelector('.skeleton-container');
    if (skeleton) {
        skeleton.remove();
    }
}

export function loadContentInstantly(containerId, content) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Remove skeleton immediately
    hideSkeletonLoader(containerId);
    
    // Show content instantly - no transitions!
    container.innerHTML = content;
    container.classList.add('instant-load');
}

// --- User Activity Timeout ---
const INACTIVITY_TIMEOUT = 60 * 60 * 1000; // 60 minutes

function checkActivity() {
    const lastActivity = localStorage.getItem('lastActivity');
    if (lastActivity && (Date.now() - lastActivity > INACTIVITY_TIMEOUT)) {
        logoutUser();
    }
}

export function resetActivityTimer() {
    localStorage.setItem('lastActivity', Date.now());
}

export function initActivityTracker() {
    resetActivityTimer();
    window.addEventListener('mousemove', resetActivityTimer);
    window.addEventListener('keydown', resetActivityTimer);
    window.addEventListener('click', resetActivityTimer);
    setInterval(checkActivity, 5000); // Check every 5 seconds
}

export function logoutUser() {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('userRole');
    localStorage.removeItem('lastActivity');
    window.location.href = 'login.html';
}
