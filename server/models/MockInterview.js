const mongoose = require('mongoose');

const mockInterviewSchema = new mongoose.Schema({
    co: { type: String, required: true },
    cat: { type: String, required: true },
    level: { type: String, enum: ['Easy', 'Medium', 'Hard'], required: true },
    role: { type: String, required: true },
    q: { type: String, required: true },
    flow: { type: String, required: true }
});

module.exports = mongoose.model('MockInterview', mockInterviewSchema);
