import { API_URL } from './config.js';
import { safeFetch, showToast, formatVendorName, escapeHtml } from './utils.js';
import { renderExpirationChart, showModal, hideModal, showVendorSpecificInfo, renderCertificatesTable, renderTargetSystemsTable } from './ui.js';

export async function fetchTargetSystems() {
    try {
        const [targetSystems, dnsProviders] = await Promise.all([
            safeFetch(`${API_URL}/target-systems/`),
            fetchDnsProviders()
        ]);
        
        const count = targetSystems?.length || 0;
        
        if (document.getElementById('active-target-systems')) {
            document.getElementById('active-target-systems').textContent = count;
        }

        renderTargetSystemsTable(targetSystems, dnsProviders);
        return targetSystems;
    } catch (error) {
        if (document.getElementById('active-target-systems')) {
            document.getElementById('active-target-systems').textContent = '0';
        }
        return [];
    }
}

export async function fetchDashboardStats() {
    try {
        const stats = await safeFetch(`${API_URL}/system/stats/`);
        
        if (document.getElementById('managed-domains')) {
            document.getElementById('managed-domains').textContent = stats.total_dns_providers;
        }
        if (document.getElementById('issued-certificates')) {
            document.getElementById('issued-certificates').textContent = stats.total_certificates;
        }
        if (document.getElementById('expiring-soon')) {
            document.getElementById('expiring-soon').textContent = stats.expiring_soon;
        }
        if (document.getElementById('managed-systems')) {
            document.getElementById('managed-systems').textContent = stats.total_target_systems;
        }

        const certs = await safeFetch(`${API_URL}/certificates/`);
        if (certs) {
            renderExpirationChart(certs);
        }

    } catch (error) {
        if (document.getElementById('managed-domains')) {
            document.getElementById('managed-domains').textContent = '0';
        }
        if (document.getElementById('issued-certificates')) {
            document.getElementById('issued-certificates').textContent = '0';
        }
        if (document.getElementById('expiring-soon')) {
            document.getElementById('expiring-soon').textContent = '0';
        }
        if (document.getElementById('managed-systems')) {
            document.getElementById('managed-systems').textContent = '0';
        }
    }
}

export async function fetchCertificates() {
    try {
        const [certs, dnsProviders] = await Promise.all([
            safeFetch(`${API_URL}/certificates/`),
            fetchDnsProviders()
        ]);
        renderCertificatesTable(certs, dnsProviders);
        return certs;
    } catch (error) {
        // Error is handled by safeFetch
        return [];
    }
}

export async function sendLog(level, message, extra = {}) {
    // Frontend logging to backend is disabled - endpoint doesn't exist
    // This prevents spam in the docker logs from OPTIONS requests
    // If you want to enable frontend logging, create the /logs/frontend/ endpoint in the backend
    console.log(`[${level.toUpperCase()}] ${message}`, extra);
}

export async function fetchLogs() {
    try {
        const [logs, timezoneData] = await Promise.all([
            safeFetch(`${API_URL}/logs/`),
            safeFetch(`${API_URL}/system/timezone/`)
        ]);
        const timezone = timezoneData.timezone;
        const logsTable = document.getElementById('logs-table')?.getElementsByTagName('tbody')[0];
        if (logsTable) {
            logsTable.innerHTML = '';
            logs.forEach(log => {
                const row = logsTable.insertRow();
                row.innerHTML = `
                    <td>${new Date(log.timestamp).toLocaleString(undefined, { timeZone: timezone })}</td>
                    <td>${escapeHtml(log.level.toUpperCase())}</td>
                    <td>${escapeHtml(log.action)}</td>
                    <td>${escapeHtml(log.target)}</td>
                    <td>${escapeHtml(log.message)}</td>
                `;
            });
        }
    } catch (error) {
        // Error is already displayed by safeFetch
    }
}

export async function fetchUsers() {
    try {
        const users = await safeFetch(`${API_URL}/auth/users/`);
        const usersList = document.getElementById('users-list');
        if (usersList) {
            usersList.innerHTML = '';
            users.forEach(user => {
                const userItem = document.createElement('div');
                userItem.className = 'user-item';
                userItem.innerHTML = `
                    <div class="user-info">
                        <span class="username">${escapeHtml(user.username)}</span>
                        <span class="role">${escapeHtml(user.role)}</span>
                    </div>
                    <div class="user-actions">
                        <button class="edit-user-btn" data-id="${user.id}" data-username="${user.username}" data-role="${user.role}">Edit</button>
                        <button class="delete-user-btn" data-id="${user.id}">Delete</button>
                        <button class="change-password-btn" data-id="${user.id}">Change Password</button>
                    </div>
                `;
                usersList.appendChild(userItem);
            });
        }
    } catch (error) {
        // Error is already displayed by safeFetch
    }
}

export async function fetchDnsProviders() {
    try {
        const accounts = await safeFetch(`${API_URL}/dns/dns-provider-accounts/`);
        const dnsAccountsTable = document.getElementById('dns-accounts-table')?.getElementsByTagName('tbody')[0];
        if (dnsAccountsTable) {
            dnsAccountsTable.innerHTML = '';
            accounts.forEach(acc => {
                const row = dnsAccountsTable.insertRow();
                row.innerHTML = `
                    <td>${acc.company}</td>
                    <td>${acc.managed_domain}</td>
                    <td>${acc.provider_type}</td>
                    <td class="actions-cell">
                        <div class="action-buttons">
                            <button class="edit-dns-btn" data-id="${acc.id}">Edit</button>
                            <button class="delete-dns-btn" data-id="${acc.id}">Delete</button>
                        </div>
                    </td>
                `;
            });
        }
        return accounts;
    } catch (error) {
        // Error is already displayed by safeFetch
        return [];
    }
}

