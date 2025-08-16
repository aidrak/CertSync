import { API_URL } from '../config.js';
import { safeFetch, showToast } from '../utils.js';
import { showModal, hideModal } from '../ui.js';
import { fetchLogLevel, setLogLevel, fetchBackupSettings, saveBackupSettings, backupNow, fetchBackupHistory } from '../api.js';

function setupUserInteractionHandlers() {
    const changePasswordBtn = document.getElementById('change-password-btn-user');
    if (changePasswordBtn) {
        // Remove existing listeners to prevent duplicates
        const newBtn = changePasswordBtn.cloneNode(true);
        changePasswordBtn.parentNode.replaceChild(newBtn, changePasswordBtn);
        newBtn.addEventListener('click', () => {
            const changePasswordModal = document.getElementById('change-password-modal');
            document.getElementById('change-password-modal-title').textContent = 'Change Your Password';
            document.getElementById('current-password').style.display = 'block';
            document.querySelector('label[for="current-password"]').style.display = 'block';
            document.getElementById('current-password').required = true;
            changePasswordModal.dataset.userId = ''; // Not needed for changing own password
            showModal(changePasswordModal);
        });
    }
}

function setupUserForms() {
    document.getElementById('change-password-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        if (newPassword !== confirmPassword) {
            showToast('Passwords do not match.', 'error');
            return;
        }

        const changePasswordModal = document.getElementById('change-password-modal');
        const userId = changePasswordModal.dataset.userId;

        let url;
        let payload;

        if (userId) {
            // Admin is changing another user's password
            url = `${API_URL}/auth/users/${userId}/password`;
            payload = { password: newPassword };
        } else {
            // User is changing their own password
            url = `${API_URL}/auth/users/me/password`;
            payload = {
                current_password: document.getElementById('current-password').value,
                new_password: newPassword,
            };
        }

        try {
            await safeFetch(url, {
                method: 'PUT',
                body: JSON.stringify(payload),
            });
            hideModal(changePasswordModal);
            showToast('Password changed successfully!', 'success');
            document.getElementById('change-password-form').reset();
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

function setupSettingsButtons() {
    const setLogLevelBtn = document.getElementById('set-log-level-btn');
    if (setLogLevelBtn) {
        // Remove existing listeners to prevent duplicates
        const newBtn = setLogLevelBtn.cloneNode(true);
        setLogLevelBtn.parentNode.replaceChild(newBtn, setLogLevelBtn);
        newBtn.addEventListener('click', setLogLevel);
    }

    const saveBackupSettingsBtn = document.getElementById('save-backup-settings-btn');
    if (saveBackupSettingsBtn) {
        const newBtn = saveBackupSettingsBtn.cloneNode(true);
        saveBackupSettingsBtn.parentNode.replaceChild(newBtn, saveBackupSettingsBtn);
        newBtn.addEventListener('click', async () => {
            const settings = {
                backup_enabled: document.getElementById('backup-enabled').checked,
                backup_frequency: document.getElementById('backup-frequency').value,
                backup_time: document.getElementById('backup-time').value,
                backup_retention_days: parseInt(document.getElementById('backup-retention').value, 10),
                backup_location: document.getElementById('backup-location').value,
            };
            await saveBackupSettings(settings);
        });
    }

    const backupNowBtn = document.getElementById('backup-now-btn');
    if (backupNowBtn) {
        const newBtn = backupNowBtn.cloneNode(true);
        backupNowBtn.parentNode.replaceChild(newBtn, backupNowBtn);
        newBtn.addEventListener('click', async () => {
            await backupNow();
            fetchBackupHistory();
        });
    }

    const viewAllCertsBtn = document.getElementById('view-all-certs-btn');
    if (viewAllCertsBtn) {
        const newBtn = viewAllCertsBtn.cloneNode(true);
        viewAllCertsBtn.parentNode.replaceChild(newBtn, viewAllCertsBtn);
        newBtn.addEventListener('click', () => {
            window.location.href = '/certificates.html';
        });
    }
}

export function initializeSettingsHandlers() {
    // Always re-initialize handlers on page view
    fetchLogLevel();
    fetchBackupSettings();
    fetchBackupHistory();
    setupUserForms();
    setupSettingsButtons();
    setupUserInteractionHandlers();
}
