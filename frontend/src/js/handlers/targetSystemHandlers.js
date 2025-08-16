import { API_URL } from '../config.js';
import { safeFetch, showToast, formatVendorName, safeEventSource } from '../utils.js';
import {
    showModal, hideModal, updateApiKeyFieldLabel, showVendorSpecificInfo,
    createTestProgressDisplay, updateTestStep, clearTestProgressDisplay
} from '../ui.js';
import { fetchTargetSystems, fetchDnsProviders } from '../api.js';

async function populateCompanyDropdown(selectElementId) {
    const selectElement = document.getElementById(selectElementId);
    if (!selectElement) return;

    try {
        const dnsProviders = await fetchDnsProviders();
        const companies = [...new Set(dnsProviders.map(provider => provider.company))];
        
        selectElement.innerHTML = '<option value="">Select Company</option>';
        companies.forEach(company => {
            const option = document.createElement('option');
            option.value = company;
            option.textContent = company;
            selectElement.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to populate company dropdown:', error);
    }
}

function updateNameField(isEdit = false) {
    const prefix = isEdit ? 'edit-' : '';
    const type = document.getElementById(`${prefix}ts-type`).value;
    const nameLabel = document.querySelector(`label[for="${prefix}ts-name"]`);
    const nameInput = document.getElementById(`${prefix}ts-name`);

    if (nameLabel && nameInput) {
        if (['fortigate', 'panos', 'sonicwall'].includes(type)) {
            nameLabel.textContent = 'Firewall Name:';
            nameInput.placeholder = 'Ex. Cambridge-FW-01';
        } else {
            nameLabel.textContent = 'System Name:';
            nameInput.placeholder = '';
        }
    }
}

function setupAddTargetSystemModal() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.id === 'add-target-system-btn') {
            const addTargetSystemModal = document.getElementById('add-target-system-modal');
            document.getElementById('add-target-system-form')?.reset();
            resetTestConnectionButton();
            resetModalSize();
            await populateCompanyDropdown('ts-company');
            updateApiKeyFieldLabel();
            showVendorSpecificInfo();
            updateNameField(false);
            showModal(addTargetSystemModal);
        }
    });

    // Handle modal close events to reset button state and modal size
    document.body.addEventListener('click', (e) => {
        // Handle close button (×) clicks
        if (e.target.classList.contains('close-btn')) {
            const modal = e.target.closest('.modal');
            if (modal && modal.id === 'add-target-system-modal') {
                resetTestConnectionButton();
                resetModalSize();
            }
        }
        
        // Removed: clicks outside modal no longer close it
    });

    // Removed: ESC key no longer closes modal

    document.body.addEventListener('change', (e) => {
        if (e.target.id === 'ts-type' || e.target.id === 'edit-ts-type') {
            const isEdit = e.target.id === 'edit-ts-type';
            updateNameField(isEdit);
            updateApiKeyFieldLabel();
            if (!isEdit) {
                showVendorSpecificInfo();
            }
        }
    });
}

function resetTestConnectionButton() {
    const button = document.getElementById('test-connection-btn');
    if (button) {
        button.textContent = 'Test Connection';
        button.disabled = false;
        if (button.dataset.targetSystemData) {
            delete button.dataset.targetSystemData;
        }
    }
    
    // Close any active EventSource connection
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
}

function resetModalSize() {
    // Clear any test progress display and reset modal size
    clearTestProgressDisplay();
}

function setupTestConnectionButton() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.id !== 'test-connection-btn') return;
        const button = e.target;
        const type = document.getElementById('ts-type').value;
        
        const targetSystemData = {
            company: document.getElementById('ts-company').value,
            system_name: document.getElementById('ts-name').value,
            system_type: type,
            public_ip: document.getElementById('ts-public-ip').value,
            port: parseInt(document.getElementById('ts-port').value, 10),
            api_key: '' // Default to empty string
        };

        if (type === 'sonicwall') {
            targetSystemData.admin_username = document.getElementById('ts-admin-username').value;
            targetSystemData.admin_password = document.getElementById('ts-admin-password').value;
        } else {
            targetSystemData.api_key = document.getElementById('ts-api-key').value;
        }

        if (button.textContent === 'Test Connection') {
            const existingTargetSystems = await fetchTargetSystems();
            if (existingTargetSystems.some(ts => ts.system_name === targetSystemData.system_name)) {
                showToast('A target system with this name already exists.', 'error');
                return;
            }
            createTestProgressDisplay('add-target-system-modal');
            updateTestStep(`Connecting to ${formatVendorName(type)}...`, 'running');
            button.disabled = true;
            button.textContent = 'Testing...';

            const testData = { ...targetSystemData };
            let sseEndpoint;

            // Route to type-specific endpoint and prepare appropriate parameters
            if (type === 'sonicwall') {
                delete testData.api_key;
                delete testData.system_type;
                sseEndpoint = `${API_URL}/target-systems/test_connection_sse/sonicwall`;
                
            } else if (type === 'fortigate' || type === 'panos') {
                delete testData.admin_username;
                delete testData.admin_password;
                delete testData.system_type;
                sseEndpoint = `${API_URL}/target-systems/test_connection_sse/${type}`;
                
            } else {
                showToast(`Unknown target system type: ${type}`, 'error');
                button.textContent = 'Test Connection';
                button.disabled = false;
                return;
            }

            const queryParams = new URLSearchParams(testData).toString();
            currentEventSource = safeEventSource(`${sseEndpoint}?${queryParams}`);

            currentEventSource.onmessage = function(event) {
                const log = event.data;
                let status = 'info';
                if (log.includes('✅')) status = 'success';
                if (log.includes('❌')) status = 'error';
                updateTestStep(log, status);

                if (log.includes("SUCCESS: Complete certificate workflow validated!")) {
                    updateTestStep('✅ Validation successful!', 'success');
                    button.textContent = 'Save Target System';
                    button.disabled = false;
                    button.dataset.targetSystemData = JSON.stringify(targetSystemData);
                } else if (log.includes("###CLOSE###")) {
                    // Stream ended, check if test was successful
                    if (button.textContent !== 'Save Target System') {
                        resetTestConnectionButton();
                    }
                }
            };

            currentEventSource.onerror = function(error) {
                console.error('EventSource failed:', error);
                updateTestStep(`❌ Error: Connection failed or stream ended.`, 'error');
                resetTestConnectionButton();
                // Removed: modal no longer auto-closes on error
            };

        } else if (button.textContent === 'Save Target System') {
            try {
                const storedData = JSON.parse(button.dataset.targetSystemData);
                // Ensure company field is included
                if (!storedData.company) {
                    storedData.company = document.getElementById('ts-company').value;
                }
                console.log('Saving target system data:', storedData);
                await safeFetch(`${API_URL}/target-systems/`, {
                    method: 'POST',
                    body: JSON.stringify(storedData)
                });

                updateTestStep('✅ Target system saved successfully!', 'success');
                setTimeout(() => {
                    hideModal(document.getElementById('add-target-system-modal'));
                    fetchTargetSystems();
                    clearTestProgressDisplay();
                    showToast('Target system added successfully!', 'success');
                    button.textContent = 'Test Connection';
                    button.disabled = false;
                }, 1500);

            } catch (error) {
                updateTestStep(`❌ Error saving target system: ${error.message}`, 'error');
            }
        }
    });
}

