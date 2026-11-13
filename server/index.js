require('dotenv').config();
const express = require('express');
const session = require('express-session');
const MongoStore = require('connect-mongo');
const cors = require('cors');
const path = require('path');
const { connectDB, dbState } = require('./config/db');
const passport = require('./config/passport');

const app = express();
const PORT = process.env.PORT || 5000;

// Trust Render's reverse proxy (needed for secure cookies)
if (process.env.NODE_ENV === 'production' || process.env.RENDER) {
    app.set('trust proxy', 1);
}

// Health/keep-alive endpoints. Registered FIRST so they never depend on the DB,
// sessions or auth. Used by Render's health check and the keep-alive cron.
app.get(['/api/ping', '/healthz'], (req, res) => {
    res.json({ status: 'ok', uptime: Math.round(process.uptime()), db: dbState() });
});

// Connect to MongoDB (retries in the background; never kills the process)
connectDB();

// Middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

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
if (!process.env.SESSION_SECRET) {
    console.warn('SESSION_SECRET is not set; using an insecure fallback. Set it in production.');
}
app.use(session({
    secret: process.env.SESSION_SECRET || 'dev-insecure-session-secret',
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
app.use(express.static(path.join(__dirname, '../client')));

// Catch-all: serve index.html for non-API routes (SPA fallback)
app.get('*', (req, res) => {
    // Don't catch API/auth routes — let them 404 naturally
    if (req.path.startsWith('/auth') || req.path.startsWith('/api') || req.path.startsWith('/admin')) {
        return res.status(404).json({ error: 'Not found' });
    }
    res.sendFile(path.join(__dirname, '../client/index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
});
