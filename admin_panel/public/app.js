// Admin Panel Frontend
// Page is served at /music/ by Nginx which proxies to Node.js port 8000
// Nginx strips /music/ prefix, so:
//   fetch('api/settings')  → /music/api/settings → Node.js /api/settings ✓
//   fetch('/api/settings') → /api/settings       → Next.js (WRONG!) ✗
// Socket.io must use path: '/music/socket.io' so Nginx proxies it correctly

const socket = io({ path: '/music/socket.io' });

// State
let currentTab = 'dashboard';
let autoscroll = true;

// DOM
const navItems        = document.querySelectorAll('.nav-item');
const tabContents     = document.querySelectorAll('.tab-content');
const tabTitle        = document.getElementById('tabTitle');
const tabSubtitle     = document.getElementById('tabSubtitle');
const themeBtn        = document.getElementById('themeBtn');
const settingsForm    = document.getElementById('settingsForm');
const nightModeChk    = document.getElementById('night_mode');
const nightInputs     = document.getElementById('nightInputs');
const logConsole      = document.getElementById('logConsole');
const clearLogsBtn    = document.getElementById('clearLogsBtn');
const autoscrollBtn   = document.getElementById('autoscrollBtn');
const successAlert    = document.getElementById('successAlert');

// --- Tab Switching ---
navItems.forEach(item => {
    item.addEventListener('click', e => {
        e.preventDefault();
        switchTab(item.getAttribute('data-tab'));
    });
});

function switchTab(tab) {
    currentTab = tab;
    navItems.forEach(i => i.classList.toggle('active', i.getAttribute('data-tab') === tab));
    tabContents.forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));

    if (tab === 'dashboard') {
        tabTitle.textContent    = 'Dashboard';
        tabSubtitle.textContent = "Bot holati va oxirgi faollik ko'rsatkichi";
        fetchStats();
        fetchTodaySchedule();
    } else if (tab === 'settings') {
        tabTitle.textContent    = 'Sozlamalar';
        tabSubtitle.textContent = 'Botning asosiy ish koeffitsiyentlarini boshqarish';
        fetchSettings();
    } else if (tab === 'logs') {
        tabTitle.textContent    = 'Live Loglar';
        tabSubtitle.textContent = "Tizim jarayonlarini real vaqtda kuzatib boring";
        scrollToBottom();
    }
}

// --- Theme ---
themeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    themeBtn.querySelector('i').className       = isDark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    themeBtn.querySelector('span').textContent  = isDark ? 'Kunduzgi Rejim' : 'Tungi Rejim';
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
});

// Load saved theme
const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.body.classList.add('dark-mode');
    themeBtn.querySelector('i').className      = 'fa-solid fa-sun';
    themeBtn.querySelector('span').textContent = 'Kunduzgi Rejim';
}

// --- Night Mode Toggle ---
nightModeChk.addEventListener('change', () => {
    nightInputs.style.display = nightModeChk.checked ? 'grid' : 'none';
});

// --- Settings: Fetch ---
async function fetchSettings() {
    try {
        // NOTE: relative path 'api/settings' (no leading slash!)
        const res  = await fetch('api/settings');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        document.getElementById('planning_hour').value     = data.planning_hour    ?? 5;
        document.getElementById('daily_post_count').value  = data.daily_post_count ?? 5;
        document.getElementById('demo_duration').value     = data.demo_duration    ?? 30;
        document.getElementById('target_search_bot').value = data.target_search_bot ?? '@Zoryuklabot';
        document.getElementById('source_channels').value   = data.source_channels  ?? '';

        const isNight = data.night_mode === 'true';
        nightModeChk.checked          = isNight;
        nightInputs.style.display     = isNight ? 'grid' : 'none';

        document.getElementById('night_start').value = data.night_start ?? 23;
        document.getElementById('night_end').value   = data.night_end   ?? 7;

        // Dashboard cards
        const ph = String(data.planning_hour ?? '5');
        document.getElementById('statDailyLimit').textContent   = data.daily_post_count ?? '0';
        document.getElementById('statSearchBot').textContent    = data.target_search_bot ?? '—';
        document.getElementById('statPlanningHour').textContent = `${ph.padStart(2,'0')}:00`;
        document.getElementById('statDemoDuration').textContent = `${data.demo_duration ?? '30'}s`;
        document.getElementById('statNightMode').textContent    = isNight
            ? `Faol (${data.night_start ?? 23}:00 – ${data.night_end ?? 7}:00)`
            : "O'chirilgan";
    } catch (err) {
        console.error('Settings fetch error:', err);
    }
}

