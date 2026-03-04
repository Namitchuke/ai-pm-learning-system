require('dotenv').config();
const express = require('express');
const session = require('express-session');
const MongoStore = require('connect-mongo');
const cors = require('cors');
const path = require('path');
const connectDB = require('./config/db');
const passport = require('./config/passport');

const app = express();
const PORT = process.env.PORT || 5000;

// Connect to MongoDB
connectDB();

// Middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

app.use(cors({
    origin: process.env.NODE_ENV === 'production' ? false : process.env.CLIENT_URL,
    credentials: true
}));

// Sessions (stored in MongoDB)
app.use(session({
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
    store: MongoStore.create({
        mongoUrl: process.env.MONGODB_URI,
        ttl: 14 * 24 * 60 * 60 // 14 days
    }),
    cookie: {
        maxAge: 14 * 24 * 60 * 60 * 1000,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: process.env.NODE_ENV === 'production' ? 'none' : 'lax'
    }
}));

// Passport
app.use(passport.initialize());
app.use(passport.session());

// API Routes
app.use('/auth', require('./routes/auth'));
app.use('/api/progress', require('./routes/progress'));
app.use('/api/content', require('./routes/content'));
app.use('/admin', require('./routes/admin'));

// Serve static frontend files in production
if (process.env.NODE_ENV === 'production') {
    app.use(express.static(path.join(__dirname, '../client/dist')));
    app.get('*', (req, res) => {
        res.sendFile(path.join(__dirname, '../client/dist/index.html'));
    });
} else {
    // In dev, serve from client/ directly for quick iteration
    app.use(express.static(path.join(__dirname, '../client')));
}

app.listen(PORT, () => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
});
