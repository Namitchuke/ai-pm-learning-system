const mongoose = require('mongoose');

const progressSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, unique: true },
    startDate: { type: String, default: '' },
    weekOffset: { type: Number, default: 0 },
    items: { type: mongoose.Schema.Types.Mixed, default: {} },
    artifacts: { type: mongoose.Schema.Types.Mixed, default: {} },
    quizAnswers: { type: mongoose.Schema.Types.Mixed, default: {} },
    skillLevels: { type: mongoose.Schema.Types.Mixed, default: {} },
    skillQuizAnswers: { type: mongoose.Schema.Types.Mixed, default: {} },
    weeklyMetrics: { type: mongoose.Schema.Types.Mixed, default: {} },
    overallMetrics: {
        type: mongoose.Schema.Types.Mixed,
        default: { cases: 0, apps: 0, mocks: 0 }
    },
    decisionLogs: { type: Array, default: [] },
    expanded: { type: mongoose.Schema.Types.Mixed, default: {} },
    casesCompleted: { type: mongoose.Schema.Types.Mixed, default: {} },
    casesState: { type: mongoose.Schema.Types.Mixed, default: { co: 'All', cat: 'All', lv: 'All' } },
    mockInterviewsState: { type: mongoose.Schema.Types.Mixed, default: { co: 'All', cat: 'All', lv: 'All', role: 'All' } },
    updatedAt: { type: Date, default: Date.now }
});

progressSchema.pre('save', function (next) {
    this.updatedAt = new Date();
    next();
});

module.exports = mongoose.model('Progress', progressSchema);
