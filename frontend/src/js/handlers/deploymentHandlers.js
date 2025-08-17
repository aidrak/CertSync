import { API_URL } from '../config.js';
import { safeFetch, showToast, safeEventSource } from '../utils.js';
import { showModal, hideModal, updateTestStep, showConfirmationModal } from '../ui.js';
import { fetchCertificates, fetchTargetSystems, fetchDeployments, fetchCompanies, fetchCertificatesByCompany, fetchTargetSystemsByCompany, createDeployment, verifyVpnDeployment, getDeployment, updateDeployment, renewCertificate } from '../api.js';

async function populateSelectWithOptions(selectElementId, fetchData, optionTextFormatter) {
    const selectElement = document.getElementById(selectElementId);
    if (!selectElement) return;

    try {
        const items = await fetchData();
        selectElement.innerHTML = `<option value="">Select ${selectElementId.split('-')[1]}</option>`;
        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = optionTextFormatter(item);
            selectElement.appendChild(option);
        });
    } catch (error) {
        console.error(`Failed to populate ${selectElementId}:`, error);
    }
}

async function populateCompanyDropdown() {
    const companySelect = document.getElementById('deployment-company');
    if (!companySelect) return;

    try {
        const companies = await fetchCompanies();
        companySelect.innerHTML = '<option value="">Select Company</option>';
        companies.forEach(company => {
            const option = document.createElement('option');
            option.value = company;
            option.textContent = company;
            companySelect.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to populate companies:', error);
    }
}

async function populateCertificateDropdown(company) {
    const certificateSelect = document.getElementById('deployment-certificate');
    if (!certificateSelect) return;

    if (!company) {
        certificateSelect.innerHTML = '<option value="">Select Certificate</option>';
        certificateSelect.disabled = true;
        return;
    }

    try {
        const certificates = await fetchCertificatesByCompany(company);
        certificateSelect.innerHTML = '<option value="">Select Certificate</option>';
        certificates.forEach(cert => {
            const option = document.createElement('option');
            option.value = cert.id;
            option.textContent = cert.common_name;
            certificateSelect.appendChild(option);
        });
        certificateSelect.disabled = false;
    } catch (error) {
        console.error('Failed to populate certificates:', error);
        certificateSelect.disabled = true;
    }
}

async function populateTargetSystemDropdown(company) {
    const targetSystemSelect = document.getElementById('deployment-target-system');
    if (!targetSystemSelect) return;

    if (!company) {
        targetSystemSelect.innerHTML = '<option value="">Select Target System</option>';
        targetSystemSelect.disabled = true;
        return;
    }

    try {
        const targetSystems = await fetchTargetSystemsByCompany(company);
        targetSystemSelect.innerHTML = '<option value="">Select Target System</option>';
        targetSystems.forEach(ts => {
            const option = document.createElement('option');
            option.value = ts.id;
            option.textContent = ts.system_name;
            targetSystemSelect.appendChild(option);
        });
        targetSystemSelect.disabled = false;
    } catch (error) {
        console.error('Failed to populate target systems:', error);
        targetSystemSelect.disabled = true;
    }
}

function setupAddDeploymentModal() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.id === 'add-deployment-btn') {
            const addDeploymentModal = document.getElementById('add-deployment-modal');
            document.getElementById('add-deployment-form')?.reset();
            
            // Reset the form to initial state
            document.getElementById('deployment-certificate').disabled = true;
            document.getElementById('deployment-target-system').disabled = true;
            document.getElementById('deployment-auto-renewal').checked = true;
            
            await populateCompanyDropdown();
            const company = document.getElementById('deployment-company').value;
            await Promise.all([
                populateCertificateDropdown(company),
                populateTargetSystemDropdown(company)
            ]);
            showModal(addDeploymentModal);
        }
    });
}

function setupCompanyChangeHandler() {
    document.body.addEventListener('change', async (e) => {
        if (e.target.id === 'deployment-company') {
            const company = e.target.value;
            await Promise.all([
                populateCertificateDropdown(company),
                populateTargetSystemDropdown(company)
            ]);
        }
    });
}

