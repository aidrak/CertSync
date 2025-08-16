import { API_URL } from '../config.js';
import { safeFetch, showToast } from '../utils.js';
import { showModal, hideModal } from '../ui.js';
import { fetchUsers } from '../api.js';

function populateUserForm(id, username, role) {
    document.getElementById('user-id').value = id;
    document.getElementById('user-username').value = username;
    document.getElementById('user-role').value = role;
    document.getElementById('user-modal-title').textContent = 'Edit User';
    document.getElementById('user-form-submit-btn').textContent = 'Update User';
    document.getElementById('user-password').required = false;
    showModal(document.getElementById('add-user-modal'));
}

async function deleteUser(id) {
    if (confirm('Are you sure you want to delete this user?')) {
        try {
            await safeFetch(`${API_URL}/auth/users/${id}`, { method: 'DELETE' });
            fetchUsers();
            showToast('User deleted successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    }
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
            } else if (target.classList.contains('change-password-btn')) {
                const changePasswordModal = document.getElementById('change-password-modal');
                document.getElementById('change-password-modal-title').textContent = 'Set User Password';
                document.getElementById('current-password').style.display = 'none';
                document.querySelector('label[for="current-password"]').style.display = 'none';
                document.getElementById('current-password').required = false;
                changePasswordModal.dataset.userId = id;
                showModal(changePasswordModal);
            }
        });
    }
}

function setupUserForms() {
    const addUserBtn = document.getElementById('add-user-btn');
    if (addUserBtn) {
        const newBtn = addUserBtn.cloneNode(true);
        addUserBtn.parentNode.replaceChild(newBtn, addUserBtn);
        newBtn.addEventListener('click', () => {
            document.getElementById('add-user-form').reset();
            document.getElementById('user-id').value = '';
            document.getElementById('user-modal-title').textContent = 'Add User';
            document.getElementById('user-form-submit-btn').textContent = 'Add User';
            document.getElementById('user-password').required = true;
            showModal(document.getElementById('add-user-modal'));
        });
    }

    document.getElementById('add-user-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('user-id').value;
        const url = id ? `${API_URL}/auth/users/${id}` : `${API_URL}/auth/users/`;
        const method = id ? 'PUT' : 'POST';

        const userData = {
            username: document.getElementById('user-username').value,
            role: document.getElementById('user-role').value,
        };

        const password = document.getElementById('user-password').value;
        if (password) {
            userData.password = password;
        }

        try {
            await safeFetch(url, { method, body: JSON.stringify(userData) });
            hideModal(document.getElementById('add-user-modal'));
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
            url = `${API_URL}/auth/users/${userId}/password`;
            payload = { password: newPassword };
        } else {
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

export function initializeUserHandlers() {
    fetchUsers();
    setupUserForms();
    setupUserInteractionHandlers();
}
