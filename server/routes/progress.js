const express = require('express');
const router = express.Router();
const { isAuthenticated } = require('../middleware/auth');
const Progress = require('../models/Progress');

// Get user's progress
router.get('/', isAuthenticated, async (req, res) => {
    try {
        let progress = await Progress.findOne({ userId: req.user._id });
        if (!progress) {
            progress = await Progress.create({ userId: req.user._id });
        }
        res.json(progress);
    } catch (err) {
        console.error('Progress GET error:', err);
        res.status(500).json({ error: 'Failed to load progress' });
    }
});

// Save user's progress (full state replacement)
router.put('/', isAuthenticated, async (req, res) => {
    try {
        const allowedFields = [
            'startDate', 'weekOffset', 'items', 'artifacts', 'quizAnswers',
            'skillLevels', 'skillQuizAnswers', 'weeklyMetrics', 'overallMetrics',
            'decisionLogs', 'expanded', 'casesCompleted', 'mocksDone', 'casesState', 'mockInterviewsState'
        ];

        const isObj = v => v && typeof v === 'object' && !Array.isArray(v);
        const body = isObj(req.body) ? req.body : {};
        const update = {};
        for (const field of allowedFields) {
            const v = body[field];
            if (v === undefined || v === null) continue;
            // Type-check every field so a client can't store arbitrary shapes
            if (field === 'startDate') {
                if (typeof v !== 'string' || !/^(\d{4}-\d{2}-\d{2})?$/.test(v)) continue;
            } else if (field === 'weekOffset') {
                if (typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > 60) continue;
            } else if (field === 'decisionLogs') {
                if (!Array.isArray(v) || v.length > 500) continue;
                update[field] = v.filter(isObj).map(l => ({
                    cat: String(l.cat || '').slice(0, 40),
                    text: String(l.text || '').slice(0, 4000),
                    time: String(l.time || '').slice(0, 60)
                }));
                continue;
            } else if (!isObj(v)) {
                continue;
            }
            update[field] = v;
        }
        update.updatedAt = new Date();

        const progress = await Progress.findOneAndUpdate(
            { userId: req.user._id },
            { $set: update },
            { new: true, upsert: true }
        );

        res.json({ success: true });
    } catch (err) {
        console.error('Progress PUT error:', err);
        res.status(500).json({ error: 'Failed to save progress' });
    }
});

module.exports = router;