function setupAddDeploymentForm() {
    const form = document.getElementById('add-deployment-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const certificateId = document.getElementById('deployment-certificate').value;
        const targetSystemId = document.getElementById('deployment-target-system').value;
        const autoRenewalEnabled = document.getElementById('deployment-auto-renewal').checked;

        // Basic validation
        if (!certificateId || !targetSystemId) {
            showToast('Please select both certificate and target system', 'error');
            return;
        }

        try {
            await createDeployment(certificateId, targetSystemId, autoRenewalEnabled);
            hideModal(document.getElementById('add-deployment-modal'));
            await fetchDeployments();
            showToast('Deployment added successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

function setupDeploymentDynamicEventListeners() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.classList.contains('deploy-btn')) {
            const deploymentId = e.target.dataset.id;
            const button = e.target;
            const originalText = button.textContent;
            
            try {
                button.textContent = 'Deploying...';
                button.disabled = true;
                
                // Clear previous progress and show modal
                const progressList = document.getElementById('deployment-progress-list');
                if (progressList) {
                    progressList.innerHTML = '';
                }
                const progressModal = document.getElementById('deployment-progress-modal');
                showModal(progressModal);
                
                // Create SSE connection for real-time deployment progress
                const eventSource = safeEventSource(`${API_URL}/deploy/${deploymentId}/run-sse`);
                
                eventSource.onmessage = function(event) {
                    const rawData = event.data;
                    const message = rawData.startsWith('data:') ? rawData.substring(5).trim() : rawData.trim();
                    
                    if (!message) return;
                    
                    console.log('Deployment progress:', message);
                    
                    // Determine status based on message content
                    let status = 'info';
                    if (message.includes('✅') || message.includes('🎉')) status = 'success';
                    if (message.includes('❌') || message.includes('💔')) status = 'error';
                    if (message.includes('⚠️')) status = 'warning';
                    if (message.includes('🚀') || message.includes('🔐') || message.includes('📤') || message.includes('📥') || message.includes('🔧') || message.includes('💾') || message.includes('🔍')) status = 'running';
                    
                    // Update progress display
                    updateTestStep(message, status);
                    
                    // Update button text with current progress (simplified)
                    if (message.includes('🔐')) {
                        button.textContent = 'Authenticating...';
                    } else if (message.includes('📤')) {
                        button.textContent = 'Uploading...';
                    } else if (message.includes('📥')) {
                        button.textContent = 'Importing...';
                    } else if (message.includes('🔧')) {
                        button.textContent = 'Configuring...';
                    } else if (message.includes('💾')) {
                        button.textContent = 'Saving...';
                    } else if (message.includes('🔍')) {
                        button.textContent = 'Verifying...';
                    }
                };
                
                eventSource.onopen = function() {
                    console.log('Deployment SSE connection opened');
                };
                
                eventSource.onerror = function(event) {
                    console.error('Deployment SSE error:', event);
                    eventSource.close();
                    button.textContent = originalText;
                    button.disabled = false;
                    showToast('Deployment connection error', 'error');
                };
                
                // Handle completion
                eventSource.addEventListener('error', function() {
                    eventSource.close();
                });
                
                // Listen for completion messages
                const originalOnMessage = eventSource.onmessage;
                eventSource.onmessage = function(event) {
                    originalOnMessage(event);
                    
                    const rawData = event.data;
                    const message = rawData.startsWith('data:') ? rawData.substring(5).trim() : rawData.trim();
                    
                    if (message.includes('🎉') && message.includes('completed successfully')) {
                        eventSource.close();
                        button.textContent = originalText;
                        button.disabled = false;
                        showToast('SSL VPN certificate deployment completed successfully!', 'success');
                        fetchDeployments(); // Refresh the table
                    } else if (message.includes('💔') || message.includes('FAILED')) {
                        eventSource.close();
                        button.textContent = originalText;
                        button.disabled = false;
                        showToast('SSL VPN certificate deployment failed', 'error');
                        fetchDeployments(); // Refresh the table
                    }
                };
                
            } catch (error) {
                console.error('Deployment error:', error);
                button.textContent = originalText;
                button.disabled = false;
                showToast('Deployment failed to start', 'error');
            }
        }

        if (e.target.classList.contains('verify-vpn-btn')) {
            const deploymentId = e.target.dataset.id;
            const button = e.target;
            const originalText = button.textContent;
            
            try {
                button.textContent = 'Verifying...';
                button.disabled = true;
                
                // Create SSE connection for real-time verification progress
                const eventSource = safeEventSource(`${API_URL}/deploy/${deploymentId}/verify-vpn-sse`);
                
                eventSource.onmessage = function(event) {
                    const message = event.data;
                    console.log('Verification progress:', message);
                    
                    // Update button text based on verification step
                    if (message.includes('🔐')) {
                        button.textContent = 'Authenticating...';
                    } else if (message.includes('🔍')) {
                        button.textContent = 'Checking...';
                    } else if (message.includes('📋')) {
                        button.textContent = 'Validating...';
                    }
                };
                
                eventSource.onopen = function() {
                    console.log('Verification SSE connection opened');
                };
                
                eventSource.onerror = function(event) {
                    console.error('Verification SSE error:', event);
                    eventSource.close();
                    button.textContent = originalText;
                    button.disabled = false;
                    showToast('Verification connection error', 'error');
                };
                
                // Listen for completion messages
                const originalOnMessage = eventSource.onmessage;
                eventSource.onmessage = function(event) {
                    originalOnMessage(event);
                    
                    const message = event.data;
                    if (message.includes('✅') && message.includes('completed')) {
                        eventSource.close();
                        button.textContent = originalText;
                        button.disabled = false;
                        
                        if (message.includes('verification successful')) {
                            showToast('VPN certificate verification successful!', 'success');
                        } else {
                            showToast('VPN certificate verification completed', 'info');
                        }
                    } else if (message.includes('❌') && (message.includes('failed') || message.includes('error'))) {
                        eventSource.close();
                        button.textContent = originalText;
                        button.disabled = false;
                        showToast('VPN certificate verification failed', 'error');
                    }
                };
                
            } catch (error) {
                console.error('Verification error:', error);
                button.textContent = originalText;
                button.disabled = false;
                showToast('Verification failed to start', 'error');
            }
        }

        // Renew certificate functionality
        if (e.target.classList.contains('renew-cert-btn')) {
            const deploymentId = e.target.dataset.id;
            const button = e.target;
            const originalText = button.textContent;
            
            try {
                button.textContent = 'Renewing...';
                button.disabled = true;
                
                const result = await renewCertificate(deploymentId);
                showToast('Certificate renewal completed successfully!', 'success');
                await fetchDeployments(); // Refresh the table
                
            } catch (error) {
                console.error('Certificate renewal error:', error);
                showToast('Certificate renewal failed', 'error');
            } finally {
                button.textContent = originalText;
                button.disabled = false;
            }
        }

        // Delete deployment functionality
        if (e.target.classList.contains('delete-deployment-btn')) {
            const deploymentId = e.target.dataset.id;
            
            showConfirmationModal('Are you sure you want to delete this deployment?', async () => {
                try {
                    await safeFetch(`${API_URL}/deploy/${deploymentId}`, { method: 'DELETE' });
                    showToast('Deployment deleted successfully', 'success');
                    await fetchDeployments(); // Refresh the table
                } catch (error) {
                    // Error is handled by safeFetch
                }
            });
        }
    });
}

