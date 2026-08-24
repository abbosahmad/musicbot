// server.js - Premium Node.js Admin Panel with Auth & Bot Control
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env') });

const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { Pool } = require('pg');
const fs = require('fs');
const { execFile } = require('child_process');

const app = express();
const server = http.createServer(app);

const io = new Server(server, {
  path: '/socket.io',
  cors: { origin: process.env.ADMIN_PANEL_ORIGIN || 'https://abboscoder.uz' }
});

const crypto = require('crypto');

const PORT = 8000;
const ADMIN_PASSWORD_ENV = process.env.ADMIN_PASSWORD;
if (!ADMIN_PASSWORD_ENV) {
  console.error('❌ ADMIN_PASSWORD environment variable is not set! Exiting...');
  process.exit(1);
}
let ADMIN_PASSWORD = ADMIN_PASSWORD_ENV;

// Persistent session management
const sessionsPath = path.resolve(__dirname, '../session/admin_sessions.json');

function loadSessions() {
  try {
    if (fs.existsSync(sessionsPath)) {
      const data = fs.readFileSync(sessionsPath, 'utf8');
      return JSON.parse(data);
    }
  } catch (err) {
    console.error('Failed to load sessions:', err);
  }
  return {};
}

function saveSessions(sessions) {
  try {
    fs.mkdirSync(path.dirname(sessionsPath), { recursive: true });
    fs.writeFileSync(sessionsPath, JSON.stringify(sessions, null, 2), 'utf8');
  } catch (err) {
    console.error('Failed to save sessions:', err);
  }
}

let activeSessions = loadSessions();

function cleanExpiredSessions() {
  const now = Date.now();
  let changed = false;
  for (const [token, expires] of Object.entries(activeSessions)) {
    if (now > expires) {
      delete activeSessions[token];
      changed = true;
    }
  }
  if (changed) saveSessions(activeSessions);
}
setInterval(cleanExpiredSessions, 3600 * 1000); // Clean every hour

// Helper to persistently update key in .env file
function updateEnvFile(key, value) {
  try {
    const envPath = path.resolve(__dirname, '../.env');
    if (!fs.existsSync(envPath)) {
      fs.writeFileSync(envPath, `${key}=${value}\n`, 'utf8');
      return;
    }
    let content = fs.readFileSync(envPath, 'utf8');
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`^${escapedKey}=.*$`, 'm');
    if (regex.test(content)) {
      content = content.replace(regex, `${key}=${value}`);
    } else {
      content += `\n${key}=${value}`;
    }
    fs.writeFileSync(envPath, content, 'utf8');
  } catch (err) {
    console.error('Failed to write .env file:', err);
  }
}

// PostgreSQL Connection
if (!process.env.DATABASE_URL) {
  console.error('❌ DATABASE_URL environment variable is not set! Exiting...');
  process.exit(1);
}
const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// Middleware for security headers
app.use((req, res, next) => {
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'same-origin');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.socket.io; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; img-src 'self' data:; connect-src 'self' ws: wss:;");
  next();
});

// Middleware for parsing requests
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Helper to manually parse cookies
function getCookie(req, name) {
  const cookieHeader = req.headers.cookie;
  if (!cookieHeader) return null;
  const cookies = cookieHeader.split(';').reduce((acc, cookie) => {
    const parts = cookie.trim().split('=');
    const key = parts[0];
    const value = parts.slice(1).join('=');
    acc[key] = value;
    return acc;
  }, {});
  return cookies[name] || null;
}

// In-memory rate limiter for login
const loginAttempts = new Map();
function rateLimitLogin(req, res, next) {
  const ip = req.ip || req.headers['x-forwarded-for'] || req.socket.remoteAddress;
  const now = Date.now();
  const limitTime = 60 * 1000; // 1 minute
  const maxAttempts = 5;

  if (loginAttempts.has(ip)) {
    const data = loginAttempts.get(ip);
    if (now - data.lastAttempt > limitTime) {
      data.count = 1;
      data.lastAttempt = now;
    } else {
      data.count += 1;
      if (data.count > maxAttempts) {
        return res.status(429).json({ success: false, error: 'Juda ko\'p urinishlar! Iltimos, 1 daqiqa kuting.' });
      }
    }
  } else {
    loginAttempts.set(ip, { count: 1, lastAttempt: now });
  }
  next();
}

