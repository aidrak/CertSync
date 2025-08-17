import { API_URL } from '../config.js';
import { safeFetch, showToast, safeEventSource } from '../utils.js';
import { showModal, hideModal, createTestProgressDisplay, updateTestStep, renderCertificatesTable, clearTestProgressDisplay, showConfirmationModal } from '../ui.js';
import { fetchCertificates } from '../api.js';

let currentCertEventSource = null;

function resetCertificateRequestButton() {
    const form = document.getElementById('request-cert-form');
    if (form) {
        const button = form.querySelector('button[type="submit"]');
        if (button) {
            button.textContent = 'Request Certificate';
            button.disabled = false;
        }
    }
    
    // Close any active EventSource connection
    if (currentCertEventSource) {
        currentCertEventSource.close();
        currentCertEventSource = null;
    }
}

function resetModalSize() {
    clearTestProgressDisplay();
}

function setupRequestCertificateModal() {
    const requestCertBtn = document.getElementById('request-certificate-btn');
    if (!requestCertBtn) return;

    const newBtn = requestCertBtn.cloneNode(true);
    requestCertBtn.parentNode.replaceChild(newBtn, requestCertBtn);
    
    newBtn.addEventListener('click', async () => {
        const requestCertModal = document.getElementById('request-cert-modal');
        if (requestCertModal) {
            try {
                resetCertificateRequestButton();
                resetModalSize();
                
                const dnsProviders = await safeFetch(`${API_URL}/dns/dns-provider-accounts/`);
                const companySelect = document.getElementById('cert-company');
                const domainInput = document.getElementById('cert-domain');
                
                companySelect.innerHTML = '<option value="">Select Company</option>';
                
                const companies = [...new Set(dnsProviders.map(p => p.company))];
                companies.forEach(company => {
                    const option = document.createElement('option');
                    option.value = company;
                    option.textContent = company;
                    companySelect.appendChild(option);
                });

                companySelect.addEventListener('change', () => {
                    const selectedCompany = companySelect.value;
                    const provider = dnsProviders.find(p => p.company === selectedCompany);
                    if (provider) {
                        domainInput.value = provider.managed_domain;
                    } else {
                        domainInput.value = '';
                    }
                });

            } catch (error) {
                // safeFetch already handles showing a toast message
            }
            showModal(requestCertModal);
        }
    });

    // Handle modal close events to reset button state and modal size
    document.body.addEventListener('click', (e) => {
        // Handle close button (×) clicks
        if (e.target.classList.contains('close-btn')) {
            const modal = e.target.closest('.modal');
            if (modal && modal.id === 'request-cert-modal') {
                resetCertificateRequestButton();
                resetModalSize();
            }
        }
        
        // Removed: clicks outside modal no longer close it
    });

    // Removed: ESC key no longer closes modal
}

function setupCertificateRequestForm() {
    const form = document.getElementById('request-cert-form');
    if (!form) return;
    
    const newForm = form.cloneNode(true);
    form.parentNode.replaceChild(newForm, form);
    
    newForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const button = newForm.querySelector('button[type="submit"]');
        
        if (button.disabled) return;

        const selectedCompany = document.getElementById('cert-company').value;
        const commonName = document.getElementById('cert-common-name').value;

        const dnsProviders = await safeFetch(`${API_URL}/dns/dns-provider-accounts/`);
        const provider = dnsProviders.find(p => p.company === selectedCompany);

        if (!provider) {
            showToast('Could not find DNS provider for the selected company.', 'error');
            return;
        }

        const certRequest = {
            domains: [commonName],
            dns_provider_account_id: provider.id
        };

        createTestProgressDisplay('request-cert-modal');
        updateTestStep('🚀 Starting certificate request...', 'running');
        button.disabled = true;

        const dnsProviderName = provider.provider_type.toLowerCase();

        const sseEndpoint = `${API_URL}/certificates/request-le-cert-sse/${dnsProviderName}`;
        
        const params = new URLSearchParams({
            domains: certRequest.domains.join(','),
            dns_provider_account_id: certRequest.dns_provider_account_id,
            token: localStorage.getItem('accessToken')
        });
        
        const getEndpoint = `${sseEndpoint}?${params}`;
        currentCertEventSource = safeEventSource(getEndpoint);

        currentCertEventSource.onmessage = function(event) {
            const rawData = event.data;
            const log = rawData.startsWith('data:') ? rawData.substring(5).trim() : rawData.trim();

            if (!log) return;

            let status = 'info';
            if (log.includes('✅') || log.includes('🎉')) status = 'success';
            if (log.includes('❌')) status = 'error';
            if (log.includes('⚠️') || log.includes('🔍 DEBUG')) status = 'warning';
            
            updateTestStep(log, status);

            if (log.includes('🎉 Certificate request completed successfully!')) {
                updateTestStep('✅ Certificate generated and saved!', 'success');
                
                const form = document.getElementById('request-cert-form');
                const button = form.querySelector('button[type="submit"]');
                button.textContent = 'Close';
                button.disabled = false;
                
                // Refresh certificates table immediately
                fetchCertificates();
                
                // Remove old event listeners and add new one
                const newButton = button.cloneNode(true);
                button.parentNode.replaceChild(newButton, button);
                
                newButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    hideModal(document.getElementById('request-cert-modal'));
                });

                currentCertEventSource.close();
                currentCertEventSource = null;
                showToast('Certificate generated successfully!', 'success');
            }
            
            if (log.includes('❌') && log.includes('Error')) {
                resetCertificateRequestButton();
                showToast('Certificate request failed. Check the logs for details.', 'error');
            }
        };

        currentCertEventSource.onerror = function(error) {
            console.error('EventSource failed:', error);
            updateTestStep('❌ Connection failed', 'error');
            resetCertificateRequestButton();
            showToast('Connection to server failed', 'error');
        };

        currentCertEventSource.onopen = function(event) {
            console.log('SSE connection opened');
            updateTestStep('🔗 Connected to server', 'info');
        };
    });
}

