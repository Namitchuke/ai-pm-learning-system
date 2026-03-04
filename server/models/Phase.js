const mongoose = require('mongoose');

const phaseSchema = new mongoose.Schema({
    phaseIndex: { type: Number, required: true, unique: true },
    name: { type: String, required: true },
    weeks: [{
        label: String,
        focus: String,
        items: [{
            text: String,
            detail: String,
            done_when: String
        }],
        quiz: [{
            q: String,
            options: [String],
            answer: Number
        }],
        resources: [{
            title: String,
            url: String
        }]
    }]
});

module.exports = mongoose.model('Phase', phaseSchema);