// Authentication Middleware
function requireAuth(req, res, next) {
  const normalizedPath = req.path.toLowerCase();
  
  // Allow login page and API login endpoint
  if (normalizedPath === '/login' || normalizedPath === '/login.html' || normalizedPath === '/api/login') {
    return next();
  }

  const token = getCookie(req, 'auth_token');
  if (token && activeSessions[token] && Date.now() < activeSessions[token]) {
    return next();
  }

  // Redirect HTML requests to login
  const acceptHeader = req.headers['accept'] || '';
  if (acceptHeader.includes('text/html')) {
    res.redirect('login');
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
}

// Apply authentication middleware
app.use(requireAuth);

// Route for extensionless /login
app.get('/login', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'login.html'));
});

// Redirect login.html to login
app.get('/login.html', (req, res) => {
  res.redirect(301, 'login');
});

// Redirect index.html to root /
app.get('/index.html', (req, res) => {
  res.redirect(301, './');
});

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));


// DB Connection Check
pool.connect((err, client, release) => {
  if (err) {
    console.error('❌ PostgreSQL connection error:', err.message);
  } else {
    console.log('✅ Connected to PostgreSQL successfully!');
    release();
  }
});

// Helper for safe shell execution (no shell spawned)
function runCommand(cmd, args) {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, (err, stdout, stderr) => {
      if (err) return reject(err);
      resolve(stdout.trim());
    });
  });
}

// Auth API
app.post('/api/login', rateLimitLogin, (req, res) => {
  const { password } = req.body;
  console.log(`[Login Attempt] Received login attempt (password length: ${password ? password.length : 0})`);
  if (password === ADMIN_PASSWORD) {
    const token = crypto.randomBytes(32).toString('hex');
    const expires = Date.now() + 86400 * 7 * 1000; // 7 days
    activeSessions[token] = expires;
    saveSessions(activeSessions);

    const isSecure = req.secure || req.headers['x-forwarded-proto'] === 'https';
    const secureFlag = isSecure ? '; Secure' : '';
    res.setHeader('Set-Cookie', `auth_token=${token}; Max-Age=${86400 * 7}; HttpOnly${secureFlag}; Path=/; SameSite=Lax`);
    res.json({ success: true });
  } else {
    res.status(401).json({ success: false, error: 'Parol noto\'g\'ri!' });
  }
});

// Bot Control APIs
app.get('/api/bot/status', async (req, res) => {
  try {
    const status = await runCommand('systemctl', ['is-active', 'musicbot']);
    res.json({ running: status === 'active' });
  } catch (err) {
    res.json({ running: false });
  }
});

app.post('/api/bot/start', async (req, res) => {
  try {
    await runCommand('systemctl', ['start', 'musicbot']);
    console.log('✅ Bot started via Web Panel');
    res.json({ success: true, message: 'Bot ishga tushirildi!' });
  } catch (err) {
    console.error('Start error:', err);
    res.status(500).json({ error: 'Botni ishga tushirishda xato' });
  }
});

app.post('/api/bot/stop', async (req, res) => {
  try {
    await runCommand('systemctl', ['stop', 'musicbot']);
    console.log('❌ Bot stopped via Web Panel');
    res.json({ success: true, message: 'Bot to\'xtatildi!' });
  } catch (err) {
    console.error('Stop error:', err);
    res.status(500).json({ error: 'Botni to\'xtatishda xato' });
  }
});

app.post('/api/bot/restart', async (req, res) => {
  try {
    await runCommand('systemctl', ['restart', 'musicbot']);
    console.log('🔄 Bot restarted via Web Panel');
    res.json({ success: true, message: 'Bot qayta yuklandi!' });
  } catch (err) {
    console.error('Restart error:', err);
    res.status(500).json({ error: 'Botni qayta yuklashda xato' });
  }
});

app.post('/api/bot/post-now', async (req, res) => {
  try {
    await pool.query(
      "INSERT INTO bot_settings (key, value) VALUES ('action_trigger', 'post_now') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    );
    console.log('⚡ Manual post action triggered via Web Panel');
    res.json({ success: true, message: 'Musiqa joylash buyrug\'i yuborildi!' });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Musiqa joylash buyrug\'ini yuborishda xato' });
  }
});

app.post('/api/bot/replan', async (req, res) => {
  try {
    await pool.query(
      "INSERT INTO bot_settings (key, value) VALUES ('action_trigger', 'replan') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    );
    console.log('⚡ Replan action triggered via Web Panel');
    res.json({ success: true, message: 'Jadvalni yangilash buyrug\'i yuborildi!' });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Jadvalni yangilash buyrug\'ini yuborishda xato' });
  }
});