async function deleteCertificate(certId) {
    try {
        const response = await fetch(`${API_URL}/certificates/${certId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            }
        });

        if (response.ok) {
            showToast('Certificate deleted successfully!', 'success');
            await fetchCertificates(); // Refresh the table
        } else {
            const errorData = await response.json();
            showToast(errorData.detail || 'Failed to delete certificate.', 'error');
        }
    } catch (error) {
        console.error('Delete failed:', error);
        showToast('An unexpected error occurred.', 'error');
    }
}

function showRenewalConfirmModal(certId, commonName, dnsProviderId) {
    // Create confirmation modal
    const confirmModal = document.createElement('div');
    confirmModal.className = 'modal';
    confirmModal.innerHTML = `
        <div class="modal-content">
            <span class="close-btn">&times;</span>
            <h2>Confirm Certificate Renewal</h2>
            <p>Are you sure you want to renew the certificate for <strong>${commonName}</strong>?</p>
            <p>This will overwrite the existing certificate with a new one.</p>
            <div style="text-align: right; margin-top: 20px;">
                <button class="cancel-renewal-btn" style="margin-right: 10px;">Cancel</button>
                <button class="confirm-renewal-btn">Yes, Renew Certificate</button>
            </div>
        </div>
    `;
    
    // Add event listeners
    confirmModal.querySelector('.close-btn').addEventListener('click', () => {
        hideModal(confirmModal);
        confirmModal.remove();
    });
    
    confirmModal.querySelector('.cancel-renewal-btn').addEventListener('click', () => {
        hideModal(confirmModal);
        confirmModal.remove();
    });
    
    confirmModal.querySelector('.confirm-renewal-btn').addEventListener('click', () => {
        hideModal(confirmModal);
        confirmModal.remove();
        renewCertificate(certId, commonName, dnsProviderId);
    });
    
    // Show the modal
    document.body.appendChild(confirmModal);
    showModal(confirmModal);
}

async function renewCertificate(certId, commonName, dnsProviderId) {
    try {
        // First get the DNS provider to determine the type
        const dnsProviders = await safeFetch(`${API_URL}/dns/dns-provider-accounts/`);
        const provider = dnsProviders.find(p => p.id == dnsProviderId);
        
        if (!provider) {
            showToast('Could not find DNS provider for this certificate.', 'error');
            return;
        }

        // Create a renewal modal similar to the request modal
        const renewalModal = createRenewalModal(certId, commonName, provider);
        document.body.appendChild(renewalModal);
        showModal(renewalModal);

        // Set up the renewal process with SSE
        const dnsProviderName = provider.provider_type.toLowerCase();
        const sseEndpoint = `${API_URL}/certificates/renew-le-cert-sse/${dnsProviderName}`;
        
        const params = new URLSearchParams({
            cert_id: certId,
            domains: commonName,
            dns_provider_account_id: dnsProviderId,
            token: localStorage.getItem('accessToken')
        });
        
        const getEndpoint = `${sseEndpoint}?${params}`;
        
        createTestProgressDisplay(renewalModal.id);
        updateTestStep('🔄 Starting certificate renewal...', 'running');
        
        currentCertEventSource = safeEventSource(getEndpoint);

        currentCertEventSource.onmessage = function(event) {
            const rawData = event.data;
            const log = rawData.startsWith('data:') ? rawData.substring(5).trim() : rawData.trim();

            if (!log) return;

            let status = 'info';
            if (log.includes('✅') || log.includes('🎉')) status = 'success';
            if (log.includes('❌')) status = 'error';
            if (log.includes('⚠️') || log.includes('🔍 DEBUG')) status = 'warning';
            
            updateTestStep(log, status);

            if (log.includes('🎉 Certificate request completed successfully!')) {
                updateTestStep('✅ Certificate renewed and saved!', 'success');
                
                const closeBtn = renewalModal.querySelector('.close-renewal-btn');
                if (closeBtn) {
                    closeBtn.textContent = 'Close';
                    closeBtn.disabled = false;
                }
                
                // Refresh certificates table immediately
                fetchCertificates();
                
                currentCertEventSource.close();
                currentCertEventSource = null;
                showToast('Certificate renewed successfully!', 'success');
            }
            
            if (log.includes('❌') && log.includes('Error')) {
                const closeBtn = renewalModal.querySelector('.close-renewal-btn');
                if (closeBtn) {
                    closeBtn.textContent = 'Close';
                    closeBtn.disabled = false;
                }
                showToast('Certificate renewal failed. Check the logs for details.', 'error');
            }
        };

        currentCertEventSource.onerror = function(error) {
            console.error('EventSource failed:', error);
            updateTestStep('❌ Connection failed', 'error');
            const closeBtn = renewalModal.querySelector('.close-renewal-btn');
            if (closeBtn) {
                closeBtn.textContent = 'Close';
                closeBtn.disabled = false;
            }
            showToast('Connection to server failed', 'error');
        };

        currentCertEventSource.onopen = function(event) {
            console.log('SSE connection opened for renewal');
            updateTestStep('🔗 Connected to server', 'info');
        };

    } catch (error) {
        console.error('Renewal failed:', error);
        showToast('An unexpected error occurred during renewal.', 'error');
    }
}

function createRenewalModal(certId, commonName, provider) {
    const modalId = `renewal-modal-${certId}`;
    const modal = document.createElement('div');
    modal.id = modalId;
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-btn">&times;</span>
            <h2>Renew Certificate</h2>
            <form class="renewal-form">
                <p><strong>Certificate:</strong> ${commonName}</p>
                <p><strong>DNS Provider:</strong> ${provider.company} (${provider.managed_domain})</p>
                <p>This will overwrite the existing certificate with a new one.</p>
                <button type="button" class="close-renewal-btn" disabled>Renewing...</button>
            </form>
        </div>
    `;
    
    // Add close functionality
    modal.querySelector('.close-btn').addEventListener('click', () => {
        if (currentCertEventSource) {
            currentCertEventSource.close();
            currentCertEventSource = null;
        }
        hideModal(modal);
        modal.remove();
    });
    
    modal.querySelector('.close-renewal-btn').addEventListener('click', () => {
        if (currentCertEventSource) {
            currentCertEventSource.close();
            currentCertEventSource = null;
        }
        hideModal(modal);
        modal.remove();
    });
    
    return modal;
}

let downloadHandlerInitialized = false;

function setupDownloadCertificateHandler() {
    if (downloadHandlerInitialized) return;
    downloadHandlerInitialized = true;
    
    document.body.addEventListener('click', (e) => {
        if (e.target.classList.contains('download-cert-btn')) {
            const certId = e.target.dataset.id;
            const passwordModal = document.getElementById('pfx-password-modal');
            document.getElementById('pfx-cert-id').value = certId;
            showModal(passwordModal);
        }
        
        if (e.target.classList.contains('delete-cert-btn')) {
            const certId = e.target.dataset.id;
            showConfirmationModal('Are you sure you want to delete this certificate?', () => {
                deleteCertificate(certId);
            });
        }
        
        if (e.target.classList.contains('renew-cert-btn')) {
            const certId = e.target.dataset.id;
            const commonName = e.target.dataset.commonName;
            const dnsProviderId = e.target.dataset.dnsProviderId;
            
            showRenewalConfirmModal(certId, commonName, dnsProviderId);
        }
    });

    document.body.addEventListener('submit', async (e) => {
        if (e.target.id !== 'pfx-password-form') return;
        e.preventDefault();
        
        const certId = document.getElementById('pfx-cert-id').value;
        const passwordInput = document.getElementById('pfx-password');
        const password = passwordInput.value;

        if (password.length < 8) {
            showToast('Password must be at least 8 characters long.', 'error');
            return;
        }

        const token = localStorage.getItem('accessToken');

        try {
            const response = await fetch(`${API_URL}/certificates/${certId}/download/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ password: password })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                const contentDisposition = response.headers.get('content-disposition');
                let filename = 'certificate.pfx';
                if (contentDisposition) {
                    const filenameMatch = contentDisposition.match(/filename="(.+)"/);
                    if (filenameMatch && filenameMatch.length > 1) {
                        filename = filenameMatch;
                    }
                }
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
                showToast('Certificate downloaded successfully!', 'success');
                hideModal(document.getElementById('pfx-password-modal'));
                e.target.reset(); // Clear the form fields
            } else {
                const errorData = await response.json();
                showToast(errorData.detail || 'Failed to download certificate.', 'error');
            }
        } catch (error) {
            showToast('An unexpected error occurred.', 'error');
        }
    });
}

let certificateHandlersInitialized = false;

export function initializeCertificateHandlers() {
    if (certificateHandlersInitialized) return;
    certificateHandlersInitialized = true;
    
    setupRequestCertificateModal();
    setupCertificateRequestForm();
    setupDownloadCertificateHandler();
}