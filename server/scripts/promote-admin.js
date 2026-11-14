/**
 * Promote one specific user to admin.
 * Usage: node server/scripts/promote-admin.js user@example.com
 */
require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../models/User');

(async () => {
    const email = (process.argv[2] || '').trim().toLowerCase();
    if (!email) { console.error('Usage: node server/scripts/promote-admin.js <email>'); process.exit(1); }
    if (!process.env.MONGODB_URI) { console.error('MONGODB_URI is not set'); process.exit(1); }
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        const user = await User.findOneAndUpdate({ email }, { role: 'admin' }, { new: true });
        console.log(user ? `Promoted ${user.email} to admin.` : `No user with email ${email}.`);
    } catch (err) {
        console.error(err.message);
        process.exitCode = 1;
    } finally {
        await mongoose.connection.close();
    }
})();
