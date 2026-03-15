/**
 * FinBot CTF - Hacker Toolkit: Dead Drop
 */

const DeadDrop = {
    messages: [],
    selectedId: null,
    isLoading: false,
};

document.addEventListener('DOMContentLoaded', () => {
    loadDeadDrop();
});

async function loadDeadDrop() {
    if (DeadDrop.isLoading) return;
    DeadDrop.isLoading = true;

    showLoading(true);

    try {
        const data = await CTF.getDeadDrop({ limit: 100 });
        DeadDrop.messages = data.messages || [];

        updateModuleCount(DeadDrop.messages.length);
        renderMessageList();

        if (DeadDrop.selectedId) {
            const still = DeadDrop.messages.find(m => m.id === DeadDrop.selectedId);
            if (!still) DeadDrop.selectedId = null;
        }
        if (DeadDrop.selectedId) {
            showMessage(DeadDrop.selectedId);
        }
    } catch (err) {
        console.error('Failed to load dead drop:', err);
    } finally {
        DeadDrop.isLoading = false;
        showLoading(false);
    }
}

function showLoading(loading) {
    const el = {
        loading: document.getElementById('dead-drop-loading'),
        content: document.getElementById('dead-drop-content'),
        empty: document.getElementById('dead-drop-empty'),
    };

    if (loading) {
        el.loading.classList.remove('hidden');
        el.content.classList.add('hidden');
        el.empty.classList.add('hidden');
    } else if (DeadDrop.messages.length === 0) {
        el.loading.classList.add('hidden');
        el.content.classList.add('hidden');
        el.empty.classList.remove('hidden');
    } else {
        el.loading.classList.add('hidden');
        el.content.classList.remove('hidden');
        el.empty.classList.add('hidden');
    }
}

function updateModuleCount(count) {
    document.getElementById('dead-drop-count').textContent = count;
}

function renderMessageList() {
    const list = document.getElementById('dead-drop-list');
    if (!list) return;

    if (DeadDrop.messages.length === 0) {
        list.innerHTML = '';
        return;
    }

    list.innerHTML = DeadDrop.messages.map(msg => {
        const isActive = msg.id === DeadDrop.selectedId;
        const unreadClass = !msg.is_read ? 'unread' : '';
        const activeClass = isActive ? 'active' : '';
        const toAddrs = (msg.to_addresses || []).join(', ');
        const timeStr = formatRelativeTime(msg.created_at);

        return `
            <div class="dd-msg-item ${unreadClass} ${activeClass}" onclick="selectMessage(${msg.id})">
                <div class="flex items-start justify-between gap-2 mb-1">
                    <div class="dd-subject text-sm truncate flex-1">${escapeHtml(msg.subject)}</div>
                    ${!msg.is_read ? '<div class="w-2 h-2 rounded-full bg-ctf-primary shrink-0 mt-1.5"></div>' : ''}
                </div>
                <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-ctf-danger/70 font-mono truncate">${escapeHtml(toAddrs)}</span>
                    <span class="text-xs text-text-secondary/50 shrink-0">${timeStr}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function selectMessage(id) {
    DeadDrop.selectedId = id;
    renderMessageList();
    await showMessage(id);
}

async function showMessage(id) {
    const detail = document.getElementById('reading-detail');
    const empty = document.getElementById('reading-empty');
    if (!detail || !empty) return;

    try {
        const data = await CTF.getDeadDropMessage(id);
        if (data.error) {
            empty.classList.remove('hidden');
            detail.classList.add('hidden');
            return;
        }

        const msg = data.message;

        // Mark as read locally
        const local = DeadDrop.messages.find(m => m.id === id);
        if (local) {
            local.is_read = true;
            renderMessageList();
        }

        const toHtml = renderAddresses('To', msg.to_addresses);
        const ccHtml = msg.cc_addresses ? renderAddresses('CC', msg.cc_addresses) : '';
        const bccHtml = msg.bcc_addresses ? renderAddresses('BCC', msg.bcc_addresses) : '';

        detail.innerHTML = `
            <div class="mb-6">
                <div class="flex items-start justify-between gap-4 mb-4">
                    <h3 class="text-xl font-semibold text-text-bright">${escapeHtml(msg.subject)}</h3>
                    <span class="shrink-0 px-2 py-0.5 rounded text-xs font-mono bg-ctf-danger/15 text-ctf-danger border border-ctf-danger/20">INTERCEPTED</span>
                </div>
                <div class="space-y-2 text-sm">
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">From</span>
                        <span class="dd-addr-tag dd-addr-internal">${escapeHtml(msg.from_address || msg.sender_name)}</span>
                    </div>
                    ${toHtml}
                    ${ccHtml}
                    ${bccHtml}
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">Date</span>
                        <span class="text-text-secondary text-xs">${formatDateTime(msg.created_at)}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">Type</span>
                        <span class="text-text-secondary text-xs font-mono">${escapeHtml(msg.message_type)}</span>
                    </div>
                </div>
            </div>
            <div class="dd-body">${escapeHtml(msg.body)}</div>
        `;

        empty.classList.add('hidden');
        detail.classList.remove('hidden');
    } catch (err) {
        console.error('Failed to load message:', err);
    }
}

function renderAddresses(label, addresses) {
    if (!addresses || addresses.length === 0) return '';
    const tags = addresses.map(addr => {
        const cls = isInternalAddress(addr) ? 'dd-addr-internal' : 'dd-addr-external';
        const icon = isInternalAddress(addr)
            ? ''
            : '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>';
        return `<span class="dd-addr-tag ${cls}">${icon}${escapeHtml(addr)}</span>`;
    }).join(' ');
    return `<div class="flex items-center gap-2 flex-wrap"><span class="dd-header-label">${label}</span>${tags}</div>`;
}

function isInternalAddress(addr) {
    return addr && addr.endsWith('.finbot');
}

function activateModule(module) {
    if (module === 'dead-drop') {
        loadDeadDrop();
    }
}

function formatRelativeTime(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return 'now';
    if (diffMin < 60) return `${diffMin}m`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
