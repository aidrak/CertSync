// Shared layout and navigation - loads instantly
export function initializeSharedLayout() {
    // No dynamic content loading - everything is static HTML
    // Just initialize event handlers for shared components
    
    initializeNavigation();
    initializeSharedModals();
    initializeToastSystem();
}

function initializeNavigation() {
    // Simple navigation - no SPA routing
    const navLinks = document.querySelectorAll('a[data-link]');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            // Let browser handle navigation naturally
            // Remove SPA prevention
        });
    });
    
    // Update active navigation state
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentPage) {
            link.classList.add('active');
        }
    });
}

function initializeSharedModals() {
    // Shared modal behavior - no DOM replacement issues
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('close-btn')) {
            const modal = e.target.closest('.modal');
            if (modal) {
                modal.style.display = 'none';
            }
        }
    });
}

function initializeToastSystem() {
    // Toast system that works across all pages
    if (!document.getElementById('toast-container')) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
}

// Sign out functionality
export function initializeSignOut() {
    const signOutBtn = document.getElementById('sign-out-btn');
    if (signOutBtn) {
        signOutBtn.addEventListener('click', () => {
            localStorage.removeItem('accessToken');
            localStorage.removeItem('userRole');
            window.location.href = 'login.html';
        });
    }
}