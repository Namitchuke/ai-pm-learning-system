const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const LocalStrategy = require('passport-local').Strategy;
const bcrypt = require('bcryptjs');
const User = require('../models/User');

const DUMMY_HASH = bcrypt.hashSync('not-a-real-password', 12);

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

// Google OAuth Strategy (only registered when credentials are configured, so a
// missing env var disables Google login instead of crashing the whole server)
const googleEnabled = !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);
if (!googleEnabled) console.warn('GOOGLE_CLIENT_ID/SECRET not set; Google login disabled.');
if (googleEnabled) passport.use(new GoogleStrategy({
    clientID: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    callbackURL: '/auth/google/callback',
    proxy: true
}, async (accessToken, refreshToken, profile, done) => {
    try {
        let user = await User.findOne({ googleId: profile.id });
        if (user) return done(null, user);

        const gEmail = profile.emails && profile.emails[0];
        if (!gEmail || !gEmail.value) return done(null, false);
        const verified = gEmail.verified !== false && (!profile._json || profile._json.email_verified !== false);

        // Check if email already exists (signed up with password first).
        // Only link accounts when Google confirms the email is verified.
        user = await User.findOne({ email: gEmail.value.toLowerCase() });
        if (user) {
            if (!verified) return done(null, false);
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
        // One generic message for every failure, and a hash comparison even when the
        // account is missing, so responses don't reveal which emails are registered.
        const INVALID = { message: 'Incorrect email or password' };
        const user = await User.findOne({ email: String(email).trim().toLowerCase() });
        const hash = (user && user.passwordHash) || DUMMY_HASH;
        const isMatch = await bcrypt.compare(String(password), hash);
        if (!user || !user.passwordHash || !isMatch) return done(null, false, INVALID);

        user.lastLoginAt = new Date();
        await user.save();
        done(null, user);
    } catch (err) {
        done(err);
    }
}));

passport.googleEnabled = googleEnabled;
module.exports = passport;
