const express = require('express');
const router = express.Router();
const { isAuthenticated } = require('../middleware/auth');
const Phase = require('../models/Phase');
const SkillQuiz = require('../models/SkillQuiz');
const MockInterview = require('../models/MockInterview');
const CaseStudy = require('../models/CaseStudy');

// Get all phases (24-week curriculum)
router.get('/phases', isAuthenticated, async (req, res) => {
    try {
        const phases = await Phase.find().sort({ phaseIndex: 1 });
        res.json(phases);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load phases' });
    }
});

// Get all skill quizzes
router.get('/quizzes', isAuthenticated, async (req, res) => {
    try {
        const quizzes = await SkillQuiz.find();
        // Convert to the same format the frontend expects: { skillId: { level: [questions] } }
        const map = {};
        quizzes.forEach(q => { map[q.skillId] = q.levels; });
        res.json(map);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load quizzes' });
    }
});

// Get all mock interviews
router.get('/interviews', isAuthenticated, async (req, res) => {
    try {
        const interviews = await MockInterview.find();
        res.json(interviews);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load interviews' });
    }
});

// Get all case studies
router.get('/cases', isAuthenticated, async (req, res) => {
    try {
        const cases = await CaseStudy.find();
        res.json(cases);
    } catch (err) {
        res.status(500).json({ error: 'Failed to load case studies' });
    }
});

module.exports = router;
