const express = require('express');
const router = express.Router();
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
        const users = await User.find().select('-passwordHash').sort({ createdAt: -1 });
        const progress = await Progress.find();

        const usersWithProgress = users.map(u => {
            const p = progress.find(pr => pr.userId.toString() === u._id.toString());
            const itemsDone = p ? Object.values(p.items || {}).filter(Boolean).length : 0;
            return {
                ...u.toObject(),
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
        const item = await Model.findByIdAndUpdate(req.params.id, req.body, { new: true });
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
            { skillId: req.params.skillId },
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
