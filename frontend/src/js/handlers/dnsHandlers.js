import { API_URL } from '../config.js';
import { safeFetch, showToast } from '../utils.js';
import {
    showModal, hideModal,
    createTestProgressDisplay, updateTestStep, clearTestProgressDisplay,
    updateDnsCredentialsFields, updateEditDnsCredentialsFields, showConfirmationModal
} from '../ui.js';
import { fetchDnsProviders } from '../api.js';

function resetTestCredentialsButton() {
    const button = document.getElementById('test-dns-credentials-btn');
    if (button) {
        button.textContent = 'Test Credentials';
        button.disabled = false;
        if (button.dataset.credentials) {
            delete button.dataset.credentials;
        }
    }
}

function resetModalSize() {
    clearTestProgressDisplay();
}

function setupAddDnsAccountModal() {
    console.log('setupAddDnsAccountModal called');
    // Use event delegation for the add button
    document.body.addEventListener('click', (e) => {
        if (e.target.id === 'add-dns-account-btn') {
            console.log('Add DNS account button clicked');
            const addDnsAccountModal = document.getElementById('add-dns-account-modal');
            if (addDnsAccountModal) {
                document.getElementById('add-dns-account-form')?.reset();
                resetTestCredentialsButton();
                resetModalSize();
                updateDnsCredentialsFields();
                showModal(addDnsAccountModal);
            } else {
                console.log('Modal not found');
            }
        }
    });

    // Handle modal close events to reset button state and modal size
    document.body.addEventListener('click', (e) => {
        // Handle close button (×) clicks
        if (e.target.classList.contains('close-btn')) {
            const modal = e.target.closest('.modal');
            if (modal && modal.id === 'add-dns-account-modal') {
                resetTestCredentialsButton();
                resetModalSize();
            }
        }
        
        // Removed: clicks outside modal no longer close it
    });

    // Removed: ESC key no longer closes modal

    // Use event delegation for provider select changes
    document.body.addEventListener('change', (e) => {
        if (e.target.id === 'dns-account-provider') {
            updateDnsCredentialsFields();
        } else if (e.target.id === 'edit-dns-account-provider') {
            updateEditDnsCredentialsFields();
        }
    });
}

function setupTestDnsCredentialsButton() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.id !== 'test-dns-credentials-btn') return;
        const button = e.target;
        const provider = document.getElementById('dns-account-provider').value;
        let credentials = {};

        if (provider === 'cloudflare') {
            credentials.token = document.getElementById('cred-cloudflare-token').value;
        } else if (provider === 'digitalocean') {
            credentials.token = document.getElementById('cred-digitalocean-token').value;
        }

        const accountData = {
            managed_domain: document.getElementById('dns-account-domain').value,
            provider_type: provider,
            credentials: credentials,
            company: document.getElementById('dns-account-company').value
        };

        if (button.textContent === 'Test Credentials') {
            try {
                createTestProgressDisplay('add-dns-account-modal');
                updateTestStep('Validating credentials...', 'running');
                button.disabled = true;
                button.textContent = 'Testing...';

                await safeFetch(`${API_URL}/dns/dns-provider-accounts/test`, {
                    method: 'POST',
                    body: JSON.stringify(accountData)
                });

                updateTestStep('✅ All tests passed!', 'success');
                button.textContent = 'Save Account';
                button.disabled = false;
                
                button.dataset.credentials = JSON.stringify(accountData);

            } catch (error) {
                updateTestStep(`❌ Error: ${error.message}`, 'error');
                resetTestCredentialsButton();
            }
        } else if (button.textContent === 'Save Account') {
            try {
                const storedData = JSON.parse(button.dataset.credentials);
                
                const createData = {
                    ...storedData,
                    credentials: JSON.stringify(storedData.credentials)
                };

                await safeFetch(`${API_URL}/dns/dns-provider-accounts/`, {
                    method: 'POST',
                    body: JSON.stringify(createData)
                });

                updateTestStep('✅ DNS account created successfully!', 'success');
                setTimeout(() => {
                    hideModal(document.getElementById('add-dns-account-modal'));
                    fetchDnsProviders();
                    clearTestProgressDisplay();
                    showToast('DNS Provider Account added successfully!', 'success');
                    button.textContent = 'Test Credentials';
                    button.disabled = false;
                }, 1500);

            } catch (error) {
                updateTestStep(`❌ Error saving account: ${error.message}`, 'error');
            }
        }
    });
}

function setupEditDnsAccountForm() {
    document.body.addEventListener('submit', async (e) => {
        if (e.target.id !== 'edit-dns-account-form') return;
        e.preventDefault();
        const accountId = document.getElementById('edit-dns-account-id').value;
        const provider = document.getElementById('edit-dns-account-provider').value;
        let credentials = {};

        if (provider === 'cloudflare') {
            credentials.token = document.getElementById('edit-cred-cloudflare-token').value;
        } else if (provider === 'digitalocean') {
            credentials.token = document.getElementById('edit-cred-digitalocean-token').value;
        }

        const accountData = {
            managed_domain: document.getElementById('edit-dns-account-domain').value,
            provider_type: provider,
            credentials: JSON.stringify(credentials),
            company: document.getElementById('edit-dns-account-company').value
        };

        try {
            await safeFetch(`${API_URL}/dns/dns-provider-accounts/${accountId}`, { method: 'PUT', body: JSON.stringify(accountData) });
            hideModal(document.getElementById('edit-dns-account-modal'));
            fetchDnsProviders();
            showToast('DNS Provider Account updated successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

function setupDnsDynamicEventListeners() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.classList.contains('edit-dns-btn')) {
            const accountId = e.target.dataset.id;
            try {
                const accounts = await safeFetch(`${API_URL}/dns/dns-provider-accounts/`);
                const account = accounts.find(acc => acc.id == accountId);
                if (account) {
                    document.getElementById('edit-dns-account-id').value = account.id;
                    document.getElementById('edit-dns-account-domain').value = account.domain;
                    document.getElementById('edit-dns-account-provider').value = account.provider_type;
                    document.getElementById('edit-dns-account-company').value = account.company;
                    updateEditDnsCredentialsFields();
                    showModal(document.getElementById('edit-dns-account-modal'));
                }
            } catch (error) {
                // Errors are handled by safeFetch
            }
        }

        if (e.target.classList.contains('delete-dns-btn')) {
            const accountId = e.target.dataset.id;
            showConfirmationModal('Are you sure you want to delete this DNS provider account?', async () => {
                try {
                    await safeFetch(`${API_URL}/dns/dns-provider-accounts/${accountId}`, { method: 'DELETE' });
                    fetchDnsProviders();
                    showToast('DNS Provider Account deleted successfully!', 'success');
                } catch (error) {
                    // Error is handled by safeFetch
                }
            });
        }
    });
}

let dnsHandlersInitialized = false;

export function initializeDnsHandlers() {
    if (dnsHandlersInitialized) return;
    dnsHandlersInitialized = true;
    
    setupAddDnsAccountModal();
    setupTestDnsCredentialsButton();
    setupEditDnsAccountForm();
    setupDnsDynamicEventListeners();
}