// Settings & Stats APIs
app.get('/api/settings', async (req, res) => {
  try {
    const result = await pool.query('SELECT key, value FROM bot_settings');
    const settings = {};
    result.rows.forEach(row => {
      settings[row.key] = row.value;
    });
    res.json(settings);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error fetching settings' });
  }
});

app.post('/api/settings', async (req, res) => {
  try {
    const {
      planning_hour,
      daily_post_count,
      clean_source_channels,
      direct_source_channels,
      source_channels,
      main_channel_name,
      main_channel_link,
      demo_duration,
      night_mode,
      night_start,
      night_end,
      target_search_bot,
      new_password
    } = req.body;

    // Input validation
    if (planning_hour !== undefined) {
      const hour = parseInt(planning_hour);
      if (isNaN(hour) || hour < 0 || hour > 23) {
        return res.status(400).json({ error: 'Rejalashtirish soati 0 va 23 oralig\'ida bo\'lishi kerak!' });
      }
    }
    if (daily_post_count !== undefined) {
      const count = parseInt(daily_post_count);
      if (isNaN(count) || count < 1 || count > 100) {
        return res.status(400).json({ error: 'Kunlik postlar soni 1 va 100 oralig\'ida bo\'lishi kerak!' });
      }
    }
    if (night_start !== undefined) {
      const ns = parseInt(night_start);
      if (isNaN(ns) || ns < 0 || ns > 23) {
        return res.status(400).json({ error: 'Tun rejimi boshlanishi 0 va 23 oralig\'ida bo\'lishi kerak!' });
      }
    }
    if (night_end !== undefined) {
      const ne = parseInt(night_end);
      if (isNaN(ne) || ne < 0 || ne > 23) {
        return res.status(400).json({ error: 'Tun rejimi tugashi 0 va 23 oralig\'ida bo\'lishi kerak!' });
      }
    }

    // Check if new password is provided and not empty
    if (new_password && new_password.trim() !== '') {
      const cleanPass = new_password.trim();
      if (cleanPass.length < 8) {
        return res.status(400).json({ error: 'Yangi parol kamida 8 ta belgidan iborat bo\'lishi kerak!' });
      }
      updateEnvFile('ADMIN_PASSWORD', cleanPass);
      ADMIN_PASSWORD = cleanPass;

      // Revoke all existing sessions for security
      activeSessions = {};

      // Generate a new session token for the current user
      const token = crypto.randomBytes(32).toString('hex');
      const expires = Date.now() + 86400 * 7 * 1000;
      activeSessions[token] = expires;
      saveSessions(activeSessions);

      const isSecure = req.secure || req.headers['x-forwarded-proto'] === 'https';
      const secureFlag = isSecure ? '; Secure' : '';
      res.setHeader('Set-Cookie', `auth_token=${token}; Max-Age=${86400 * 7}; HttpOnly${secureFlag}; Path=/; SameSite=Lax`);
      console.log('🔒 Admin password updated and all existing sessions revoked!');
    }

    const updates = {};
    if (planning_hour !== undefined)           updates.planning_hour           = String(planning_hour);
    if (daily_post_count !== undefined)        updates.daily_post_count        = String(daily_post_count);
    if (clean_source_channels !== undefined)   updates.clean_source_channels   = String(clean_source_channels);
    if (direct_source_channels !== undefined)  updates.direct_source_channels  = String(direct_source_channels);
    if (source_channels !== undefined)         updates.source_channels         = String(source_channels);
    if (main_channel_name !== undefined)       updates.main_channel_name       = String(main_channel_name);
    if (main_channel_link !== undefined)       updates.main_channel_link       = String(main_channel_link);
    if (demo_duration !== undefined)           updates.demo_duration           = String(demo_duration);
    if (target_search_bot !== undefined)       updates.target_search_bot       = String(target_search_bot);
    if (night_start !== undefined)             updates.night_start             = String(night_start);
    if (night_end !== undefined)               updates.night_end               = String(night_end);
    updates.night_mode = (night_mode === 'true' || night_mode === true) ? 'true' : 'false';

    for (const [key, value] of Object.entries(updates)) {
      await pool.query(
        'INSERT INTO bot_settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
        [key, value]
      );
    }

    console.log('✅ Settings updated:', updates);
    res.json({ success: true, message: 'Settings updated successfully!' });
  } catch (err) {
    console.error('❌ Settings save error:', err);
    res.status(500).json({ error: 'Database error saving settings' });
  }
});

