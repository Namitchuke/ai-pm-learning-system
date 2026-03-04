const mongoose = require('mongoose');

const skillQuizSchema = new mongoose.Schema({
    skillId: { type: String, required: true, unique: true },
    skillName: { type: String, required: true },
    levels: { type: mongoose.Schema.Types.Mixed, default: {} }
    // levels: { "1": [{ q, options, answer }], "2": [...], ... }
});

module.exports = mongoose.model('SkillQuiz', skillQuizSchema);