async function populateEditCompanyDropdown() {
    const companySelect = document.getElementById('edit-deployment-company');
    if (!companySelect) return;

    try {
        const companies = await fetchCompanies();
        companySelect.innerHTML = '<option value="">Select Company</option>';
        companies.forEach(company => {
            const option = document.createElement('option');
            option.value = company;
            option.textContent = company;
            companySelect.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to populate companies:', error);
    }
}

async function populateEditCertificateDropdown(company, selectedCertId = null) {
    const certificateSelect = document.getElementById('edit-deployment-certificate');
    if (!certificateSelect) return;

    if (!company) {
        certificateSelect.innerHTML = '<option value="">Select Certificate</option>';
        certificateSelect.disabled = true;
        return;
    }

    try {
        const certificates = await fetchCertificatesByCompany(company);
        certificateSelect.innerHTML = '<option value="">Select Certificate</option>';
        certificates.forEach(cert => {
            const option = document.createElement('option');
            option.value = cert.id;
            option.textContent = cert.common_name;
            if (cert.id == selectedCertId) option.selected = true;
            certificateSelect.appendChild(option);
        });
        certificateSelect.disabled = false;
    } catch (error) {
        console.error('Failed to populate certificates:', error);
        certificateSelect.disabled = true;
    }
}

async function populateEditTargetSystemDropdown(company, selectedTargetId = null) {
    const targetSystemSelect = document.getElementById('edit-deployment-target-system');
    if (!targetSystemSelect) return;

    if (!company) {
        targetSystemSelect.innerHTML = '<option value="">Select Target System</option>';
        targetSystemSelect.disabled = true;
        return;
    }

    try {
        const targetSystems = await fetchTargetSystemsByCompany(company);
        targetSystemSelect.innerHTML = '<option value="">Select Target System</option>';
        targetSystems.forEach(ts => {
            const option = document.createElement('option');
            option.value = ts.id;
            option.textContent = ts.system_name;
            if (ts.id == selectedTargetId) option.selected = true;
            targetSystemSelect.appendChild(option);
        });
        targetSystemSelect.disabled = false;
    } catch (error) {
        console.error('Failed to populate target systems:', error);
        targetSystemSelect.disabled = true;
    }
}

function setupEditDeploymentModal() {
    document.body.addEventListener('click', async (e) => {
        if (e.target.classList.contains('edit-deployment-btn')) {
            const deploymentId = e.target.dataset.id;
            const editModal = document.getElementById('edit-deployment-modal');
            
            try {
                // Get deployment details
                const deployment = await getDeployment(deploymentId);
                
                // Populate form
                document.getElementById('edit-deployment-id').value = deploymentId;
                document.getElementById('edit-deployment-auto-renewal').checked = deployment.auto_renewal_enabled;
                
                // Populate companies dropdown
                await populateEditCompanyDropdown();
                
                // Set selected company
                const companySelect = document.getElementById('edit-deployment-company');
                companySelect.value = deployment.certificate.company;
                
                // Populate certificates and target systems for the selected company
                await Promise.all([
                    populateEditCertificateDropdown(deployment.certificate.company, deployment.certificate_id),
                    populateEditTargetSystemDropdown(deployment.certificate.company, deployment.target_system_id)
                ]);
                
                showModal(editModal);
            } catch (error) {
                showToast('Failed to load deployment details', 'error');
            }
        }
    });
}

function setupEditCompanyChangeHandler() {
    document.body.addEventListener('change', async (e) => {
        if (e.target.id === 'edit-deployment-company') {
            const company = e.target.value;
            await Promise.all([
                populateEditCertificateDropdown(company),
                populateEditTargetSystemDropdown(company)
            ]);
        }
    });
}

function setupEditDeploymentForm() {
    const form = document.getElementById('edit-deployment-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const deploymentId = document.getElementById('edit-deployment-id').value;
        const certificateId = document.getElementById('edit-deployment-certificate').value;
        const targetSystemId = document.getElementById('edit-deployment-target-system').value;
        const autoRenewalEnabled = document.getElementById('edit-deployment-auto-renewal').checked;

        // Basic validation
        if (!certificateId || !targetSystemId) {
            showToast('Please select both certificate and target system', 'error');
            return;
        }

        try {
            await updateDeployment(deploymentId, certificateId, targetSystemId, autoRenewalEnabled);
            hideModal(document.getElementById('edit-deployment-modal'));
            await fetchDeployments();
            showToast('Deployment updated successfully!', 'success');
        } catch (error) {
            // Error is handled by safeFetch
        }
    });
}

let deploymentHandlersInitialized = false;

export function initializeDeploymentHandlers() {
    if (deploymentHandlersInitialized) return;
    deploymentHandlersInitialized = true;

    setupAddDeploymentModal();
    setupCompanyChangeHandler();
    setupAddDeploymentForm();
    setupEditDeploymentModal();
    setupEditCompanyChangeHandler();
    setupEditDeploymentForm();
    setupDeploymentDynamicEventListeners();
}