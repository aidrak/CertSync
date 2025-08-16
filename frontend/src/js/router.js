import { fetchDashboardStats, fetchTargetSystems, fetchCertificates, fetchDnsProviders, fetchLogs, fetchUsers, fetchLogLevel, fetchDeployments, fetchBackupSettings, fetchBackupHistory } from './api.js';
import { initializeAllHandlers } from './handlers/index.js';
import { initializeUserHandlers } from './handlers/userHandlers.js';

const routes = {
    '/index.html': {
        template: 'index.html',
        title: 'Dashboard',
        init: () => {
            fetchDashboardStats();
            fetchTargetSystems();
        }
    },
    '/': {
        template: 'index.html',
        title: 'Dashboard',
        init: () => {
            fetchDashboardStats();
            fetchTargetSystems();
        }
    },
    '/dns.html': {
        template: 'dns.html',
        title: 'DNS Providers',
        init: fetchDnsProviders
    },
    '/certificates.html': {
        template: 'certificates.html',
        title: 'Certificates',
        init: fetchCertificates
    },
    '/target_systems.html': {
        template: 'target_systems.html',
        title: 'Target Systems',
        init: fetchTargetSystems
    },
    '/deployments.html': {
        template: 'deployments.html',
        title: 'Deployments',
        init: fetchDeployments
    },
    '/logs.html': {
        template: 'logs.html',
        title: 'Logs',
        init: fetchLogs
    },
    '/settings.html': {
        template: 'settings.html',
        title: 'Settings',
        init: () => {
            fetchLogLevel();
            fetchBackupSettings();
            fetchBackupHistory();
        }
    },
    '/users.html': {
        template: 'users.html',
        title: 'Users',
        init: initializeUserHandlers
    }
};

const navigateTo = (url) => {
    history.pushState(null, null, new URL(url).pathname);
    router();
};

const router = async () => {
    const path = window.location.pathname;
    const route = routes[path] || routes['/'];

    try {
        const response = await fetch(route.template);
        if (!response.ok) {
            throw new Error(`Failed to fetch template: ${response.status}`);
        }
        const html = await response.text();
        
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        
        // Replace main content
        const mainContent = doc.querySelector('.main-content');
        const currentMainContent = document.querySelector('.main-content');
        if (mainContent && currentMainContent) {
            currentMainContent.innerHTML = mainContent.innerHTML;
        }

        // Remove old modals to prevent duplicates
        document.querySelectorAll('.modal').forEach(modal => {
            modal.remove();
        });

        // Append new modals from the fetched page to the body
        doc.querySelectorAll('.modal').forEach(modal => {
            document.body.appendChild(modal);
        });

        document.title = `CertSync - ${route.title}`;

        // Reinitialize handlers after content is loaded
        initializeAllHandlers();

        if (route.init) {
            route.init();
        }

        updateNavLinks();
    } catch (error) {
        console.error('Error during routing:', error);
    }
};

const updateNavLinks = () => {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-links a').forEach(link => {
        if (link.pathname === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
};

export const initializeRouter = () => {
    document.addEventListener('click', (e) => {
        if (e.target.matches('[data-link]')) {
            e.preventDefault();
            navigateTo(e.target.href);
        }
    });

    window.addEventListener('popstate', router);
    
    // Call router immediately since DOMContentLoaded has already fired
    router();
};
