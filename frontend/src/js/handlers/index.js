import { initializeTargetSystemHandlers } from './targetSystemHandlers.js';
import { initializeCertificateHandlers } from './certificateHandlers.js';
import { initializeDnsHandlers } from './dnsHandlers.js';
import { initializeSettingsHandlers } from './settingsHandlers.js';
import { initializeDeploymentHandlers } from './deploymentHandlers.js';
import { showModal, hideModal } from '../ui.js';
import { fetchDashboardStats, fetchTargetSystems } from '../api.js';

function initializeGenericHandlers() {
    // Use event delegation for sign-out and close buttons
    document.body.addEventListener('click', (e) => {
        if (e.target.id === 'sign-out-btn') {
            localStorage.removeItem('accessToken');
            window.location.href = 'login.html';
        }

        if (e.target.classList.contains('close-btn')) {
            const modal = e.target.closest('.modal');
            if (modal) {
                hideModal(modal);
            }
        }
    });
}

let handlersInitialized = false;

export function initializeAllHandlers() {
    // Always reinitialize handlers for router navigation
    // but prevent duplicate generic handlers
    if (!handlersInitialized) {
        initializeGenericHandlers();
        handlersInitialized = true;
    }
    
    // These need to be reinitialized on each page navigation
    initializeTargetSystemHandlers();
    initializeCertificateHandlers();
    initializeDnsHandlers();
    initializeSettingsHandlers();
    initializeDeploymentHandlers();
}
