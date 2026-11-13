const mongoose = require('mongoose');
require('dotenv').config();

let connecting = false;

const dbState = () => (mongoose.connection.readyState === 1 ? 'connected' : 'disconnected');

// Connect with retry/backoff. Never exits the process: a DB blip (or Atlas
// waking up) must not take the whole web service down and fail Render's health check.
const connectDB = async (attempt = 1) => {
    if (connecting) return;
    if (!process.env.MONGODB_URI) {
        console.error('MONGODB_URI is not set; API routes will return 503 until it is.');
        return;
    }
    connecting = true;
    try {
        await mongoose.connect(process.env.MONGODB_URI, { serverSelectionTimeoutMS: 10000 });
        console.log('MongoDB connected');
    } catch (err) {
        const delay = Math.min(30000, 2000 * attempt);
        console.error(`MongoDB connection error (attempt ${attempt}): ${err.message}. Retrying in ${delay / 1000}s`);
        connecting = false;
        setTimeout(() => connectDB(attempt + 1), delay);
        return;
    }
    connecting = false;
};

mongoose.connection.on('disconnected', () => console.warn('MongoDB disconnected'));

module.exports = { connectDB, dbState };
