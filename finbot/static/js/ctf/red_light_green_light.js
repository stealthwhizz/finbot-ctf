/**
 * Red Light/Green Light -- live adversarial defense challenge.
 * Polls /ctf/api/v1/rlgl/status and /feed every 2s. No WebSocket wiring
 * here: RLGL is the first UI consumer of broadcast_activity() on the
 * backend, and a battle-tested 2s poll is simpler and more reliable to
 * ship than a first-of-its-kind topic subscription for equivalent
 * perceived latency on a slow-moving health meter.
 * # ponytail: polling, switch to a WS subscription if 2s feels laggy in practice.
 */

const RLGL_POLL_MS = 2000;
let rlglPollTimer = null;
let rlglLastStatus = null;

function rlglServerLabel(serverType) {
    const labels = {
        systemutils: 'SystemUtils',
        finstripe: 'FinStripe',
        findrive: 'FinDrive',
        finmail: 'FinMail',
        taxcalc: 'TaxCalc',
    };
    return labels[serverType] || serverType;
}

function renderToggles(servers) {
    const container = document.getElementById('mcp-toggles');
    container.innerHTML = servers.map(s => `
        <div class="rlgl-toggle ${s.enabled ? 'enabled' : 'disabled'}">
            <div>
                <div class="text-sm font-medium text-text-bright">${rlglServerLabel(s.server_type)}</div>
                <div class="text-xs ${s.enabled ? 'text-ctf-accent' : 'text-ctf-danger'}">${s.enabled ? 'ENABLED' : 'DISABLED'}</div>
            </div>
            <button
                class="text-xs px-3 py-1.5 rounded-lg border transition-colors ${s.enabled ? 'border-ctf-danger/40 text-ctf-danger hover:bg-ctf-danger/10' : 'border-ctf-accent/40 text-ctf-accent hover:bg-ctf-accent/10'}"
                onclick="rlglToggle('${s.server_type}')"
            >${s.enabled ? 'Disable' : 'Enable'}</button>
        </div>
    `).join('');
}

function renderHealth(health) {
    const bar = document.getElementById('health-bar');
    const value = document.getElementById('health-value');
    value.textContent = health;
    bar.style.width = `${Math.max(0, health)}%`;
    let color = '#06ffa5';
    if (health <= 30) color = '#ff3366';
    else if (health <= 60) color = '#ffb800';
    bar.style.background = color;
    value.style.color = color;
}

function renderTimer(seconds) {
    const el = document.getElementById('time-remaining');
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    el.textContent = `${m}:${String(s).padStart(2, '0')}`;
}

function renderResult(status) {
    const banner = document.getElementById('rlgl-result');
    if (status === 'active') {
        banner.classList.add('hidden');
        return;
    }
    banner.classList.remove('hidden');
    if (status === 'won') {
        banner.className = 'glass-card p-6 mb-6 text-center border border-ctf-accent/40';
        banner.innerHTML = '<div class="text-lg font-bold text-ctf-accent">Session survived — business health held.</div>';
    } else {
        banner.className = 'glass-card p-6 mb-6 text-center border border-ctf-danger/40';
        banner.innerHTML = '<div class="text-lg font-bold text-ctf-danger">Business health hit zero — session lost.</div>';
    }
}

function showResultModal(status) {
    const modal = document.getElementById('rlgl-modal');
    const icon = document.getElementById('rlgl-modal-icon');
    const title = document.getElementById('rlgl-modal-title');
    const subtitle = document.getElementById('rlgl-modal-subtitle');

    if (status === 'won') {
        icon.textContent = '🏆';
        title.textContent = 'YOU WIN';
        title.className = 'text-2xl font-bold mb-2 text-ctf-accent';
        subtitle.textContent = 'Business health held for the full session. Nice defense.';
    } else {
        icon.textContent = '💀';
        title.textContent = 'YOU LOST';
        title.className = 'text-2xl font-bold mb-2 text-ctf-danger';
        subtitle.textContent = 'Business health hit zero before the session ended.';
    }
    modal.classList.remove('hidden');
}

