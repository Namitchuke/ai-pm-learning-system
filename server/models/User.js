const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
    googleId: { type: String, sparse: true, unique: true },
    username: { type: String, required: true, unique: true, trim: true, minlength: 3 },
    name: { type: String, required: true, trim: true },
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    passwordHash: { type: String }, // null for Google-only users
    role: { type: String, enum: ['learner', 'admin'], default: 'learner' },
    studyRole: { type: String, enum: ['AI PM', 'Data Analyst', 'SD'], default: 'AI PM' },
    avatar: { type: String, default: '' },
    lastLoginAt: { type: Date },
    createdAt: { type: Date, default: Date.now }
});

module.exports = mongoose.model('User', userSchema);
