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
            'decisionLogs', 'expanded', 'casesCompleted', 'casesState', 'mockInterviewsState'
        ];

        const update = {};
        allowedFields.forEach(field => {
            if (req.body[field] !== undefined) {
                update[field] = req.body[field];
            }
        });
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
