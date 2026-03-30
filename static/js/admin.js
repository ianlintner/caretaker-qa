// Admin Dashboard JavaScript - SPA with client-side routing

// Determine which page to show based on URL path
function getCurrentPage() {
    const path = window.location.pathname;
    if (path === '/admin/clients') return 'clients';
    if (path === '/admin/tokens') return 'tokens';
    if (path === '/admin/users') return 'users';
    return 'dashboard';
}

// Show the active page section and highlight nav
function showPage(page) {
    // Hide all page sections
    document.querySelectorAll('.page-section').forEach(el => {
        el.style.display = 'none';
    });

    // Show the target page
    const target = document.getElementById('page-' + page);
    if (target) {
        target.style.display = 'block';
    }

    // Highlight active nav link
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('data-page') === page) {
            link.style.backgroundColor = 'var(--primary-color)';
            link.style.color = '#fff';
            link.style.borderRadius = '4px';
        } else {
            link.style.backgroundColor = '';
            link.style.color = '';
        }
    });

    // Load data for the page
    if (page === 'dashboard') loadDashboard();
    else if (page === 'clients') loadClients();
    else if (page === 'tokens') loadTokens();
    else if (page === 'users') loadUsers();
}

// Client-side navigation (no full page reload)
function setupNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const page = this.getAttribute('data-page');
            const href = this.getAttribute('href');
            history.pushState({ page: page }, '', href);
            showPage(page);
        });
    });

    window.addEventListener('popstate', function(e) {
        showPage(getCurrentPage());
    });
}

// -- Dashboard --
async function loadDashboard() {
    try {
        const response = await fetch('/admin/api/dashboard');
        const data = await response.json();
        document.getElementById('total-clients').textContent = data.total_clients || 0;
        document.getElementById('total-users').textContent = data.total_users || 0;
        document.getElementById('active-tokens').textContent = data.active_tokens || 0;
        document.getElementById('total-tokens').textContent = data.total_tokens || 0;
    } catch (error) {
        console.error('Failed to fetch dashboard stats:', error);
    }
}

