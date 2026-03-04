const express = require('express');
const router = express.Router();
const passport = require('passport');
const bcrypt = require('bcryptjs');
const User = require('../models/User');
const Progress = require('../models/Progress');

// Signup (email/password)
router.post('/signup', async (req, res) => {
    try {
        const { username, name, email, password, studyRole } = req.body;

        if (!username || !name || !email || !password) {
            return res.status(400).json({ error: 'All fields are required' });
        }
        if (password.length < 6) {
            return res.status(400).json({ error: 'Password must be at least 6 characters' });
        }

        const existingEmail = await User.findOne({ email: email.toLowerCase() });
        if (existingEmail) return res.status(400).json({ error: 'Email already registered' });

        const existingUsername = await User.findOne({ username });
        if (existingUsername) return res.status(400).json({ error: 'Username already taken' });

        const passwordHash = await bcrypt.hash(password, 12);

        const user = await User.create({
            username,
            name,
            email: email.toLowerCase(),
            passwordHash,
            role: 'learner',
            studyRole: studyRole || 'AI PM'
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
router.get('/google', passport.authenticate('google', {
    scope: ['profile', 'email']
}));

router.get('/google/callback',
    passport.authenticate('google', { failureRedirect: '/?error=google_auth_failed' }),
    async (req, res) => {
        // Ensure progress record exists for Google users too
        const existing = await Progress.findOne({ userId: req.user._id });
        if (!existing) {
            await Progress.create({ userId: req.user._id });
        }
        res.redirect('/dashboard.html');
    }
);

// Logout
router.post('/logout', (req, res) => {
    req.logout((err) => {
        if (err) return res.status(500).json({ error: 'Logout failed' });
        res.json({ message: 'Logged out' });
    });
});

// Get current user
router.get('/me', (req, res) => {
    if (!req.isAuthenticated()) return res.status(401).json({ error: 'Not authenticated' });
    const u = req.user;
    res.json({ user: { id: u._id, name: u.name, email: u.email, role: u.role, studyRole: u.studyRole, avatar: u.avatar, username: u.username } });
});

module.exports = router;