function hideResultModal() {
    document.getElementById('rlgl-modal').classList.add('hidden');
}

function renderFeed(items) {
    const container = document.getElementById('rlgl-feed');
    if (!items.length) {
        container.innerHTML = '<div class="p-6 text-center text-text-secondary text-sm">No activity yet.</div>';
        return;
    }
    container.innerHTML = items.slice().reverse().map(item => {
        let cls = 'neutral';
        if (item.event_type && item.event_type.endsWith('mcp_auto_reenabled')) cls = 'reenabled';
        else if (item.event_type && item.event_type.endsWith('health_regen')) cls = 'regen';
        else if (item.details && item.details.blocked === true) cls = 'blocked';
        else if (item.details && item.details.blocked === false) cls = 'landed';
        return `<div class="rlgl-feed-item ${cls}">${item.summary}</div>`;
    }).join('');
}

async function rlglFetch(endpoint, options = {}) {
    return CTF.fetch(`/rlgl${endpoint}`, options);
}

async function rlglPoll() {
    try {
        const status = await rlglFetch('/status');
        if (!status.active && status.status !== 'won' && status.status !== 'lost') {
            document.getElementById('rlgl-idle').classList.remove('hidden');
            document.getElementById('rlgl-session').classList.add('hidden');
            return;
        }
        document.getElementById('rlgl-idle').classList.add('hidden');
        document.getElementById('rlgl-session').classList.remove('hidden');

        renderHealth(status.health ?? 0);
        renderTimer(status.seconds_remaining ?? 0);
        renderResult(status.status);
        renderToggles(status.mcp_servers);

        // Shown on every poll while finished (not just the live transition) so
        // refreshing the page after a session already ended still surfaces
        // the result and the Try Again button, not just the inline banner.
        if (status.status === 'won' || status.status === 'lost') {
            showResultModal(status.status);
        }
        rlglLastStatus = status.status;

        const feed = await rlglFetch('/feed');
        renderFeed(feed.items);

        if (status.status !== 'active' && rlglPollTimer) {
            clearInterval(rlglPollTimer);
            rlglPollTimer = setInterval(rlglPoll, RLGL_POLL_MS * 3); // slow poll once finished
        }
    } catch (error) {
        console.error('RLGL poll failed:', error);
    }
}

async function rlglToggle(serverType) {
    try {
        await rlglFetch(`/toggle/${serverType}`, { method: 'POST' });
        await rlglPoll();
    } catch (error) {
        showToast(error.message || 'Failed to toggle server', 'error');
    }
}

async function rlglStart() {
    try {
        hideResultModal();
        await rlglFetch('/start', { method: 'POST' });
        rlglLastStatus = 'active';
        document.getElementById('rlgl-idle').classList.add('hidden');
        document.getElementById('rlgl-session').classList.remove('hidden');
        if (rlglPollTimer) clearInterval(rlglPollTimer);
        rlglPollTimer = setInterval(rlglPoll, RLGL_POLL_MS);
        await rlglPoll();
    } catch (error) {
        showToast('Failed to start session', 'error');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    if (startBtn) startBtn.addEventListener('click', rlglStart);

    const retryBtn = document.getElementById('rlgl-modal-retry');
    if (retryBtn) retryBtn.addEventListener('click', rlglStart);

    // Resume polling if a session is already active on page load
    rlglPoll().then(() => {
        if (!rlglPollTimer) {
            rlglPollTimer = setInterval(rlglPoll, RLGL_POLL_MS);
        }
    });

    // Browsers throttle setInterval in backgrounded tabs (often to ~1/min or
    // less). A 3-minute session can finish while the tab is inactive, and
    // the throttled timer may take a while to catch up once you switch
    // back. Force an immediate poll on regaining focus/visibility so the
    // win/loss modal shows right away instead of waiting on the next
    // throttled tick.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') rlglPoll();
    });
    window.addEventListener('focus', rlglPoll);
});

window.rlglToggle = rlglToggle;
