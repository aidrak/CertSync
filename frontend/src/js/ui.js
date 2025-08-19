import { formatVendorName, escapeHtml } from './utils.js';

export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) {
        console.error('Toast container not found!');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 100);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            container.removeChild(toast);
        }, 500);
    }, 5000);
}

export function showModal(modal) {
    if (modal) {
        modal.style.display = 'block';
        modal.classList.add('show');
    }
}

function resetAllForms() {
    document.querySelectorAll('form').forEach(form => {
        form.reset();
    });
}

export function hideModal(modal) {
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
        
        const progressContainer = document.getElementById('test-progress-container');
        if (progressContainer) {
            progressContainer.remove();
        }

        if (modal.id === 'request-cert-modal') {
            resetRequestCertForm();
        } else {
            resetAllForms();
        }
    }
}
export function showConfirmationModal(message, onConfirm) {
    const modal = document.getElementById('confirmation-modal');
    const messageElement = document.getElementById('confirmation-message');
    const confirmBtn = document.getElementById('confirm-btn');
    const cancelBtn = document.getElementById('cancel-btn');

    messageElement.textContent = message;

    const confirmHandler = () => {
        onConfirm();
        hideModal(modal);
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    const cancelHandler = () => {
        hideModal(modal);
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    confirmBtn.addEventListener('click', confirmHandler);
    cancelBtn.addEventListener('click', cancelHandler);

    showModal(modal);
}

function resetRequestCertForm() {
    const form = document.getElementById('request-cert-form');
    if (form) {
        form.reset();
        const button = form.querySelector('button[type="submit"]');
        if (button) {
            button.textContent = 'Request Certificate';
            button.disabled = false;
        }
    }
}

export function createTestProgressDisplay(modalId) {
    clearTestProgressDisplay();

    const modalContent = document.querySelector(`#${modalId} .modal-content`);
    if (!modalContent) return;

    modalContent.classList.add('large-flex');

    let flexContainer = modalContent.querySelector('.modal-flex-container');
    if (!flexContainer) {
        const form = modalContent.querySelector('form');
        flexContainer = document.createElement('div');
        flexContainer.className = 'modal-flex-container';
        
        const formColumn = document.createElement('div');
        formColumn.className = 'modal-form-column';
        
        formColumn.appendChild(form);
        flexContainer.appendChild(formColumn);
        modalContent.appendChild(flexContainer);
    }

    const progressColumn = document.createElement('div');
    progressColumn.id = 'test-progress-container';
    progressColumn.className = 'modal-progress-column';
    
    const progressTitle = document.createElement('div');
    progressTitle.style.fontWeight = 'bold';
    progressTitle.style.marginBottom = '10px';
    progressTitle.textContent = 'Test Progress:';
    progressColumn.appendChild(progressTitle);
    
    const progressList = document.createElement('div');
    progressList.id = 'test-progress-list';
    progressColumn.appendChild(progressList);
    
    flexContainer.appendChild(progressColumn);
}

export function updateTestStep(message, status = 'info') {
    // Try test progress list first (for new deployment tests), then fall back to deployment progress list (for existing deployments)
    let progressList = document.getElementById('test-progress-list');
    if (!progressList) {
        progressList = document.getElementById('deployment-progress-list');
    }
    if (!progressList) return;
    
    const stepDiv = document.createElement('div');
    stepDiv.style.cssText = `
        padding: 5px 0;
        font-size: 0.9em;
        display: flex;
        align-items: center;
    `;
    
    let icon = '';
    let color = '#6c757d';
    
    if (status === 'success') {
        icon = '✅ ';
        color = '#28a745';
    } else if (status === 'error') {
        icon = '❌ ';
        color = '#dc3545';
    } else if (status === 'running') {
        icon = '⏳ ';
        color = '#007bff';
    }
    
    const emojiRegex = /([\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}])/gu;
    const cleanedMessage = message.replace(/^\[\d{2}:\d{2}:\d{2}\]\s/, '').replace(emojiRegex, '').trim();

    stepDiv.innerHTML = `<span style="color: ${color};">${icon}${cleanedMessage}</span>`;
    progressList.appendChild(stepDiv);
    
    const container = document.getElementById('test-progress-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

export function clearTestProgressDisplay() {
    const progressContainer = document.getElementById('test-progress-container');
    if (progressContainer) {
        progressContainer.remove();
    }
    
    // Reset modal size by removing the large-flex class and flex container
    const modalContent = progressContainer?.closest('.modal-content') || 
                        document.querySelector('.modal-content.large-flex');
    if (modalContent) {
        modalContent.classList.remove('large-flex');
        
        const flexContainer = modalContent.querySelector('.modal-flex-container');
        if (flexContainer) {
            const form = flexContainer.querySelector('form');
            if (form) {
                // Move form back to its original position
                modalContent.appendChild(form);
            }
            flexContainer.remove();
        }
    }
}

export function renderCertificatesTable(certificates, dnsProviders) {
    const tableBody = document.querySelector('#certificates-table tbody');
    if (!tableBody) return;
    tableBody.innerHTML = '';

    if (certificates.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="5">No certificates found.</td></tr>';
        return;
    }

    // Sort certificates: first by company A-Z, then by common name A-Z
    const sortedCertificates = [...certificates].sort((a, b) => {
        const dnsProviderA = dnsProviders.find(p => p.id === a.dns_provider_account_id);
        const dnsProviderB = dnsProviders.find(p => p.id === b.dns_provider_account_id);
        const companyA = (dnsProviderA ? dnsProviderA.company : 'N/A').toLowerCase();
        const companyB = (dnsProviderB ? dnsProviderB.company : 'N/A').toLowerCase();
        
        // First sort by company
        const companyCompare = companyA.localeCompare(companyB);
        if (companyCompare !== 0) {
            return companyCompare;
        }
        
        // If companies are the same, sort by common name
        return a.common_name.toLowerCase().localeCompare(b.common_name.toLowerCase());
    });

    sortedCertificates.forEach(cert => {
        const dnsProvider = dnsProviders.find(p => p.id === cert.dns_provider_account_id);
        const companyName = dnsProvider ? dnsProvider.company : 'N/A';
        const domain = dnsProvider ? dnsProvider.managed_domain : 'N/A';
        const expires = new Date(cert.expires_at).toLocaleDateString();
        const isExpiringSoon = (new Date(cert.expires_at) - new Date()) / (1000 * 60 * 60 * 24) < 30;

        const row = `
            <tr>
                <td>${companyName}</td>
                <td>${cert.common_name}</td>
                <td>${domain}</td>
                <td class="${isExpiringSoon ? 'expiring-soon' : ''}">${expires}</td>
                <td>
                    <button class="download-cert-btn" data-id="${cert.id}">Download</button>
                    <button class="renew-cert-btn readonly-hide" data-id="${cert.id}" data-common-name="${cert.common_name}" data-dns-provider-id="${cert.dns_provider_account_id}">Renew</button>
                    <button class="delete-cert-btn readonly-hide" data-id="${cert.id}">Delete</button>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}

export function renderDnsProvidersTable(accounts) {
    const tableBody = document.querySelector('#dns-accounts-table tbody');
    if (!tableBody) return;
    tableBody.innerHTML = '';

    if (accounts.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="4">No DNS providers found.</td></tr>';
        return;
    }

    accounts.forEach(acc => {
        const row = `
            <tr>
                <td>${acc.company}</td>
                <td>${acc.managed_domain}</td>
                <td>${acc.provider_type}</td>
                <td class="actions-cell">
                    <div class="action-buttons">
                        <button class="edit-dns-btn readonly-hide" data-id="${acc.id}">Edit</button>
                        <button class="delete-dns-btn readonly-hide" data-id="${acc.id}">Delete</button>
                    </div>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}

export function renderDeploymentsTable(deployments) {
    const tableBody = document.querySelector('#deployments-table tbody');
    if (!tableBody) return;
    tableBody.innerHTML = '';

    if (deployments.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="9">No deployments found.</td></tr>';
        return;
    }

    const sortedDeployments = [...deployments].sort((a, b) => {
        const companyA = (a.target_system?.company || a.certificate?.dns_provider_account?.company || 'N/A').toLowerCase();
        const companyB = (b.target_system?.company || b.certificate?.dns_provider_account?.company || 'N/A').toLowerCase();
        
        const companyCompare = companyA.localeCompare(companyB);
        if (companyCompare !== 0) return companyCompare;
        
        const certA = (a.certificate?.common_name || 'N/A').toLowerCase();
        const certB = (b.certificate?.common_name || 'N/A').toLowerCase();
        return certA.localeCompare(certB);
    });

    sortedDeployments.forEach(deployment => {
        const row = `
            <tr>
                <td>${escapeHtml(deployment.target_system?.company || deployment.certificate?.dns_provider_account?.company || 'N/A')}</td>
                <td>${escapeHtml(deployment.certificate?.common_name || 'N/A')}</td>
                <td>${escapeHtml(deployment.target_system?.system_name || 'N/A')}</td>
                <td>${escapeHtml(deployment.status || 'pending')}</td>
                <td>${deployment.certificate?.expires_at ? new Date(deployment.certificate.expires_at).toLocaleDateString() : 'N/A'}</td>
                <td>${deployment.next_renewal_date ? new Date(deployment.next_renewal_date).toLocaleDateString() : 'N/A'}</td>
                <td style="text-align: center;">
                    <input type="checkbox" class="toggle-switch auto-renewal-toggle"
                           data-id="${deployment.id}"
                           ${deployment.auto_renewal_enabled ? 'checked' : ''}>
                </td>
                <td class="actions-cell">
                    <div class="action-buttons">
                        <button class="deploy-btn" data-id="${deployment.id}">Deploy</button>
                        <button class="verify-vpn-btn" data-id="${deployment.id}" style="margin-left: 5px;">Verify</button>
                        <button class="renew-cert-btn" data-id="${deployment.id}" style="margin-left: 5px;">Renew</button>
                        <button class="edit-deployment-btn" data-id="${deployment.id}" style="margin-left: 5px;">Edit</button>
                        <button class="delete-deployment-btn" data-id="${deployment.id}">Delete</button>
                    </div>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}

export function renderTargetSystemsTable(targetSystems, dnsProviders) {
    const tableBody = document.querySelector('#target-systems-table tbody');
    if (!tableBody) return;
    tableBody.innerHTML = '';

    if (targetSystems.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="7">No target systems found.</td></tr>';
        return;
    }

    // Sort target systems: first by company A-Z, then by system name A-Z
    const sortedTargetSystems = [...targetSystems].sort((a, b) => {
        const companyA = (a.company || 'N/A').toLowerCase();
        const companyB = (b.company || 'N/A').toLowerCase();
        
        // First sort by company
        const companyCompare = companyA.localeCompare(companyB);
        if (companyCompare !== 0) {
            return companyCompare;
        }
        
        // If companies are the same, sort by system name
        return a.system_name.toLowerCase().localeCompare(b.system_name.toLowerCase());
    });

    sortedTargetSystems.forEach(ts => {
        const dnsProvider = dnsProviders.find(p => p.id === ts.dns_provider_account_id);
        const companyName = ts.company || 'N/A';
        const row = `
            <tr>
                <td>${companyName}</td>
                <td>${ts.system_name}</td>
                <td>${ts.system_type}</td>
                <td>${ts.public_ip}</td>
                <td>${ts.vpn_port || 'N/A'}</td>
                <td>${ts.management_port}</td>
                <td>
                    <button class="edit-ts-btn" data-id="${ts.id}">Edit</button>
                    <button class="delete-ts-btn" data-id="${ts.id}">Delete</button>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}


export function updateApiKeyFieldLabel() {
    // --- Add Form ---
    const type = document.getElementById('ts-type')?.value;
    const apiKeyGroup = document.getElementById('ts-api-key-group');
    const apiKeyInput = document.getElementById('ts-api-key');
    const adminUsernameGroup = document.getElementById('ts-admin-username-group');
    const adminPasswordGroup = document.getElementById('ts-admin-password-group');
    const adminUsernameInput = document.getElementById('ts-admin-username');
    const adminPasswordInput = document.getElementById('ts-admin-password');

    if (apiKeyGroup && apiKeyInput && adminUsernameGroup && adminPasswordGroup && adminUsernameInput && adminPasswordInput) {
        if (type === 'sonicwall') {
            apiKeyGroup.style.display = 'none';
            apiKeyInput.required = false;
            adminUsernameGroup.style.display = 'block';
            adminPasswordGroup.style.display = 'block';
            adminUsernameInput.required = true;
            adminPasswordInput.required = true;
        } else {
            apiKeyGroup.style.display = 'block';
            apiKeyInput.required = true;
            adminUsernameGroup.style.display = 'none';
            adminPasswordGroup.style.display = 'none';
            adminUsernameInput.required = false;
            adminPasswordInput.required = false;
        }
    }

    // --- Edit Form ---
    const editType = document.getElementById('edit-ts-type')?.value;
    const editApiKeyGroup = document.getElementById('edit-ts-api-key-group');
    const editAdminUsernameGroup = document.getElementById('edit-ts-admin-username-group');
    const editAdminPasswordGroup = document.getElementById('edit-ts-admin-password-group');

    if (editApiKeyGroup && editAdminUsernameGroup && editAdminPasswordGroup) {
        if (editType === 'sonicwall') {
            editApiKeyGroup.style.display = 'none';
            editAdminUsernameGroup.style.display = 'block';
            editAdminPasswordGroup.style.display = 'block';
        } else {
            editApiKeyGroup.style.display = 'block';
            editAdminUsernameGroup.style.display = 'none';
            editAdminPasswordGroup.style.display = 'none';
        }
    }
}

export function showVendorSpecificInfo() {
    // This function is now handled by updateApiKeyFieldLabel, 
    // but we'll keep it here in case it's used elsewhere.
    // For now, it does nothing.
}

export function displayTestResults(results, vendor) {
    const resultsContent = document.getElementById('test-results-content');
    resultsContent.innerHTML = '';

    const success = results.overall_success || (results.status === 'success');
    const details = results.details || {};
    const logs = results.logs || [];

    const title = document.createElement('h3');
    title.textContent = `${formatVendorName(vendor)} Test Results: ${success ? '✅ Success' : '❌ Failure'}`;
    title.style.color = success ? '#28a745' : '#dc3545';
    resultsContent.appendChild(title);

    if (Object.keys(details).length > 0) {
        const detailsHeader = document.createElement('h4');
        detailsHeader.textContent = 'Device Details';
        detailsHeader.style.marginTop = '15px';
        resultsContent.appendChild(detailsHeader);

        const detailsList = document.createElement('ul');
        detailsList.style.listStyleType = 'none';
        detailsList.style.paddingLeft = '0';
        
        for (const [key, value] of Object.entries(details)) {
            const item = document.createElement('li');
            item.innerHTML = `<strong>${key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ')}:</strong> ${value}`;
            detailsList.appendChild(item);
        }
        resultsContent.appendChild(detailsList);
    }

    if (logs.length > 0) {
        const logsHeader = document.createElement('h4');
        logsHeader.textContent = 'Test Log';
        logsHeader.style.marginTop = '15px';
        resultsContent.appendChild(logsHeader);

        const logContainer = document.createElement('div');
        logContainer.style.cssText = `
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 10px;
            max-height: 300px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
        `;
        
        const coloredLogs = logs.map(log => {
            if (log.includes('✅')) return `<span style="color: #28a745;">${log}</span>`;
            if (log.includes('❌')) return `<span style="color: #dc3545;">${log}</span>`;
            if (log.includes('⚠️')) return `<span style="color: #ffc107;">${log}</span>`;
            if (log.includes('🔍') || log.includes('📋')) return `<span style="color: #007bff;">${log}</span>`;
            return log;
        });
        
        logContainer.innerHTML = coloredLogs.join('\n');
        resultsContent.appendChild(logContainer);
    }

    showModal(document.getElementById('test-results-modal'));
}

export function displayTestError(error, vendor) {
    const resultsContent = document.getElementById('test-results-content');
    resultsContent.innerHTML = `
        <h3 style="color: #dc3545;">Test Failed</h3>
        <p><strong>Error:</strong> ${error.message}</p>
    `;
    
    if (vendor === 'sonicwall') {
        resultsContent.innerHTML += `
            <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 10px; margin: 10px 0;">
                <strong>SonicWall Common Issues:</strong>
                <ul style="margin: 5px 0; padding-left: 20px;">
                    <li>Admin session conflict (someone logged into web GUI)</li>
                    <li>API not enabled in SonicOS settings</li>
                    <li>Incorrect admin password</li>
                    <li>Network connectivity issues</li>
                </ul>
            </div>
        `;
    }
    
    showModal(document.getElementById('test-results-modal'));
}

export function renderExpirationChart(certs) {
    const chartElement = document.getElementById('expiration-chart');
    if (!chartElement) return;
    
    const ctx = chartElement.getContext('2d');
    const labels = [];
    const data = [];
    const now = new Date();
    
    for (let i = 0; i < 15; i++) {
        const date = new Date(now);
        date.setDate(now.getDate() + i);
        labels.push(date.toLocaleDateString());
        data.push(0);
    }

    certs.forEach(cert => {
        const expires = new Date(cert.expires_at);
        const diffDays = Math.ceil((expires - now) / (1000 * 60 * 60 * 24));
        if (diffDays >= 0 && diffDays < 15) {
            data[diffDays]++;
        }
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Certificates Expiring',
                data: data,
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } }
        }
    });
}

export function updateDnsCredentialsFields() {
    const provider = document.getElementById('dns-account-provider').value;
    const fieldsContainer = document.getElementById('dns-credentials-fields');
    fieldsContainer.innerHTML = '';

    if (provider === 'cloudflare' || provider === 'digitalocean') {
        fieldsContainer.innerHTML = `
            <label for="cred-${provider}-token">Token:</label>
            <input type="password" id="cred-${provider}-token" required autocomplete="new-password">
        `;
    }
}

export function updateEditDnsCredentialsFields() {
    const provider = document.getElementById('edit-dns-account-provider').value;
    const fieldsContainer = document.getElementById('edit-dns-credentials-fields');
    fieldsContainer.innerHTML = '';

    if (provider === 'cloudflare' || provider === 'digitalocean') {
        fieldsContainer.innerHTML = `
            <label for="edit-cred-${provider}-token">Token:</label>
            <input type="password" id="edit-cred-${provider}-token" autocomplete="new-password">
            <small>Leave blank to keep existing token.</small>
        `;
    }
}

export function initializePlaceholders() {
    const placeholders = {
        'managed-domains': '0',
        'issued-certificates': '0',
        'expiring-soon': '0',
        'active-firewalls': '0',
        'failed-renewals': '0',
    };
    for (const id in placeholders) {
        const el = document.getElementById(id);
        if (el) el.textContent = placeholders[id];
    }
}

export function showLogMessageModal(message) {
    const modal = document.getElementById('log-message-modal');
    const messageElement = document.getElementById('full-log-message');
    if (modal && messageElement) {
        messageElement.textContent = message;
        showModal(modal);
    }
}

export async function updateSonicWallStatus() {
    try {
        const firewalls = await safeFetch(`${API_URL}/firewalls/`);
        const sonicwallCount = firewalls.filter(fw => fw.vendor === 'sonicwall').length;
        
        const statusSection = document.getElementById('sonicwall-status-section');
        const countElement = document.getElementById('sonicwall-firewalls-count');
        const ftpStatusElement = document.getElementById('ftp-server-status');
        
        if (sonicwallCount > 0) {
            statusSection.style.display = 'block';
            countElement.textContent = sonicwallCount;
            ftpStatusElement.textContent = '✅';
            ftpStatusElement.parentElement.querySelector('p').textContent = 'FTP Server (Active)';
        } else {
            statusSection.style.display = 'none';
        }
    } catch (error) {
        // Error handled by safeFetch
    }
}
