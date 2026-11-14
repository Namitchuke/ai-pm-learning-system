const express = require('express');
const router = express.Router();
const mongoose = require('mongoose');
const { isAdmin } = require('../middleware/auth');
const User = require('../models/User');
const Progress = require('../models/Progress');
const Phase = require('../models/Phase');
const SkillQuiz = require('../models/SkillQuiz');
const MockInterview = require('../models/MockInterview');
const CaseStudy = require('../models/CaseStudy');

// Get all users with progress summary
router.get('/users', isAdmin, async (req, res) => {
    try {
        const users = await User.find().select('-passwordHash -__v').sort({ createdAt: -1 }).lean();
        const progress = await Progress.find();

        const usersWithProgress = users.map(u => {
            const p = progress.find(pr => pr.userId.toString() === u._id.toString());
            const itemsDone = p ? Object.values(p.items || {}).filter(Boolean).length : 0;
            return {
                ...u,
                googleId: u.googleId ? true : undefined, // expose only whether Google is linked
                progress: {
                    itemsDone,
                    cases: p?.overallMetrics?.cases || 0,
                    mocks: p?.overallMetrics?.mocks || 0,
                    lastActive: p?.updatedAt || u.createdAt
                }
            };
        });

        res.json(usersWithProgress);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load users' });
    }
});

// Get admin dashboard stats
router.get('/stats', isAdmin, async (req, res) => {
    try {
        const users = await User.find();
        const progress = await Progress.find();

        const totalUsers = users.length;

        // Active this week (last 7 days)
        const ONE_WEEK = 7 * 24 * 60 * 60 * 1000;
        const now = new Date();
        const activeThisWeek = progress.filter(p => {
            return p.updatedAt && (now - new Date(p.updatedAt)) < ONE_WEEK;
        }).length;

        // Average items done
        let totalItemsDone = 0;
        let progressWithItems = 0;
        progress.forEach(p => {
            const items = Object.values(p.items || {}).filter(Boolean).length;
            if (items > 0) {
                totalItemsDone += items;
                progressWithItems++;
            }
        });
        const avgItemsDone = progressWithItems > 0 ? Math.round(totalItemsDone / progressWithItems) : 0;

        res.json({ totalUsers, activeThisWeek, avgItemsDone });
    } catch (err) {
        res.status(500).json({ error: 'Failed to fetch stats' });
    }
});

// Model map for generic CRUD
const models = {
    interviews: MockInterview,
    cases: CaseStudy
};

// Add content
router.post('/content/:type', isAdmin, async (req, res) => {
    try {
        const Model = models[req.params.type];
        if (!Model) return res.status(400).json({ error: 'Invalid content type' });
        const item = await Model.create(req.body);
        res.json(item);
    } catch (err) {
        res.status(500).json({ error: 'Failed to create content' });
    }
});

// Update content
router.put('/content/:type/:id', isAdmin, async (req, res) => {
    try {
        const Model = models[req.params.type];
        if (!Model) return res.status(400).json({ error: 'Invalid content type' });
        if (!mongoose.isValidObjectId(req.params.id)) return res.status(400).json({ error: 'Invalid id' });
        const item = await Model.findByIdAndUpdate(req.params.id, req.body, { new: true, runValidators: true });
        if (!item) return res.status(404).json({ error: 'Not found' });
        res.json(item);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update content' });
    }
});

// Delete content
router.delete('/content/:type/:id', isAdmin, async (req, res) => {
    try {
        const Model = models[req.params.type];
        if (!Model) return res.status(400).json({ error: 'Invalid content type' });
        if (!mongoose.isValidObjectId(req.params.id)) return res.status(400).json({ error: 'Invalid id' });
        await Model.findByIdAndDelete(req.params.id);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Failed to delete content' });
    }
});

// Update quiz (special handling since structure is different)
router.put('/quiz/:skillId', isAdmin, async (req, res) => {
    try {
        const quiz = await SkillQuiz.findOneAndUpdate(
            { skillId: String(req.params.skillId) },
            { levels: req.body.levels },
            { new: true }
        );
        if (!quiz) return res.status(404).json({ error: 'Quiz not found' });
        res.json(quiz);
    } catch (err) {
        res.status(500).json({ error: 'Failed to update quiz' });
    }
});

module.exports = router;
