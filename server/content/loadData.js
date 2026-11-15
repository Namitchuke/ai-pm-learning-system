/**
 * Reads the curriculum constants out of client/data.js (the single source of truth
 * shared with the browser). data.js uses top-level `const`, so it is evaluated in a
 * function scope with `var` and the needed names are returned.
 */
const fs = require('fs');
const path = require('path');

function loadDataFile() {
    const dataPath = path.join(__dirname, '../../client/data.js');
    const content = fs.readFileSync(dataPath, 'utf8').replace(/\bconst\b/g, 'var');
    const fn = new Function(content + `
        return {
            PHASES: typeof PHASES !== 'undefined' ? PHASES : [],
            SKILL_QUIZZES: typeof SKILL_QUIZZES !== 'undefined' ? SKILL_QUIZZES : {},
            MOCK_INTERVIEWS: typeof MOCK_INTERVIEWS !== 'undefined' ? MOCK_INTERVIEWS : [],
            MOCK_CASES: typeof MOCK_CASES !== 'undefined' ? MOCK_CASES : [],
            CORE_SKILLS: typeof CORE_SKILLS !== 'undefined' ? CORE_SKILLS : [],
            AI_SKILLS: typeof AI_SKILLS !== 'undefined' ? AI_SKILLS : []
        };
    `);
    return fn();
}

function loadAnswers() {
    return JSON.parse(fs.readFileSync(path.join(__dirname, 'answers.json'), 'utf8'));
}

module.exports = { loadDataFile, loadAnswers };