export async function fetchLogLevel() {
    try {
        const level = await safeFetch(`${API_URL}/system/log-level`);
        document.getElementById('current-log-level').textContent = level.log_level;
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function fetchBackupSettings() {
    try {
        const settings = await safeFetch(`${API_URL}/system/backup-settings`);
        document.getElementById('backup-enabled').checked = settings.backup_enabled;
        document.getElementById('backup-frequency').value = settings.backup_frequency;
        document.getElementById('backup-time').value = settings.backup_time;
        document.getElementById('backup-retention').value = settings.backup_retention_days;
        document.getElementById('backup-location').value = settings.backup_location;
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function saveBackupSettings(settings) {
    try {
        await safeFetch(`${API_URL}/system/backup-settings`, {
            method: 'POST',
            body: JSON.stringify(settings),
        });
        showToast('Backup settings saved successfully!', 'success');
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function backupNow() {
    try {
        await safeFetch(`${API_URL}/system/backup-now`, { method: 'POST' });
        showToast('Backup started successfully!', 'success');
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function fetchBackupHistory() {
    try {
        const history = await safeFetch(`${API_URL}/system/backup-history`);
        const tableBody = document.getElementById('backup-history-table').querySelector('tbody');
        tableBody.innerHTML = '';
        history.forEach(backup => {
            const row = tableBody.insertRow();
            row.innerHTML = `
                <td>${new Date(backup.backup_date).toLocaleString()}</td>
                <td>${backup.status}</td>
                <td>${(backup.file_size / 1024).toFixed(2)} KB</td>
                <td><a href="${API_URL}/system/download-backup/${backup.id}" download>Download</a></td>
            `;
        });
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function setLogLevel() {
    const level = document.getElementById('log-level-select').value;
    try {
        const payload = {
            key: "LOGGING_LEVEL",
            value: level
        };
        await safeFetch(`${API_URL}/system/log-level/`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        await fetchLogLevel();
        showToast('Log level updated successfully!', 'success');
    } catch (error) {
        // Error is handled by safeFetch
    }
}

export async function fetchDeployments() {
    try {
        const deployments = await safeFetch(`${API_URL}/deploy/`);
        const deploymentsTable = document.getElementById('deployments-table')?.getElementsByTagName('tbody')[0];
        if (deploymentsTable) {
            deploymentsTable.innerHTML = '';
            deployments.forEach(deployment => {
                const row = deploymentsTable.insertRow();
                row.innerHTML = `
                    <td>${escapeHtml(deployment.target_system?.company || deployment.certificate?.dns_provider_account?.company || 'N/A')}</td>
                    <td>${escapeHtml(deployment.certificate?.common_name || 'N/A')}</td>
                    <td>${escapeHtml(deployment.target_system?.system_name || 'N/A')}</td>
                    <td>${escapeHtml(deployment.status || 'pending')}</td>
                    <td>${deployment.last_deployed_at ? new Date(deployment.last_deployed_at).toLocaleDateString() : 'Never'}</td>
                    <td>${deployment.next_renewal_date ? new Date(deployment.next_renewal_date).toLocaleDateString() : 'N/A'}</td>
                    <td>${deployment.auto_renewal_enabled ? 'Yes' : 'No'}</td>
                    <td class="actions-cell">
                        <div class="action-buttons">
                            <button class="deploy-btn" data-id="${deployment.id}">Deploy</button>
                            <button class="verify-vpn-btn" data-id="${deployment.id}" style="margin-left: 5px;">Verify VPN</button>
                            <button class="delete-deployment-btn" data-id="${deployment.id}">Delete</button>
                        </div>
                    </td>
                `;
            });
        }
        return deployments;
    } catch (error) {
        return [];
    }
}

export async function createDeployment(certificateId, targetSystemId, autoRenewalEnabled = false) {
    const body = {
        certificate_id: parseInt(certificateId, 10),
        target_system_id: parseInt(targetSystemId, 10),
        auto_renewal_enabled: autoRenewalEnabled
    };
    return await safeFetch(`${API_URL}/deploy/`, {
        method: 'POST',
        body: JSON.stringify(body),
    });
}

export async function verifyVpnDeployment(deploymentId) {
    return await safeFetch(`${API_URL}/deploy/${deploymentId}/verify-vpn`, {
        method: 'POST'
    });
}

export async function fetchCompanies() {
    try {
        return await safeFetch(`${API_URL}/deploy/companies/`);
    } catch (error) {
        return [];
    }
}

export async function fetchCertificatesByCompany(company) {
    try {
        return await safeFetch(`${API_URL}/deploy/certificates-by-company/${encodeURIComponent(company)}`);
    } catch (error) {
        return [];
    }
}

export async function fetchTargetSystemsByCompany(company) {
    try {
        return await safeFetch(`${API_URL}/deploy/target-systems-by-company/${encodeURIComponent(company)}`);
    } catch (error) {
        return [];
    }
}