// --- Settings: Save ---
settingsForm.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(settingsForm);

    const body = {
        planning_hour:     fd.get('planning_hour'),
        daily_post_count:  fd.get('daily_post_count'),
        demo_duration:     fd.get('demo_duration'),
        target_search_bot: fd.get('target_search_bot'),
        source_channels:   fd.get('source_channels'),
        night_mode:        nightModeChk.checked ? 'true' : 'false',
        night_start:       document.getElementById('night_start').value || '23',
        night_end:         document.getElementById('night_end').value   || '7',
        new_password:      document.getElementById('new_password').value || ''
    };

    try {
        // NOTE: relative path 'api/settings' (no leading slash!)
        const res    = await fetch('api/settings', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(body)
        });
        const result = await res.json();

        if (result.success) {
            document.getElementById('new_password').value = ''; // clear password field
            showSuccess();
            fetchSettings();
        } else {
            alert('Xatolik: ' + (result.error || 'Noma\'lum xato'));
        }
    } catch (err) {
        console.error('Settings save error:', err);
        alert('Server bilan bog\'lanishda xatolik yuz berdi: ' + err.message);
    }
});

function showSuccess() {
    successAlert.style.display = 'block';
    successAlert.style.opacity = '1';
    setTimeout(() => {
        successAlert.style.transition = 'opacity 0.4s';
        successAlert.style.opacity    = '0';
        setTimeout(() => {
            successAlert.style.display    = 'none';
            successAlert.style.opacity    = '1';
            successAlert.style.transition = '';
        }, 400);
    }, 3000);
}

// --- Stats ---
async function fetchStats() {
    try {
        // NOTE: relative path (no leading slash)
        const res  = await fetch('api/stats');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        document.getElementById('statTotalPosted').textContent = data.total_posted ?? '0';

        const list = document.getElementById('recentTracksList');
        list.innerHTML = '';

        if (data.recent_tracks && data.recent_tracks.length > 0) {
            data.recent_tracks.forEach(track => {
                const li   = document.createElement('li');
                li.className = 'recent-item';
                const d    = new Date(track.post_date);
                const time = d.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' });
                const date = d.toLocaleDateString('uz-UZ', { day: 'numeric', month: 'short' });
                li.innerHTML = `
                    <div class="recent-track-info">
                        <h4>${escapeHTML(track.artist)} – ${escapeHTML(track.title)}</h4>
                        <p><i class="fa-solid fa-check-double text-success"></i> Kanalga yuklandi</p>
                    </div>
                    <span class="recent-date">${date}, ${time}</span>
                `;
                list.appendChild(li);
            });
        } else {
            list.innerHTML = `<li class="empty-state">Hozircha faollik yo'q.</li>`;
        }
    } catch (err) {
        console.error('Stats fetch error:', err);
    }
}

// --- Today's Schedule ---
async function fetchTodaySchedule() {
    const list = document.getElementById('todayScheduleList');
    if (!list) return;
    list.innerHTML = '<li class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> Yuklanmoqda...</li>';
    try {
        const res  = await fetch('api/schedule/today');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        list.innerHTML = '';
        if (data.schedule && data.schedule.length > 0) {
            let postedCount = 0;
            let pendingCount = 0;
            data.schedule.forEach((entry, idx) => {
                if (entry.is_posted) postedCount++; else pendingCount++;
                const li = document.createElement('li');
                li.className = 'recent-item';
                const t = new Date(entry.post_time_local);
                const timeStr = t.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' });
                const statusIcon = entry.is_posted
                    ? '<i class="fa-solid fa-check-double" style="color:var(--success)"></i> Joylandi'
                    : '<i class="fa-solid fa-clock" style="color:var(--warning)"></i> Kutmoqda';
                li.innerHTML = `
                    <div class="recent-track-info">
                        <h4><span style="color:var(--text-secondary);font-weight:400;font-size:12px;margin-right:6px;">${idx + 1}.</span>${escapeHTML(entry.artist || '—')} – ${escapeHTML(entry.title || '—')}</h4>
                        <p>${statusIcon}</p>
                    </div>
                    <span class="recent-date">${timeStr}</span>
                `;
                list.appendChild(li);
            });
            // Summary badge
            const summary = document.createElement('li');
            summary.style.cssText = 'padding:10px 14px;font-size:12px;color:var(--text-secondary);border-top:1px solid var(--border-color);display:flex;gap:16px;';
            summary.innerHTML = `
                <span><i class="fa-solid fa-check-double" style="color:var(--success)"></i> Joylangan: <b>${postedCount}</b></span>
                <span><i class="fa-solid fa-clock" style="color:var(--warning)"></i> Kutmoqda: <b>${pendingCount}</b></span>
                <span><i class="fa-solid fa-music"></i> Jami: <b>${data.schedule.length}</b></span>
            `;
            list.appendChild(summary);
        } else {
            list.innerHTML = '<li class="empty-state">Bugun uchun reja topilmadi. Rejalashtirish tugmasini bosing.</li>';
        }
    } catch (err) {
        console.error('Schedule fetch error:', err);
        list.innerHTML = '<li class="empty-state">Rejalanish jadvalini yuklab bo\'lmadi.</li>';
    }
}

document.getElementById('refreshScheduleBtn').addEventListener('click', fetchTodaySchedule);

