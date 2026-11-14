const mongoose = require('mongoose');

const caseStudySchema = new mongoose.Schema({
    title: { type: String, required: true },
    desc: { type: String, required: true },
    co: { type: String, required: true },
    cat: { type: String, required: true },
    level: { type: String, enum: ['Easy', 'Medium', 'Hard'], required: true },
    hint: { type: String, default: '' },
    solution: { type: String, default: '' },
    videoUrl: { type: String, default: '' }
});

module.exports = mongoose.model('CaseStudy', caseStudySchema);
