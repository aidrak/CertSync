import { API_URL } from '../config.js';
import { safeFetch, showToast } from '../utils.js';
import { showModal, hideModal, showConfirmationModal } from '../ui.js';
import { fetchUsers } from '../api.js';

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
}

export function initializeUserHandlers() {
    fetchUsers();
    setupUserForms();
    setupUserInteractionHandlers();
}