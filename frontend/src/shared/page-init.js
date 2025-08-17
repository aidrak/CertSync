// Page-specific initialization - no dynamic routing
import { initializeSharedLayout, initializeSignOut } from './layout.js';
import { fetchDashboardStats, fetchTargetSystems, fetchCertificates, fetchDnsProviders, fetchLogs, fetchUsers, fetchLogLevel, fetchDeployments, fetchBackupSettings, fetchBackupHistory } from '../js/api.js';
import { initializeAllHandlers } from '../js/handlers/index.js';

export function initializePage() {
    // Always initialize shared layout first
    initializeSharedLayout();
    initializeSignOut();
    
    // Initialize all handlers once
    initializeAllHandlers();
    
    // Initialize page-specific content based on current page
    const currentPage = getCurrentPageName();
    initializePageContent(currentPage);
}

function getCurrentPageName() {
    const path = window.location.pathname;
    const page = path.split('/').pop() || 'index.html';
    return page.replace('.html', '');
}

function initializePageContent(pageName) {
    // Load data for specific pages - no template fetching!
    switch (pageName) {
        case 'index':
        case '':
            fetchDashboardStats();
            fetchTargetSystems();
            break;
            
        case 'dns':
            fetchDnsProviders();
            break;
            
        case 'certificates':
            fetchCertificates();
            break;
            
        case 'target_systems':
            fetchTargetSystems();
            break;
            
        case 'deployments':
            fetchDeployments();
            break;
            
        case 'logs':
            fetchLogs();
            break;

        case 'users':
            fetchUsers();
            break;
            
        case 'settings':
            fetchUsers();
            fetchLogLevel();
            fetchBackupSettings();
            fetchBackupHistory();
            break;
    }
}

// Authentication check - runs once per page load
export function checkAuthentication() {
    // Skip auth check for login page
    if (window.location.pathname.includes('login.html')) {
        return;
    }
    
    const token = localStorage.getItem('accessToken');
    if (!token) {
        window.location.href = 'login.html';
        return;
    }
    
    // Set user role visibility
    const userRole = localStorage.getItem('userRole');
    if (userRole === 'readonly') {
        document.body.classList.add('readonly');
    }

    if (userRole !== 'admin') {
        document.querySelectorAll('.admin-only').forEach(el => {
            el.style.display = 'none';
        });

        // Redirect if a non-admin tries to access the users page
        if (window.location.pathname.includes('users.html')) {
            window.location.href = 'index.html';
        }
    }
}
