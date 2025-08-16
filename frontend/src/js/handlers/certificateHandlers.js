import { API_URL } from '../config.js';
import { safeFetch, showToast, safeEventSource } from '../utils.js';
import { showModal, hideModal, createTestProgressDisplay, updateTestStep, renderCertificatesTable, clearTestProgressDisplay } from '../ui.js';
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
            dns_provider_account_id: certRequest.dns_provider_account_id
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
        const response = await safeFetch(`${API_URL}/certificates/${certId}`, {
            method: 'DELETE'
        });
        showToast('Certificate deleted successfully!', 'success');
        await fetchCertificates(); // Refresh the table
    } catch (error) {
        console.error('Delete failed:', error);
        showToast('Failed to delete certificate: ' + error.message, 'error');
    }
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
            if (confirm('Are you sure you want to delete this certificate?')) {
                deleteCertificate(certId);
            }
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
                        filename = filenameMatch[1];
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
