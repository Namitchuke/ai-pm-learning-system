require('dotenv').config();
const mongoose = require('mongoose');
const User = require('./server/models/User');

const MONGO_URI = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/ai-pm-learning';

async function promote() {
    try {
        await mongoose.connect(MONGO_URI);
        const user = await User.findOne();
        if (user) {
            user.role = 'admin';
            await user.save();
            console.log(`Promoted user ${user.email || user.username} to admin.`);
        } else {
            console.log('No users found in database.');
        }
    } catch (err) {
        console.error(err);
    } finally {
        mongoose.connection.close();
    }
}
promote();