// --- Live Logs ---
autoscrollBtn.addEventListener('click', () => {
    autoscroll = !autoscroll;
    autoscrollBtn.classList.toggle('active', autoscroll);
});

clearLogsBtn.addEventListener('click', () => {
    logConsole.innerHTML = 'Log console cleared.\n';
});

function formatLogLine(line) {
    if (!line.trim()) return '';
    let cls = 'log-line';
    if      (line.includes('SUCCESS') || line.includes('✅')) cls += ' log-success';
    else if (line.includes('ERROR')   || line.includes('❌')) cls += ' log-error';
    else if (line.includes('WARNING') || line.includes('⚠️'))cls += ' log-warning';
    else if (line.includes('CRITICAL')|| line.includes('🚨')) cls += ' log-critical';
    else if (line.includes('INFO'))                            cls += ' log-info';
    return `<span class="${cls}">${escapeHTML(line)}\n</span>`;
}

function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/[&<>'"]/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

socket.on('connect', () => {
    console.log('✅ Socket.io connected');
});
socket.on('connect_error', err => {
    console.error('❌ Socket.io error:', err.message);
});

socket.on('logs', data => {
    logConsole.innerHTML = data.split('\n').map(formatLogLine).join('');
    scrollToBottom();
});

socket.on('logs_chunk', chunk => {
    logConsole.innerHTML += chunk.split('\n').map(formatLogLine).join('');
    scrollToBottom();
});

function scrollToBottom() {
    if (autoscroll) {
        const w = logConsole.parentElement;
        w.scrollTop = w.scrollHeight;
    }
}

// --- Bot Control & Status Logic ---
const btnBotStart = document.getElementById('btnBotStart');
const btnBotStop = document.getElementById('btnBotStop');
const btnBotRestart = document.getElementById('btnBotRestart');
const btnBotPostNow = document.getElementById('btnBotPostNow');
const btnBotReplan = document.getElementById('btnBotReplan');

const botStatusBadge = document.getElementById('botStatusBadge');
const botStatusText = document.getElementById('botStatusText');
const botControlStatusBadge = document.getElementById('botControlStatusBadge');
const botControlStatusText = document.getElementById('botControlStatusText');

async function checkBotStatus() {
    try {
        const res = await fetch('api/bot/status');
        if (!res.ok) throw new Error('Status request failed');
        const data = await res.json();
        
        updateStatusUI(data.running);
    } catch (err) {
        console.error('Bot status check error:', err);
        updateStatusUI(false);
    }
}

function updateStatusUI(isRunning) {
    if (isRunning) {
        // Active
        botStatusBadge.className = 'status-badge active';
        botStatusText.textContent = 'Bot: Faol';
        
        botControlStatusBadge.className = 'status-badge active';
        botControlStatusText.textContent = 'Ishlamoqda';
    } else {
        // Inactive
        botStatusBadge.className = 'status-badge inactive';
        botStatusText.textContent = "Bot: O'chgan";
        
        botControlStatusBadge.className = 'status-badge inactive';
        botControlStatusText.textContent = "To'xtatilgan";
    }
}

async function sendBotAction(actionPath, successMessage) {
    try {
        const res = await fetch(`api/bot/${actionPath}`, { method: 'POST' });
        if (!res.ok) throw new Error('Action request failed');
        const data = await res.json();
        
        if (data.success) {
            showSuccessBanner(successMessage || data.message);
            // Instantly poll status to show transition
            setTimeout(checkBotStatus, 1500);
        } else {
            alert('Xatolik: ' + (data.error || 'Noma\'lum xatolik'));
        }
    } catch (err) {
        console.error(`Bot action error (${actionPath}):`, err);
        alert('Server bilan bog\'lanishda xato: ' + err.message);
    }
}

function showSuccessBanner(message) {
    const banner = document.getElementById('successAlert');
    banner.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span></span>`;
    banner.querySelector('span').textContent = message;
    showSuccess();
}

// Bind Button Listeners
btnBotStart.addEventListener('click', () => sendBotAction('start', 'Bot muvaffaqiyatli ishga tushirildi!'));
btnBotStop.addEventListener('click', () => sendBotAction('stop', 'Bot muvaffaqiyatli to\'xtatildi!'));
btnBotRestart.addEventListener('click', () => sendBotAction('restart', 'Bot qayta ishga tushirildi!'));
btnBotPostNow.addEventListener('click', () => sendBotAction('post-now', 'Musiqa joylash buyrug\'i yuborildi (10s ichida bajariladi)!'));
btnBotReplan.addEventListener('click', () => sendBotAction('replan', 'Jadvalni yangilash buyrug\'i yuborildi (10s ichida bajariladi)!'));

// --- Init ---
fetchSettings();
fetchStats();
checkBotStatus();

// Polling intervals
setInterval(() => { if (currentTab === 'dashboard') fetchStats(); }, 30000);
setInterval(checkBotStatus, 5000);