// -- Clients --
async function loadClients() {
    try {
        const response = await fetch('/admin/api/clients');
        const clients = await response.json();
        const tbody = document.querySelector('#clients-table tbody');

        if (clients && clients.length > 0) {
            tbody.innerHTML = clients.map(client => {
                // Parse grant_types if it's a JSON array string
                let grants = client.grant_types;
                try { grants = JSON.parse(grants).join(', '); } catch(_) {}
                return `
                <tr>
                    <td><code>${escapeHtml(client.client_id)}</code></td>
                    <td>${escapeHtml(client.name)}</td>
                    <td>${escapeHtml(client.scope)}</td>
                    <td>${escapeHtml(grants)}</td>
                    <td>${formatDate(client.created_at)}</td>
                    <td>
                        <button class="btn-danger btn-sm" onclick="deleteClient('${escapeHtml(client.id)}')">Delete</button>
                    </td>
                </tr>`;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6">No clients registered</td></tr>';
        }
    } catch (error) {
        console.error('Failed to fetch clients:', error);
        document.querySelector('#clients-table tbody').innerHTML =
            '<tr><td colspan="6">Failed to load clients</td></tr>';
    }
}

// -- Tokens --
async function loadTokens() {
    try {
        const response = await fetch('/admin/api/tokens');
        const tokens = await response.json();
        const tbody = document.querySelector('#tokens-table tbody');

        if (tokens && tokens.length > 0) {
            tbody.innerHTML = tokens.map(token => {
                let status = '';
                let statusClass = '';
                if (token.revoked) {
                    status = 'Revoked';
                    statusClass = 'status-error';
                } else if (token.expired) {
                    status = 'Expired';
                    statusClass = 'status-pending';
                } else {
                    status = 'Active';
                    statusClass = 'status-success';
                }

                const shortId = token.id.substring(0, 8) + '...';
                return `
                <tr>
                    <td><code title="${escapeHtml(token.id)}">${escapeHtml(shortId)}</code></td>
                    <td>${escapeHtml(token.client_id)}</td>
                    <td>${escapeHtml(token.user_id || '—')}</td>
                    <td>${escapeHtml(token.scope)}</td>
                    <td>${formatDate(token.expires_at)}</td>
                    <td><span class="status-badge ${statusClass}">${status}</span></td>
                    <td>
                        ${!token.revoked ? `<button class="btn-danger btn-sm" onclick="revokeToken('${escapeHtml(token.id)}')">Revoke</button>` : ''}
                    </td>
                </tr>`;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="7">No tokens found</td></tr>';
        }
    } catch (error) {
        console.error('Failed to fetch tokens:', error);
        document.querySelector('#tokens-table tbody').innerHTML =
            '<tr><td colspan="7">Failed to load tokens</td></tr>';
    }
}

// -- Users --
async function loadUsers() {
    try {
        const response = await fetch('/admin/api/users');
        const users = await response.json();
        const tbody = document.querySelector('#users-table tbody');

        if (users && users.length > 0) {
            tbody.innerHTML = users.map(user => {
                const roleClass = user.role === 'admin' ? 'status-badge status-success' : 'status-badge status-pending';
                const enabledClass = user.enabled ? 'status-badge status-success' : 'status-badge status-error';
                return `
                <tr>
                    <td>${escapeHtml(user.username)}</td>
                    <td>${escapeHtml(user.email)}</td>
                    <td><span class="${roleClass}">${escapeHtml(user.role)}</span></td>
                    <td><span class="${enabledClass}">${user.enabled ? 'Yes' : 'No'}</span></td>
                    <td>${formatDate(user.created_at)}</td>
                </tr>`;
            }).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="5">No users found</td></tr>';
        }
    } catch (error) {
        console.error('Failed to fetch users:', error);
        document.querySelector('#users-table tbody').innerHTML =
            '<tr><td colspan="5">Failed to load users</td></tr>';
    }
}

// -- Actions --
async function revokeToken(tokenId) {
    if (!confirm('Revoke this token?')) return;
    try {
        const response = await fetch(`/admin/api/tokens/${tokenId}/revoke`, { method: 'POST' });
        if (response.ok) {
            loadTokens();
            loadDashboard();
        } else {
            alert('Failed to revoke token');
        }
    } catch (error) {
        console.error('Failed to revoke token:', error);
        alert('Error revoking token');
    }
}

async function deleteClient(clientId) {
    if (!confirm('Delete this client? This cannot be undone.')) return;
    try {
        const response = await fetch(`/admin/api/clients/${clientId}`, { method: 'DELETE' });
        if (response.ok) {
            loadClients();
            loadDashboard();
        } else {
            alert('Failed to delete client');
        }
    } catch (error) {
        console.error('Failed to delete client:', error);
        alert('Error deleting client');
    }
}

// -- Utilities --
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        return new Date(dateStr).toLocaleString();
    } catch (_) {
        return dateStr;
    }
}

// Initialize charts (only on dashboard page)
function initCharts() {
    const tokenCtx = document.getElementById('tokenChart');
    if (tokenCtx) {
        new Chart(tokenCtx, {
            type: 'line',
            data: {
                labels: ['1h ago', '50m', '40m', '30m', '20m', '10m', 'Now'],
                datasets: [{
                    label: 'Tokens Issued',
                    data: [12, 19, 15, 25, 22, 30, 28],
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    const requestCtx = document.getElementById('requestChart');
    if (requestCtx) {
        new Chart(requestCtx, {
            type: 'bar',
            data: {
                labels: ['1h ago', '50m', '40m', '30m', '20m', '10m', 'Now'],
                datasets: [{
                    label: 'Requests',
                    data: [65, 78, 90, 81, 96, 105, 112],
                    backgroundColor: '#10b981',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }
}

// Auto-refresh current page data
function startAutoRefresh() {
    setInterval(() => {
        const page = getCurrentPage();
        if (page === 'dashboard') loadDashboard();
        else if (page === 'clients') loadClients();
        else if (page === 'tokens') loadTokens();
        else if (page === 'users') loadUsers();
    }, 30000);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    const page = getCurrentPage();
    showPage(page);
    initCharts();
    startAutoRefresh();
});
