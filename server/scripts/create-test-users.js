/**
 * Create (or reset) test accounts.
 * Usage: node server/scripts/create-test-users.js [count=3]
 * Passwords are random and printed once. Re-running resets them.
 */
require('dotenv').config();
const crypto = require('crypto');
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const User = require('../models/User');
const Progress = require('../models/Progress');

(async () => {
    const count = Math.min(20, Math.max(1, parseInt(process.argv[2], 10) || 3));
    if (!process.env.MONGODB_URI) { console.error('MONGODB_URI is not set'); process.exit(1); }
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        for (let i = 1; i <= count; i++) {
            const email = `testuser${i}@example.com`;
            const password = crypto.randomBytes(9).toString('base64url');
            const passwordHash = await bcrypt.hash(password, 12);
            const user = await User.findOneAndUpdate(
                { email },
                { $set: { passwordHash, name: `Test User ${i}` }, $setOnInsert: { username: `testuser${i}`, role: 'learner', studyRole: 'AI PM' } },
                { new: true, upsert: true }
            );
            await Progress.updateOne({ userId: user._id }, { $setOnInsert: { userId: user._id } }, { upsert: true });
            console.log(`${email}  ${password}`);
        }
    } catch (err) {
        console.error(err.message);
        process.exitCode = 1;
    } finally {
        await mongoose.connection.close();
    }
})();
