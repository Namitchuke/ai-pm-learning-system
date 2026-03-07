const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const LocalStrategy = require('passport-local').Strategy;
const bcrypt = require('bcryptjs');
const User = require('../models/User');

passport.serializeUser((user, done) => {
    done(null, user.id);
});

passport.deserializeUser(async (id, done) => {
    try {
        const user = await User.findById(id);
        done(null, user);
    } catch (err) {
        done(err, null);
    }
});

// Google OAuth Strategy
passport.use(new GoogleStrategy({
    clientID: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    callbackURL: '/auth/google/callback',
    proxy: true
}, async (accessToken, refreshToken, profile, done) => {
    try {
        let user = await User.findOne({ googleId: profile.id });
        if (user) return done(null, user);

        // Check if email already exists (signed up with password first)
        user = await User.findOne({ email: profile.emails[0].value });
        if (user) {
            user.googleId = profile.id;
            if (!user.avatar && profile.photos && profile.photos[0]) {
                user.avatar = profile.photos[0].value;
            }
            user.lastLoginAt = new Date();
            await user.save();
            return done(null, user);
        }

        // Create new user from Google profile
        user = await User.create({
            googleId: profile.id,
            username: profile.emails[0].value.split('@')[0] + '_' + Date.now().toString(36),
            name: profile.displayName,
            email: profile.emails[0].value,
            avatar: profile.photos && profile.photos[0] ? profile.photos[0].value : '',
            role: 'learner',
            studyRole: 'AI PM'
        });
        done(null, user);
    } catch (err) {
        done(err, null);
    }
}));

// Local (Email/Password) Strategy
passport.use(new LocalStrategy({
    usernameField: 'email'
}, async (email, password, done) => {
    try {
        const user = await User.findOne({ email: email.toLowerCase() });
        if (!user) return done(null, false, { message: 'No account with that email' });
        if (!user.passwordHash) return done(null, false, { message: 'Please login with Google' });

        const isMatch = await bcrypt.compare(password, user.passwordHash);
        if (!isMatch) return done(null, false, { message: 'Incorrect password' });

        user.lastLoginAt = new Date();
        await user.save();
        done(null, user);
    } catch (err) {
        done(err);
    }
}));

module.exports = passport;
