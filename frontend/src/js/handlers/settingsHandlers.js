import { API_URL } from '../config.js';
import { safeFetch, showToast } from '../utils.js';
import { showModal, hideModal, showConfirmationModal } from '../ui.js';
import { fetchUsers, fetchLogLevel, setLogLevel, fetchBackupSettings, saveBackupSettings, backupNow, fetchBackupHistory } from '../api.js';

function populateUserForm(id, username, role) {
    document.getElementById('user-id').value = id;
    document.getElementById('user-username').value = username;
    document.getElementById('user-role').value = role;
    document.getElementById('user-modal-title').textContent = 'Edit User';
    document.getElementById('user-form-submit-btn').textContent = 'Update User';
    document.getElementById('user-password').required = false;
    showModal(document.getElementById('user-modal'));
}

async function deleteUser(id) {
    showConfirmationModal('Are you sure you want to delete this user?', async () => {
        try {
            await safeFetch(`${API_URL}/auth/users/${id}`, { method: 'DELETE' });
            fetchUsers();
            showToast('User deleted successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

function setupUserInteractionHandlers() {
    const usersList = document.getElementById('users-list');
    if (usersList) {
        usersList.addEventListener('click', (e) => {
            const target = e.target.closest('button');
            if (!target) return;

            const { id, username, role } = target.dataset;

            if (target.classList.contains('edit-user-btn')) {
                populateUserForm(id, username, role);
            } else if (target.classList.contains('delete-user-btn')) {
                deleteUser(id);
            }
        });
    }

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
    const addUserBtn = document.getElementById('add-user-btn');
    if (addUserBtn) {
        const newBtn = addUserBtn.cloneNode(true);
        addUserBtn.parentNode.replaceChild(newBtn, addUserBtn);
        newBtn.addEventListener('click', () => {
            document.getElementById('user-form').reset();
            document.getElementById('user-id').value = '';
            document.getElementById('user-modal-title').textContent = 'Add User';
            document.getElementById('user-form-submit-btn').textContent = 'Add User';
            document.getElementById('user-password').required = true;
            showModal(document.getElementById('user-modal'));
        });
    }

    document.getElementById('user-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('user-id').value;
        const url = id ? `${API_URL}/auth/users/${id}` : `${API_URL}/auth/users/`;
        const method = id ? 'PUT' : 'POST';

        const userData = {
            username: document.getElementById('user-username').value,
            role: document.getElementById('user-role').value,
        };

        const password = document.getElementById('user-password').value;
        if (!id && !password) {
            showToast('Password is required for new users.', 'error');
            return;
        }

        if (password) {
            userData.password = password;
        }

        try {
            await safeFetch(url, { method, body: JSON.stringify(userData) });
            hideModal(document.getElementById('user-modal'));
            fetchUsers();
            showToast(`User ${id ? 'updated' : 'added'} successfully!`, 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });

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
        newBtn.addEventListener('click', async () => {
            try {
                const certs = await safeFetch(`${API_URL}/certificates/raw`);
                const modal = document.getElementById('raw-certs-modal');
                const pre = document.getElementById('raw-certs-json');
                pre.textContent = JSON.stringify(certs, null, 2);
                showModal(modal);
            } catch (error) {
                // Error is handled by safeFetch
            }
        });
    }
}

export function initializeSettingsHandlers() {
    // Always re-initialize handlers on page view
    fetchUsers();
    fetchLogLevel();
    fetchBackupSettings();
    fetchBackupHistory();
    setupUserForms();
    setupSettingsButtons();
    setupUserInteractionHandlers();
}