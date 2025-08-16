// Simple, professional MPA approach - no SPA routing chaos
import { API_URL } from './config.js';
import { showToast, decodeToken } from './utils.js';
import { initializePage, checkAuthentication } from '../shared/page-init.js';
import { sendLog } from './api.js';

// Frontend logging configuration - change this to control what gets sent to backend
// Levels: 'off', 'error', 'warn', 'info', 'debug', 'all'
const FRONTEND_LOG_LEVEL = 'error';

// --- Global Error Handling ---
// Helper function to determine if a log level should be sent to backend
function shouldSendLog(level) {
    if (FRONTEND_LOG_LEVEL === 'off') return false;
    if (FRONTEND_LOG_LEVEL === 'all') return true;
    if (FRONTEND_LOG_LEVEL === 'error' && level === 'error') return true;
    if (FRONTEND_LOG_LEVEL === 'warn' && ['error', 'warn'].includes(level)) return true;
    if (FRONTEND_LOG_LEVEL === 'info' && ['error', 'warn', 'info'].includes(level)) return true;
    if (FRONTEND_LOG_LEVEL === 'debug' && ['error', 'warn', 'info', 'debug'].includes(level)) return true;
    return false;
}

const originalConsoleError = console.error;
console.error = function(message, ...optionalParams) {
    originalConsoleError.apply(console, [message, ...optionalParams]);
    if (shouldSendLog('error')) {
        const errorMessage = typeof message === 'object' ? JSON.stringify(message) : message;
        sendLog('error', `Console Error: ${errorMessage}`, { details: optionalParams.join(', ') });
    }
};

window.addEventListener('error', event => {
    if (shouldSendLog('error')) {
        const { message, filename, lineno, colno, error } = event;
        const errorMessage = error ? error.stack : `${message} at ${filename}:${lineno}:${colno}`;
        sendLog('error', `Unhandled Exception: ${errorMessage}`);
    }
});

window.addEventListener('unhandledrejection', event => {
    if (shouldSendLog('error')) {
        const reason = event.reason || 'No reason provided';
        const errorMessage = typeof reason === 'object' ? reason.stack || JSON.stringify(reason) : reason;
        sendLog('error', `Unhandled Promise Rejection: ${errorMessage}`);
    }
});
// -----------------------------

// Clean, simple initialization - no SPA complexity
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');

    if (loginForm) {
        // Login page - simple form handling
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);

            try {
                const response = await fetch(`${API_URL}/auth/token`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData,
                });
                
                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Incorrect Username or Password");
                    }
                    throw new Error(`Login failed: ${response.status}`);
                }
                
                const data = await response.json();
                localStorage.setItem('accessToken', data.access_token);
                const decodedToken = decodeToken(data.access_token);
                if (decodedToken && decodedToken.role) {
                    localStorage.setItem('userRole', decodedToken.role);
                }
                // Standard navigation - no SPA routing
                window.location.href = 'index.html';
                
            } catch (error) {
                showToast(error.message, 'error');
            }
        });
    } else {
        // Protected pages - simple, clean initialization
        checkAuthentication();
        initializePage();
    }
});
