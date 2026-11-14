const express = require('express');
const router = express.Router();
const passport = require('passport');
const bcrypt = require('bcryptjs');
const User = require('../models/User');
const Progress = require('../models/Progress');

const STUDY_ROLES = ['AI PM', 'Data Analyst', 'SD'];

// Signup (email/password)
router.post('/signup', async (req, res) => {
    try {
        let { username, name, email, password, studyRole } = req.body || {};

        if (![username, name, email, password].every(v => typeof v === 'string' && v.trim())) {
            return res.status(400).json({ error: 'All fields are required' });
        }
        username = username.trim();
        name = name.trim();
        email = email.trim().toLowerCase();
        if (!/^[A-Za-z0-9_.-]{3,30}$/.test(username)) {
            return res.status(400).json({ error: 'Username must be 3-30 characters: letters, numbers, _ . -' });
        }
        if (name.length > 80) return res.status(400).json({ error: 'Name is too long' });
        if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            return res.status(400).json({ error: 'Enter a valid email address' });
        }
        if (password.length < 8 || password.length > 128) {
            return res.status(400).json({ error: 'Password must be 8-128 characters' });
        }
        if (!STUDY_ROLES.includes(studyRole)) studyRole = 'AI PM';

        const existingEmail = await User.findOne({ email });
        if (existingEmail) return res.status(400).json({ error: 'Email already registered' });

        const existingUsername = await User.findOne({ username });
        if (existingUsername) return res.status(400).json({ error: 'Username already taken' });

        const passwordHash = await bcrypt.hash(password, 12);

        const user = await User.create({
            username,
            name,
            email,
            passwordHash,
            role: 'learner',
            studyRole
        });

        // Create empty progress for new user
        await Progress.create({ userId: user._id });

        // Auto-login after signup
        req.login(user, (err) => {
            if (err) return res.status(500).json({ error: 'Login failed after signup' });
            res.json({ user: { id: user._id, name: user.name, email: user.email, role: user.role, studyRole: user.studyRole, avatar: user.avatar } });
        });
    } catch (err) {
        console.error('Signup error:', err);
        res.status(500).json({ error: 'Server error' });
    }
});

// Login (email/password)
router.post('/login', (req, res, next) => {
    const { email, password } = req.body || {};
    if (typeof email !== 'string' || typeof password !== 'string' || !email || !password || password.length > 128) {
        return res.status(400).json({ error: 'Email and password are required' });
    }
    passport.authenticate('local', (err, user, info) => {
        if (err) return res.status(500).json({ error: 'Server error' });
        if (!user) return res.status(401).json({ error: info?.message || 'Invalid credentials' });

        req.login(user, (err) => {
            if (err) return res.status(500).json({ error: 'Login failed' });
            res.json({ user: { id: user._id, name: user.name, email: user.email, role: user.role, studyRole: user.studyRole, avatar: user.avatar } });
        });
    })(req, res, next);
});

// Google OAuth
router.get('/google', (req, res, next) => {
    if (!passport.googleEnabled) return res.redirect('/?error=google_not_configured');
    next();
}, passport.authenticate('google', {
    scope: ['profile', 'email']
}));

router.get('/google/callback',
    passport.authenticate('google', { failureRedirect: '/?error=google_auth_failed' }),
    async (req, res) => {
        // Ensure progress record exists for Google users too
        try {
            const existing = await Progress.findOne({ userId: req.user._id });
            if (!existing) {
                await Progress.create({ userId: req.user._id });
            }
        } catch (err) {
            console.error('Google callback progress error:', err.message);
        }

        if (req.user.role === 'admin') {
            res.redirect('/admin.html');
        } else {
            res.redirect('/dashboard.html');
        }
    }
);

// Logout
router.post('/logout', (req, res) => {
    req.logout((err) => {
        if (err) return res.status(500).json({ error: 'Logout failed' });
        // Destroy the server-side session and drop the cookie, not just the user
        req.session.destroy(() => {
            res.clearCookie('aipm.sid');
            res.json({ message: 'Logged out' });
        });
    });
});

// Get current user
router.get('/me', (req, res) => {
    if (!req.isAuthenticated()) return res.status(401).json({ error: 'Not authenticated' });
    const u = req.user;
    res.json({ user: { id: u._id, name: u.name, email: u.email, role: u.role, studyRole: u.studyRole, avatar: u.avatar, username: u.username, createdAt: u.createdAt } });
});

module.exports = router;
