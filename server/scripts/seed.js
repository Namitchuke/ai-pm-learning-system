/**
 * Seed Script - Migrates existing data.js content into MongoDB
 * 
 * Usage: 
 *   1. Ensure MONGODB_URI is set in .env
 *   2. Run: node server/scripts/seed.js
 */
require('dotenv').config();
const mongoose = require('mongoose');
const fs = require('fs');
const path = require('path');
const bcrypt = require('bcryptjs');

const User = require('../models/User');
const Phase = require('../models/Phase');
const SkillQuiz = require('../models/SkillQuiz');
const MockInterview = require('../models/MockInterview');
const CaseStudy = require('../models/CaseStudy');

// We need to extract the JS constants from data.js
// data.js uses 'const' declarations, so we need to eval it in a controlled way
function loadDataFile() {
    const dataPath = path.join(__dirname, '../../client/data.js');
    let content = fs.readFileSync(dataPath, 'utf8');

    // Replace 'const' with 'var' so they become accessible after eval
    content = content.replace(/\bconst\b/g, 'var');

    // Create a sandbox to execute the data file
    const sandbox = {};
    const fn = new Function(content + `
        return {
            PHASES: typeof PHASES !== 'undefined' ? PHASES : [],
            SKILL_QUIZZES: typeof SKILL_QUIZZES !== 'undefined' ? SKILL_QUIZZES : {},
            MOCK_INTERVIEWS: typeof MOCK_INTERVIEWS !== 'undefined' ? MOCK_INTERVIEWS : [],
            MOCK_CASES: typeof MOCK_CASES !== 'undefined' ? MOCK_CASES : [],
            CORE_SKILLS: typeof CORE_SKILLS !== 'undefined' ? CORE_SKILLS : [],
            AI_SKILLS: typeof AI_SKILLS !== 'undefined' ? AI_SKILLS : [],
            SKILL_RESOURCES: typeof SKILL_RESOURCES !== 'undefined' ? SKILL_RESOURCES : {},
            WEEKLY_METRICS: typeof WEEKLY_METRICS !== 'undefined' ? WEEKLY_METRICS : [],
            INTERVIEW_BANK: typeof INTERVIEW_BANK !== 'undefined' ? INTERVIEW_BANK : [],
            ARTIFACTS: typeof ARTIFACTS !== 'undefined' ? ARTIFACTS : [],
            K: typeof K !== 'undefined' ? K : ''
        };
    `);

    return fn();
}

async function seed() {
    try {
        await mongoose.connect(process.env.MONGODB_URI);
        console.log('✅ Connected to MongoDB');

        const data = loadDataFile();
        console.log(`📦 Loaded data.js:`);
        console.log(`   PHASES: ${data.PHASES.length}`);
        console.log(`   SKILL_QUIZZES: ${Object.keys(data.SKILL_QUIZZES).length} skills`);
        console.log(`   MOCK_INTERVIEWS: ${data.MOCK_INTERVIEWS.length}`);
        console.log(`   MOCK_CASES: ${data.MOCK_CASES.length}`);

        // Clear existing content
        await Phase.deleteMany({});
        await SkillQuiz.deleteMany({});
        await MockInterview.deleteMany({});
        await CaseStudy.deleteMany({});
        console.log('🗑️  Cleared existing content');

        // Seed Phases
        for (let i = 0; i < data.PHASES.length; i++) {
            const phase = data.PHASES[i];
            await Phase.create({
                phaseIndex: i,
                name: phase.name,
                weeks: phase.weeks
            });
        }
        console.log(`✅ Seeded ${data.PHASES.length} phases`);

        // Seed Skill Quizzes
        const allSkills = [...(data.CORE_SKILLS || []), ...(data.AI_SKILLS || [])];
        for (const skill of allSkills) {
            const quizData = data.SKILL_QUIZZES[skill.id];
            if (quizData) {
                await SkillQuiz.create({
                    skillId: skill.id,
                    skillName: skill.name,
                    levels: quizData
                });
            }
        }
        console.log(`✅ Seeded ${allSkills.length} skill quizzes`);

        // Seed Mock Interviews
        if (data.MOCK_INTERVIEWS.length > 0) {
            await MockInterview.insertMany(data.MOCK_INTERVIEWS);
            console.log(`✅ Seeded ${data.MOCK_INTERVIEWS.length} mock interviews`);
        }

        // Seed Case Studies
        if (data.MOCK_CASES.length > 0) {
            await CaseStudy.insertMany(data.MOCK_CASES);
            console.log(`✅ Seeded ${data.MOCK_CASES.length} case studies`);
        }

        // Create admin user (you!)
        const existingAdmin = await User.findOne({ role: 'admin' });
        if (!existingAdmin) {
            const passwordHash = await bcrypt.hash('admin123', 12);
            await User.create({
                username: 'admin',
                name: 'Admin',
                email: 'admin@aipm.app',
                passwordHash,
                role: 'admin',
                studyRole: 'AI PM'
            });
            console.log('✅ Created admin user (email: admin@aipm.app, password: admin123)');
            console.log('   ⚠️  CHANGE THIS PASSWORD IMMEDIATELY IN PRODUCTION!');
        } else {
            console.log('ℹ️  Admin user already exists, skipping');
        }

        console.log('\n🎉 Seed completed successfully!');
        process.exit(0);
    } catch (err) {
        console.error('❌ Seed failed:', err);
        process.exit(1);
    }
}

seed();
