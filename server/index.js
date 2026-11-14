require('dotenv').config();
const express = require('express');
const session = require('express-session');
const MongoStore = require('connect-mongo');
const cors = require('cors');
const crypto = require('crypto');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const path = require('path');
const { connectDB, dbState } = require('./config/db');
const passport = require('./config/passport');

const app = express();
const PORT = process.env.PORT || 5000;

// Trust Render's reverse proxy (needed for secure cookies)
if (process.env.NODE_ENV === 'production' || process.env.RENDER) {
    app.set('trust proxy', 1);
}

app.disable('x-powered-by');

// Security headers. The pages rely on inline scripts/handlers, so script-src keeps
// 'unsafe-inline'; everything else is locked to same-origin + Google Fonts.
app.use(helmet({
    contentSecurityPolicy: {
        useDefaults: false,
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            scriptSrcAttr: ["'unsafe-inline'"],
            styleSrc: ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
            fontSrc: ["'self'", 'https://fonts.gstatic.com', 'data:'],
            imgSrc: ["'self'", 'data:', 'https:'],
            connectSrc: ["'self'"],
            objectSrc: ["'none'"],
            baseUri: ["'self'"],
            formAction: ["'self'"],
            frameAncestors: ["'none'"]
        }
    },
    crossOriginEmbedderPolicy: false
}));

// Health/keep-alive endpoints. Registered FIRST so they never depend on the DB,
// sessions or auth. Used by Render's health check and the keep-alive cron.
app.get(['/api/ping', '/healthz'], (req, res) => {
    res.json({ status: 'ok', uptime: Math.round(process.uptime()), db: dbState() });
});

// Connect to MongoDB (retries in the background; never kills the process)
connectDB();

// Middleware
app.use(express.json({ limit: '1mb' }));

// Reject Mongo operator / prototype-pollution keys anywhere in a JSON body
// (blocks NoSQL injection such as {"email": {"$ne": null}}).
function hasBadKey(v, depth = 0) {
    if (!v || typeof v !== 'object') return false;
    if (depth > 12) return true;
    for (const k of Object.keys(v)) {
        if (k.startsWith('$') || k === '__proto__' || k === 'constructor' || k === 'prototype') return true;
        if (hasBadKey(v[k], depth + 1)) return true;
    }
    return false;
}
app.use((req, res, next) => {
    if (hasBadKey(req.body) || hasBadKey(req.query)) return res.status(400).json({ error: 'Invalid request' });
    next();
});

// Rate limits: tight on credential endpoints, generous on the rest of the API
const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, limit: 20, standardHeaders: true, legacyHeaders: false,
    message: { error: 'Too many attempts. Please try again in a few minutes.' }
});
const apiLimiter = rateLimit({
    windowMs: 60 * 1000, limit: 240, standardHeaders: true, legacyHeaders: false,
    message: { error: 'Too many requests. Slow down.' }
});
app.use(['/auth/login', '/auth/signup'], authLimiter);
app.use(['/api', '/auth', '/admin'], apiLimiter);

// CSRF defence in depth (cookies are already SameSite=Lax): state-changing
// requests must come from our own origin when the browser says where they came from.
app.use((req, res, next) => {
    if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
    const origin = req.get('origin');
    if (!origin) return next();
    try {
        if (new URL(origin).host === req.get('host')) return next();
    } catch (e) { /* fall through */ }
    if (process.env.NODE_ENV !== 'production' && origin === process.env.CLIENT_URL) return next();
    res.status(403).json({ error: 'Cross-site request blocked' });
});

app.use(cors({
    origin: process.env.NODE_ENV === 'production' ? false : process.env.CLIENT_URL,
    credentials: true
}));

// API calls need the DB; fail fast with 503 instead of hanging while Mongo (re)connects
app.use(['/api', '/auth', '/admin'], (req, res, next) => {
    if (dbState() === 'connected') return next();
    res.status(503).json({ error: 'Service starting up, please retry in a moment' });
});

// Sessions (stored in MongoDB)
// No hardcoded fallback: without SESSION_SECRET we use a random per-boot secret
// (sessions reset on restart, but cookies can never be forged with a known key).
const sessionSecret = process.env.SESSION_SECRET || crypto.randomBytes(48).toString('hex');
if (!process.env.SESSION_SECRET) {
    console.warn('SESSION_SECRET is not set; using a random per-boot secret. Set it so logins survive restarts.');
}
app.use(session({
    secret: sessionSecret,
    name: 'aipm.sid',
    resave: false,
    saveUninitialized: false,
    store: process.env.MONGODB_URI ? MongoStore.create({
        mongoUrl: process.env.MONGODB_URI,
        ttl: 14 * 24 * 60 * 60 // 14 days
    }) : undefined,
    cookie: {
        maxAge: 14 * 24 * 60 * 60 * 1000,
        httpOnly: true,
        secure: 'auto', // honours trust proxy / X-Forwarded-Proto
        sameSite: 'lax'
    }
}));

// Passport
app.use(passport.initialize());
app.use(passport.session());

// API Routes
app.use('/auth', require('./routes/auth'));
app.use('/api/progress', require('./routes/progress'));
app.use('/api/content', require('./routes/content'));
app.use('/admin', require('./routes/admin'));

// Serve static frontend files
app.use(express.static(path.join(__dirname, '../client'), { dotfiles: 'ignore', index: 'index.html' }));

// Catch-all: serve index.html for non-API routes (SPA fallback)
app.get('*', (req, res) => {
    // Don't catch API/auth routes — let them 404 naturally
    if (req.path.startsWith('/auth') || req.path.startsWith('/api') || req.path.startsWith('/admin')) {
        return res.status(404).json({ error: 'Not found' });
    }
    res.sendFile(path.join(__dirname, '../client/index.html'));
});

// Last-resort error handler: never leak stack traces to clients
app.use((err, req, res, next) => {
    if (res.headersSent) return next(err);
    const status = err.status || err.statusCode || 500;
    if (status >= 500) console.error('Unhandled error:', err);
    res.status(status).json({ error: status >= 500 ? 'Server error' : 'Invalid request' });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
});
