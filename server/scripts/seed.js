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

const { loadDataFile } = require('../content/loadData');

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

        // Hints, model answers and weekly study guides (server/content/answers.json)
        const answers = JSON.parse(fs.readFileSync(path.join(__dirname, '../content/answers.json'), 'utf8'));
        const withAnswers = (item, src) => ({ ...item, ...(src || {}) });

        // Seed Phases (weeks get their study guide from answers.json)
        for (let i = 0; i < data.PHASES.length; i++) {
            const phase = data.PHASES[i];
            const weeks = phase.weeks.map((w, wi) => {
                const g = answers.weekGuides && answers.weekGuides[`${i}-${wi}`];
                return g ? { ...w, guide: g } : w;
            });
            await Phase.create({
                phaseIndex: i,
                name: phase.name,
                weeks
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
            const mockDocs = data.MOCK_INTERVIEWS.map(m => withAnswers(m, answers.mock[m.q]));
            const missingMock = mockDocs.filter(m => !m.solution).length;
            if (missingMock) console.warn(`   ⚠️  ${missingMock} mock interviews have no answer text yet`);
            await MockInterview.insertMany(mockDocs);
            console.log(`✅ Seeded ${data.MOCK_INTERVIEWS.length} mock interviews`);
        }

        // Seed Case Studies
        if (data.MOCK_CASES.length > 0) {
            const caseDocs = data.MOCK_CASES.map(c => withAnswers(c, answers.cases[c.title]));
            const missingCase = caseDocs.filter(c => !c.solution).length;
            if (missingCase) console.warn(`   ⚠️  ${missingCase} case studies have no answer text yet`);
            await CaseStudy.insertMany(caseDocs);
            console.log(`✅ Seeded ${data.MOCK_CASES.length} case studies`);
        }

        // Create admin user (you!)
        const existingAdmin = await User.findOne({ role: 'admin' });
        if (!existingAdmin) {
            const adminPassword = process.env.ADMIN_PASSWORD || require('crypto').randomBytes(9).toString('base64url');
            const passwordHash = await bcrypt.hash(adminPassword, 12);
            await User.create({
                username: 'admin',
                name: 'Admin',
                email: 'admin@aipm.app',
                passwordHash,
                role: 'admin',
                studyRole: 'AI PM'
            });
            console.log('✅ Created admin user (email: admin@aipm.app)');
            console.log(process.env.ADMIN_PASSWORD ? '   Password taken from ADMIN_PASSWORD.' : `   Generated password (shown once): ${adminPassword}`);
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