app.get('/api/stats', async (req, res) => {
  try {
    const countResult = await pool.query('SELECT COUNT(*) FROM posted_tracks');
    const recentResult = await pool.query(
      'SELECT artist, title, post_date FROM posted_tracks ORDER BY post_date DESC LIMIT 5'
    );

    res.json({
      total_posted: countResult.rows[0].count,
      recent_tracks: recentResult.rows
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database error fetching stats' });
  }
});

// Today's Schedule API
app.get('/api/schedule/today', async (req, res) => {
  try {
    // Toshkent vaqti bo'yicha bugungi kun boshlanishi va tugashi
    const result = await pool.query(`
      SELECT
        id,
        post_time AT TIME ZONE 'Asia/Tashkent' AS post_time_local,
        track_id,
        artist,
        title,
        chat_id,
        is_posted
      FROM daily_schedule
      WHERE
        (post_time AT TIME ZONE 'Asia/Tashkent')::date
          = (NOW() AT TIME ZONE 'Asia/Tashkent')::date
      ORDER BY post_time ASC
    `);
    res.json({ schedule: result.rows });
  } catch (err) {
    console.error('Schedule fetch error:', err);
    res.status(500).json({ error: 'Database error fetching schedule' });
  }
});

// Logs Real-time Streaming Logic
const logFilePath = path.resolve(__dirname, '../bot_logs.log');

function readLastLines(filePath, numLines) {
  if (!fs.existsSync(filePath)) return 'Logs file not created yet... Make sure bot is running.';
  try {
    const stat = fs.statSync(filePath);
    // Read at most last 64KB to avoid memory issues with huge logs
    const chunkSize = Math.min(stat.size, 64 * 1024);
    const fd = fs.openSync(filePath, 'r');
    const buffer = Buffer.alloc(chunkSize);
    fs.readSync(fd, buffer, 0, chunkSize, stat.size - chunkSize);
    fs.closeSync(fd);
    
    const lines = buffer.toString('utf8').split('\n');
    return lines.slice(-numLines).join('\n');
  } catch (e) {
    return 'Error reading logs file: ' + e.message;
  }
}

// Authenticate Socket.IO connections via handshake cookie
io.use((socket, next) => {
  const cookieHeader = socket.handshake.headers.cookie;
  if (!cookieHeader) {
    return next(new Error('Authentication error: No cookies found'));
  }
  const cookies = cookieHeader.split(';').reduce((acc, cookie) => {
    const parts = cookie.trim().split('=');
    const key = parts[0];
    const value = parts.slice(1).join('=');
    acc[key] = value;
    return acc;
  }, {});
  
  const token = cookies['auth_token'];
  if (token && activeSessions[token] && Date.now() < activeSessions[token]) {
    return next();
  }
  return next(new Error('Authentication error: Invalid or expired session token'));
});

io.on('connection', (socket) => {
  console.log('💻 Admin Client connected to logs socket');
  socket.emit('logs', readLastLines(logFilePath, 100));

  socket.on('disconnect', () => {
    console.log('💻 Admin Client disconnected');
  });
});

function startWatcher(filePath) {
  let fileSize = fs.existsSync(filePath) ? fs.statSync(filePath).size : 0;
  fs.watchFile(filePath, { interval: 1000 }, (curr) => {
    if (curr.size > fileSize) {
      const stream = fs.createReadStream(filePath, { start: fileSize, end: curr.size });
      stream.on('data', (chunk) => {
        io.emit('logs_chunk', chunk.toString());
      });
      fileSize = curr.size;
    } else if (curr.size < fileSize) {
      fileSize = curr.size;
    }
  });
}

if (fs.existsSync(logFilePath)) {
  startWatcher(logFilePath);
} else {
  const logDir = path.dirname(logFilePath);
  const dirWatcher = fs.watch(logDir, (eventType, filename) => {
    if (filename === 'bot_logs.log' && fs.existsSync(logFilePath)) {
      console.log('Log file created, starting watcher...');
      startWatcher(logFilePath);
      dirWatcher.close();
    }
  });
}

// Start Server
server.listen(PORT, '127.0.0.1', () => {
  console.log(`🚀 Node.js Admin Panel is running on http://localhost:${PORT}`);
});
