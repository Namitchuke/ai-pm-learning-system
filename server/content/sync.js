/**
 * Runs once each time the server connects to MongoDB, so content changes in the repo
 * reach the live database without a manual `npm run seed`.
 *
 * Safe by design:
 * - Never touches users or progress.
 * - Fills hints/solutions only where they are empty, so edits made in the admin page survive.
 * - Week resources and study guides come from the repo (there is no editor for them).
 * - If a collection is empty (fresh database) it is populated from data.js.
 * Set CONTENT_SYNC=off to disable.
 */
const Phase = require('../models/Phase');
const SkillQuiz = require('../models/SkillQuiz');
const MockInterview = require('../models/MockInterview');
const CaseStudy = require('../models/CaseStudy');
const { loadDataFile, loadAnswers } = require('./loadData');

// Questions removed from data.js that may still exist in older databases
const REMOVED_MOCK_QUESTIONS = ['Design an Airbnb experience for digital nomads.'];

const isEmpty = { $in: [null, ''] };

async function fillEmpty(Model, keyField, key, ans) {
    let n = 0;
    for (const field of ['hint', 'solution']) {
        if (!ans[field]) continue;
        const r = await Model.updateOne(
            { [keyField]: key, $or: [{ [field]: isEmpty }, { [field]: { $exists: false } }] },
            { $set: { [field]: ans[field] } }
        );
        n += r.modifiedCount || 0;
    }
    return n;
}

async function syncContent() {
    if (process.env.CONTENT_SYNC === 'off') return;
    const started = Date.now();
    const data = loadDataFile();
    const answers = loadAnswers();
    const withAns = (item, src) => ({ ...item, ...(src || {}) });
    const summary = {};

    // Fresh database: create the curriculum
    if (await Phase.countDocuments() === 0) {
        for (let i = 0; i < data.PHASES.length; i++) {
            const p = data.PHASES[i];
            await Phase.create({
                phaseIndex: i, name: p.name,
                weeks: p.weeks.map((w, wi) => ({ ...w, guide: answers.weekGuides[`${i}-${wi}`] }))
            });
        }
        summary.phasesCreated = data.PHASES.length;
    }
    if (await SkillQuiz.countDocuments() === 0) {
        const skills = [...data.CORE_SKILLS, ...data.AI_SKILLS].filter(s => data.SKILL_QUIZZES[s.id]);
        await SkillQuiz.insertMany(skills.map(s => ({ skillId: s.id, skillName: s.name, levels: data.SKILL_QUIZZES[s.id] })));
        summary.quizzesCreated = skills.length;
    }
    if (await MockInterview.countDocuments() === 0) {
        await MockInterview.insertMany(data.MOCK_INTERVIEWS.map(m => withAns(m, answers.mock[m.q])));
        summary.mocksCreated = data.MOCK_INTERVIEWS.length;
    }
    if (await CaseStudy.countDocuments() === 0) {
        await CaseStudy.insertMany(data.MOCK_CASES.map(c => withAns(c, answers.cases[c.title])));
        summary.casesCreated = data.MOCK_CASES.length;
    }

    // Existing database: remove duplicates, fill missing answers
    summary.mocksRemoved = (await MockInterview.deleteMany({ q: { $in: REMOVED_MOCK_QUESTIONS } })).deletedCount;
    let filled = 0;
    for (const [q, a] of Object.entries(answers.mock)) filled += await fillEmpty(MockInterview, 'q', q, a);
    for (const [t, a] of Object.entries(answers.cases)) filled += await fillEmpty(CaseStudy, 'title', t, a);
    summary.answerFieldsFilled = filled;

    // Week resources (dead links fixed in data.js) and study guides
    let weeksUpdated = 0;
    for (let i = 0; i < data.PHASES.length; i++) {
        const doc = await Phase.findOne({ phaseIndex: i });
        if (!doc) continue;
        data.PHASES[i].weeks.forEach((w, wi) => {
            if (!doc.weeks[wi]) return;
            doc.weeks[wi].resources = w.resources || [];
            const g = answers.weekGuides[`${i}-${wi}`];
            if (g) doc.weeks[wi].guide = g;
            weeksUpdated++;
        });
        doc.markModified('weeks');
        await doc.save();
    }
    summary.weeksUpdated = weeksUpdated;

    console.log(`Content sync done in ${Date.now() - started}ms:`, JSON.stringify(summary));
}

module.exports = { syncContent };