function setupEditTargetSystemForm() {
    document.body.addEventListener('submit', async (e) => {
        if (e.target.id !== 'edit-target-system-form') return;
        e.preventDefault();
        const targetSystemId = document.getElementById('edit-ts-id').value;
        const type = document.getElementById('edit-ts-type').value;
        const formData = {
            system_name: document.getElementById('edit-ts-name').value,
            system_type: type,
            public_ip: document.getElementById('edit-ts-public-ip').value,
            port: parseInt(document.getElementById('edit-ts-port').value, 10),
        };
        
        const apiKey = document.getElementById('edit-ts-api-key').value;
        if (apiKey) {
            formData.api_key = apiKey;
        }
        
        if (type === 'sonicwall') {
            formData.admin_username = document.getElementById('edit-ts-admin-username').value;
            const adminPassword = document.getElementById('edit-ts-admin-password').value;
            if (adminPassword) {
                formData.admin_password = adminPassword;
            }
        }

        try {
            await safeFetch(`${API_URL}/target-systems/${targetSystemId}`, { method: 'PUT', body: JSON.stringify(formData) });
            hideModal(document.getElementById('edit-target-system-modal'));
            fetchTargetSystems();
            showToast('Target system updated successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

function setupTargetSystemDynamicEventListeners() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.classList.contains('edit-ts-btn')) {
            const targetSystemId = e.target.dataset.id;
            try {
                const targetSystems = await safeFetch(`${API_URL}/target-systems/`);
                const targetSystem = targetSystems.find(ts => ts.id == targetSystemId);
                if (targetSystem) {
                    await populateCompanyDropdown('edit-ts-company');
                    document.getElementById('edit-ts-id').value = targetSystem.id;
                    document.getElementById('edit-ts-type').value = targetSystem.system_type;
                    document.getElementById('edit-ts-name').value = targetSystem.system_name;
                    document.getElementById('edit-ts-public-ip').value = targetSystem.public_ip;
                    document.getElementById('edit-ts-port').value = targetSystem.port;
                    document.getElementById('edit-ts-api-key').value = '';
                    
                    showVendorSpecificInfo();
                    if (targetSystem.system_type === 'sonicwall') {
                        document.getElementById('edit-ts-admin-username').value = targetSystem.admin_username || '';
                    }
                    
                    updateNameField(true);
                    showModal(document.getElementById('edit-target-system-modal'));
                }
            } catch (error) {
                // Error is handled by safeFetch
            }
        }

        if (e.target.classList.contains('delete-ts-btn')) {
            const targetSystemId = e.target.dataset.id;
            if (confirm('Are you sure you want to delete this target system?')) {
                try {
                    await safeFetch(`${API_URL}/target-systems/${targetSystemId}`, { method: 'DELETE' });
                    fetchTargetSystems();
                    showToast('Target system deleted successfully!', 'success');
                } catch (error) {
                    // Error is handled by safeFetch
                }
            }
        }
    });
}

let targetSystemHandlersInitialized = false;
let currentEventSource = null;

export function initializeTargetSystemHandlers() {
    if (targetSystemHandlersInitialized) return;
    targetSystemHandlersInitialized = true;
    
    setupAddTargetSystemModal();
    setupTestConnectionButton();
    setupEditTargetSystemForm();
    setupTargetSystemDynamicEventListeners();
    document.getElementById('edit-ts-type')?.addEventListener('change', updateApiKeyFieldLabel);
}
