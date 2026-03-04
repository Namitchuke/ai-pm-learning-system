let S = load();
function load() { try { let r = localStorage.getItem(K); if (r) { let p = JSON.parse(r); if (!p.skillLevels) p.skillLevels = {}; if (!p.skillQuizAnswers) p.skillQuizAnswers = {}; if (!p.decisionLogs) p.decisionLogs = []; if (!p.weeklyMetrics) p.weeklyMetrics = {}; if (!p.overallMetrics) p.overallMetrics = { cases: 0, apps: 0, mocks: 0 }; if (!p.mocksDone) p.mocksDone = {}; if (!p.casesCompleted) p.casesCompleted = {}; return p } } catch (e) { } return getDefault() }
function save() { localStorage.setItem(K, JSON.stringify(S)) }
function ik(p, w, i) { return `p${p}w${w}i${i}` }
function getCurWeek() { if (!S.startDate) return -1; let d = Math.floor((new Date() - new Date(S.startDate)) / (7 * 864e5)); return Math.max(1, Math.min(24, d + 1 + (S.weekOffset || 0))) }
function getCurWeekKey() { let w = getCurWeek(); return w < 1 ? 'w1' : 'w' + w }
function getWM(key) { let wk = getCurWeekKey(); if (!S.weeklyMetrics[wk]) S.weeklyMetrics[wk] = {}; return S.weeklyMetrics[wk][key] || 0 }
function setWM(key, val) { let wk = getCurWeekKey(); if (!S.weeklyMetrics[wk]) S.weeklyMetrics[wk] = {}; S.weeklyMetrics[wk][key] = val; save() }
function switchTab(i) { document.querySelectorAll('.tab').forEach((t, j) => t.classList.toggle('active', j === i)); document.querySelectorAll('.tab-body').forEach((t, j) => t.classList.toggle('active', j === i)); render() }
function showModal(id) { document.getElementById(id).classList.add('show') }
function hideModal(id) { document.getElementById(id).classList.remove('show') }
let editingM = null;
function openMM(key) { editingM = key; let m = WEEKLY_METRICS.find(x => x.key === key); document.getElementById('mmT').textContent = 'Update ' + m.label; document.getElementById('mmD').textContent = 'Weekly target: ' + m.target; document.getElementById('mmI').value = getWM(key); showModal('metricMo'); setTimeout(() => document.getElementById('mmI').focus(), 100) }
function saveMM() { if (editingM) { setWM(editingM, Math.max(0, parseInt(document.getElementById('mmI').value) || 0)); render() } hideModal('metricMo'); editingM = null }
document.getElementById('mmI').addEventListener('keydown', e => { if (e.key === 'Enter') saveMM(); if (e.key === 'Escape') hideModal('metricMo') });
function confirmReset() { S = getDefault(); document.getElementById('startDate').value = ''; save(); hideModal('resetMo'); render() }
function exportData() { let b = new Blob([JSON.stringify(S, null, 2)], { type: 'application/json' }), u = URL.createObjectURL(b), a = document.createElement('a'); a.href = u; a.download = 'aipm-v2-' + new Date().toISOString().slice(0, 10) + '.json'; a.click(); URL.revokeObjectURL(u) }
function importData(e) { let f = e.target.files[0]; if (!f) return; let r = new FileReader(); r.onload = x => { try { let d = JSON.parse(x.target.result); if (d.items || d.artifacts) { S = Object.assign(getDefault(), d); if (S.startDate) document.getElementById('startDate').value = S.startDate; save(); render() } } catch (err) { alert('Invalid file') } }; r.readAsText(f); e.target.value = '' }
document.querySelectorAll('.modal').forEach(m => m.addEventListener('click', function (e) { if (e.target === this) hideModal(this.id) }));
document.getElementById('startDate').addEventListener('change', function () { S.startDate = this.value; save(); render() });
if (S.startDate) document.getElementById('startDate').value = S.startDate;
function calcWeekPct(pi, wi) { let t = 0, d = 0; PHASES[pi].weeks[wi].items.forEach((_, ii) => { t++; if (S.items[ik(pi, wi, ii)]) d++ }); return t ? Math.round(d / t * 100) : 0 }
function calcPhasePct(pi) { let t = 0, d = 0; PHASES[pi].weeks.forEach((wk, wi) => wk.items.forEach((_, ii) => { t++; if (S.items[ik(pi, wi, ii)]) d++ })); return t ? Math.round(d / t * 100) : 0 }
function calcOverallPct() { let t = 0, d = 0; PHASES.forEach((ph, pi) => ph.weeks.forEach((wk, wi) => wk.items.forEach((_, ii) => { t++; if (S.items[ik(pi, wi, ii)]) d++ }))); return t ? Math.round(d / t * 100) : 0 }
function getPhaseAndWeekIdx(globalWeek) { let pi = Math.floor((globalWeek - 1) / 4), wi = (globalWeek - 1) % 4; return { pi: Math.min(pi, 5), wi: Math.min(wi, 3) } }
// ---- RENDER ----
function render() { renderTab0(); renderTab1(); renderTab2(); renderTab3(); renderTab4(); }
// ++ UI ADJ FNs ++
function adjWeek(delta) { S.weekOffset = (S.weekOffset || 0) + delta; save(); render(); }
function adjWM(key, delta) { let v = getWM(key) + delta; if (v < 0) v = 0; setWM(key, v); render(); }
function adjOM(key, delta) { let v = (S.overallMetrics[key] || 0) + delta; if (v < 0) v = 0; S.overallMetrics[key] = v; save(); render(); }
// ---- TAB 0: TODAY'S FOCUS ----
function renderTab0() {
    let el = document.getElementById('tab0'), cw = getCurWeek(), { pi, wi } = getPhaseAndWeekIdx(cw < 1 ? 1 : cw);
    let dayOfWeek = 0;
    if (S.startDate) { let start = new Date(S.startDate), now = new Date(), diffDays = Math.floor((now - start) / (864e5)), weekDay = (diffDays % 7) + 1; dayOfWeek = Math.min(weekDay, 7) }
    let phase = PHASES[pi], week = phase ? phase.weeks[wi] : null;
    let h = `<div class="focus-header">
<div class="fh-card">
    <div style="display:flex;align-items:center;justify-content:center;gap:12px">
        ${cw > 0 ? `<button class="adj-btn" style="background:var(--bg3);border:1px solid var(--border);" onclick="adjWeek(-1)">-</button>` : ''}
        <div class="fh-big">${cw > 0 ? cw : '—'}</div>
        ${cw > 0 ? `<button class="adj-btn" style="background:var(--bg3);border:1px solid var(--border);" onclick="adjWeek(1)">+</button>` : ''}
    </div>
    <div class="fh-label">Week</div><div class="fh-sub">of 24 (Manual Adjust)</div>
</div>
<div class="fh-card"><div class="fh-big">${dayOfWeek || '—'}</div><div class="fh-label">Day</div><div class="fh-sub">of 7</div></div>
<div class="fh-card"><div class="fh-big" style="font-size:16px;padding-top:6px">${phase ? phase.name : '—'}</div><div class="fh-label">Current Phase</div><div class="fh-sub">Phase ${pi + 1}</div></div>
</div>`;
    // Weekly Metrics
    h += `<div class="wm-grid">${WEEKLY_METRICS.map(m => `
<div class="wm ${m.color}">
    <div class="wm-icon" onclick="openMM('${m.key}')">${m.icon}</div>
    <div class="wm-val" style="display:flex;align-items:center;justify-content:center;gap:12px;">
        <button class="adj-btn" onclick="event.stopPropagation();adjWM('${m.key}',-1)">-</button>
        <span onclick="openMM('${m.key}')">${getWM(m.key)}</span>
        <button class="adj-btn" onclick="event.stopPropagation();adjWM('${m.key}',1)">+</button>
    </div>
    <div class="wm-lbl" onclick="openMM('${m.key}')">${m.label}</div>
    <div class="wm-tgt">Target: ${m.target}/week</div>
</div>`).join('')}</div>`;
    // This week's checklist
    if (week) {
        let wp = calcWeekPct(pi, wi);
        h += `<div class="card"><div class="card-title">${week.label} — ${week.focus} <span style="margin-left:auto;font-size:12px;color:var(--accent2)">${wp}%</span></div>`;
        h += week.items.map((it, ii) => {
            let k = ik(pi, wi, ii), d = S.items[k] || false;
            return `<div class="ci ${d ? 'done' : ''}" onclick="toggleItem('${k}')"><div class="ck">${d ? '✓' : ''}</div><div class="ci-text">${it.text}</div></div>
<div class="det ${d ? '' : 'show'}" id="det-${k}"><strong>What this means:</strong> ${it.detail}<br><span class="dw">Done when: ${it.done_when}</span></div>`
        }).join('');
        h += `</div>`;
        // Quiz
        if (week.quiz) {
            let answered = 0, correct = 0;
            week.quiz.forEach((q, qi) => { let a = S.quizAnswers[`q${pi}${wi}${qi}`]; if (a !== undefined) { answered++; if (a === q.answer) correct++ } });
            let pct = answered ? Math.round(correct / answered * 100) : 0;
            h += `<div class="quiz-box"><h4>Knowledge Check — ${week.label}</h4>`;
            h += week.quiz.map((q, qi) => {
                let qk = `q${pi}${wi}${qi}`, ans = S.quizAnswers[qk];
                return `<div class="qq"><p>${qi + 1}. ${q.q}</p>${q.options.map((o, oi) => { let cls = 'qo'; if (ans !== undefined) { if (oi === q.answer) cls += ' correct'; else if (oi === ans) cls += ' wrong' } return `<span class="${cls}" onclick="answerQ('${qk}',${oi},${q.answer})">${o}</span>` }).join('')}</div>`
            }).join('');
            if (answered > 0) { let sc = pct >= 70 ? 'good' : pct >= 40 ? 'mid' : 'bad'; h += `<div class="qscore ${sc}">Score: ${correct}/${week.quiz.length} (${pct}%)</div>` }
            h += `</div>`;
            // Dynamic Resources mapping to wrong questions
            if (answered > 0 && pct < 100 && week.resources && week.resources.length > 0) {
                h += `<div class="res-box" style="border-left: 3px solid var(--amber);"><h4>Study Missing Concepts</h4>`;
                let showIndices = new Set();
                week.quiz.forEach((q, qi) => {
                    let a = S.quizAnswers[`q${pi}${wi}${qi}`];
                    if (a !== undefined && a !== q.answer) {
                        showIndices.add(qi % week.resources.length);
                    }
                });
                if (showIndices.size === 0) showIndices.add(0);
                let customRes = Array.from(showIndices).map(idx => week.resources[idx]);
                h += customRes.map(r => `<a href="${r.url}" target="_blank">${r.title}</a>`).join('');
                h += `</div>`;
            }
        }
        // Resources toggle
        if (week.resources) {
            h += `<details style="margin-top:10px"><summary style="font-size:12px;font-weight:600;color:var(--t3);cursor:pointer;padding:6px 0">📚 All Resources for ${week.label}</summary><div class="res-box" style="margin-top:4px"><h4>📚 Resources</h4>${week.resources.map(r => `<a href="${r.url}" target="_blank">${r.title}</a>`).join('')}</div></details>`
        }
    } else { h += `<div class="card"><div class="card-title">Set your start date to begin!</div></div>` }
    el.innerHTML = h
}
// ---- TAB 1: FULL OVERVIEW ----
function renderTab1() {
    let el = document.getElementById('tab1'), h = '';
    let op = calcOverallPct();
    // Overall bar
    h += `<div class="card"><div class="card-title">📊 Overall Roadmap Progress</div>
<div class="ov-bar"><div class="ov-pct">${op}%</div><div class="ov-track"><div class="ov-fill" style="width:${op}%"></div></div></div></div>`;
    // Skill Depth Tracker
    h += `<div class="card"><div class="card-title">🎯 Skill Depth Tracker</div>`;
    h += renderSkillSection('Core PM Skills', 'core', CORE_SKILLS);
    h += renderSkillSection('AI-Specific Skills', 'ai', AI_SKILLS);
    h += `</div>`;
    // Portfolio Board
    h += `<div class="card"><div class="card-title">📦 Portfolio Status Board</div>`;
    h += ARTIFACTS.map(a => { let d = S.artifacts[a.key] || false; return `<div class="pf-item ${d ? 'done' : ''}" onclick="toggleArt('${a.key}')"><div class="pf-dot"></div><div class="pf-label">${a.label}</div></div>` }).join('');
    h += `</div>`;
    // Interview Readiness
    let ir = calcReadiness();
    let irColor = ir >= 80 ? 'var(--green)' : ir >= 50 ? 'var(--amber)' : 'var(--red)';
    let irText = ir >= 80 ? 'Competitive' : ir >= 60 ? 'Ready' : ir >= 40 ? 'Getting There' : 'Not Ready Yet';
    h += `<div class="card"><div class="card-title">🎯 Interview Readiness Score</div>
<div class="ir-gauge"><div class="ir-score">${ir}%</div><div class="ir-label">${irText}</div></div>
<div class="ir-bar"><div class="ir-fill" style="width:${ir}%;background:${irColor}"></div></div>
<div class="ir-breakdown">
<div class="ir-item"><span>Roadmap Completion</span><span>${calcOverallPct()}%</span></div>
<div class="ir-item"><span>Skills Depth</span><span>${calcSkillScore()}%</span></div>
<div class="ir-item"><span>Portfolio</span><span>${Math.round(Object.values(S.artifacts).filter(Boolean).length / 6 * 100)}%</span></div>
<div class="ir-item"><span>Cases Solved</span><span>${S.overallMetrics.cases || 0}</span></div>
<div class="ir-item"><span>Mock Interviews</span><span>${S.overallMetrics.mocks || 0}</span></div>
</div></div>`;
    // Interview Prep Bank
    h += `<div class="card"><div class="card-title">🎤 Interview Prep Bank</div>`;
    INTERVIEW_BANK.forEach((ib, i) => {
        let open = !!S.expanded['ib_' + i];
        h += `<div class="pf-item" style="cursor:pointer;flex-direction:column;align-items:flex-start" onclick="toggleIb(${i})">
<div style="font-weight:600;font-size:14px;display:flex;align-items:center;line-height:1.4"><span class="dl-cat" style="background:var(--bg3);border:1px solid var(--border);margin-right:8px">${ib.cat}</span>${ib.q}</div>
${open ? `<div style="font-size:13px;color:var(--t3);margin-top:8px;padding-left:12px;border-left:3px solid var(--accent)"><strong>Hint/Structure:</strong> ${ib.hint}</div>` : ''}
</div>`;
    });
    h += `</div>`;
    // Decision Logs
    h += `<div class="card"><div class="card-title">📝 Decision Logs</div>
<div class="dl-input">
<select id="dlCat"><option>Technical</option><option>Strategy</option><option>Trade-off</option></select>
<textarea id="dlText" placeholder="Log a decision..."></textarea>
<button class="dl-btn" onclick="addLog()">Add</button>
</div>`;
    h += (S.decisionLogs || []).slice().reverse().map((l, i) => { let ri = S.decisionLogs.length - 1 - i; return `<div class="dl-entry"><span class="dl-cat ${l.cat}">${l.cat}</span><button class="dl-del" onclick="delLog(${ri})">×</button><div class="dl-text">${l.text}</div><div class="dl-time">${l.time}</div></div>` }).join('');
    h += `</div>`;
    el.innerHTML = h
}
function renderSkillSection(title, prefix, skills) {
    let h = `<div class="skill-section"><h3>${title}</h3>`;
    skills.forEach(sk => {
        let maxPassed = 0; for (let lv = 1; lv <= 5; lv++) { if (S.skillLevels[sk.id + '_' + lv]) maxPassed = lv }
        let pct = maxPassed / 5 * 100;
        let activeLevel = null;
        h += `<div class="sk"><div class="sk-top"><div class="sk-name">${sk.name}</div><div class="sk-levels">`;
        for (let lv = 1; lv <= 5; lv++) {
            let passed = S.skillLevels[sk.id + '_' + lv] || false;
            let cls = 'sk-lv'; if (passed) cls += ' passed';
            h += `<div class="${cls}" onclick="openSkillQuiz('${sk.id}',${lv})">${lv}</div>`
        }
        h += `</div></div><div class="sk-bar"><div class="sk-fill" style="width:${pct}%"></div></div>`;
        h += `<div class="sk-quiz" id="skq-${sk.id}"></div></div>`
    });
    h += `</div>`; return h
}
function calcSkillScore() {
    let total = (CORE_SKILLS.length + AI_SKILLS.length) * 5, earned = 0;
    [...CORE_SKILLS, ...AI_SKILLS].forEach(sk => { for (let lv = 1; lv <= 5; lv++) { if (S.skillLevels[sk.id + '_' + lv]) earned++ } });
    return total ? Math.round(earned / total * 100) : 0
}
function calcReadiness() {
    let skillScore = calcSkillScore();
    let portfolioScore = Math.round(Object.values(S.artifacts).filter(Boolean).length / 6 * 100);
    let caseScore = Math.min(100, Math.round((S.overallMetrics.cases || 0) / 30 * 100));
    let mockScore = Math.min(100, Math.round((S.overallMetrics.mocks || 0) / 5 * 100));
    let roadmapScore = calcOverallPct();
    return Math.round(roadmapScore * .30 + skillScore * .25 + portfolioScore * .15 + caseScore * .15 + mockScore * .15)
}
// ---- TAB 2: DASHBOARD ----
function renderTab2() {
    let el = document.getElementById('tab2'), cw = getCurWeek(), op = calcOverallPct(), h = '';
    // Overall bar
    h += `<div class="card"><div class="card-title">Overall Progress</div>
<div class="ov-bar"><div class="ov-pct">${op}%</div><div class="ov-track"><div class="ov-fill" style="width:${op}%"></div></div></div></div>`;
    // Achievements
    let achievements = [
        { id: 'first_case', icon: '&#9670;', label: 'First Case Done', desc: 'Complete 1 case study', check: () => Object.values(S.casesCompleted || {}).filter(Boolean).length >= 1 },
        { id: 'first_mock', icon: '&#9655;', label: 'Mock Interview Given', desc: 'Practice 1 mock interview', check: () => Object.values(S.mocksDone || {}).filter(Boolean).length >= 1 },
        { id: 'prd_written', icon: '&#9671;', label: 'PRD Written', desc: 'Complete the PRD artifact', check: () => !!(S.artifacts && S.artifacts.prd) },
        { id: 'phase1', icon: '&#9632;', label: 'Phase 1 Complete', desc: 'Finish all Phase 1 tasks', check: () => calcPhasePct(0) === 100 },
        { id: 'mock_pro', icon: '&#9733;', label: 'Mock Pro', desc: 'Practice 10+ mock interviews', check: () => Object.values(S.mocksDone || {}).filter(Boolean).length >= 10 },
        { id: 'case_master', icon: '&#9830;', label: 'Case Study Pro', desc: 'Complete 10+ case studies', check: () => Object.values(S.casesCompleted || {}).filter(Boolean).length >= 10 },
        { id: 'halfway', icon: '&#9650;', label: 'Halfway There', desc: 'Complete Phase 1-3 (Week 12)', check: () => calcPhasePct(0) === 100 && calcPhasePct(1) === 100 && calcPhasePct(2) === 100 },
        { id: 'interview_ready', icon: '&#9733;', label: 'Interview Ready', desc: 'Practice 20+ mocks', check: () => Object.values(S.mocksDone || {}).filter(Boolean).length >= 20 }
    ];
    h += `<div class="card"><div class="card-title">Achievements</div>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px">`;
    achievements.forEach(a => {
        let unlocked = false;
        try { unlocked = a.check(); } catch (e) { }
        h += `<div style="text-align:center;padding:12px 8px;border-radius:8px;border:1px solid ${unlocked ? 'var(--accent)' : 'var(--border)'};background:${unlocked ? 'rgba(52,211,153,.08)' : 'var(--bg2)'};opacity:${unlocked ? '1' : '.5'};transition:all .2s">
            <div style="font-size:20px;margin-bottom:4px;${unlocked ? '' : 'filter:grayscale(1)'}">${a.icon}</div>
            <div style="font-size:11px;font-weight:600;color:${unlocked ? 'var(--t1)' : 'var(--t3)'}">${a.label}</div>
            <div style="font-size:9px;color:var(--t4);margin-top:2px">${a.desc}</div>
        </div>`;
    });
    h += `</div></div>`;
    // 24-week grid
    h += `<div class="card"><div class="card-title">Weekly Completion Grid</div><div class="wk-grid">`;
    for (let gw = 1; gw <= 24; gw++) {
        let { pi: p, wi: w } = getPhaseAndWeekIdx(gw);
        let wp = calcWeekPct(p, w);
        let cls = 'wk-cell'; if (wp === 100) cls += ' done'; else if (wp > 0) cls += ' partial'; else cls += ' empty'; if (gw === cw) cls += ' cur';
        h += `<div class="${cls}">W${gw}<span>${wp}%</span></div>`
    }
    h += `</div></div>`;
    // Phase cards
    h += `<div class="card"><div class="card-title">Phases</div>`;
    PHASES.forEach((ph, pi) => {
        let exp = S.expanded[pi] || false, pct = calcPhasePct(pi), ps = pi * 4 + 1, pe = ps + 3;
        let isCur = cw >= ps && cw <= pe;
        h += `<div class="ph-card ${exp ? 'exp' : ''} ${isCur ? 'current' : ''}">
<div class="ph-hdr" onclick="togglePh(${pi})"><div class="ph-num">${pi + 1}</div><div class="ph-info"><div class="ph-name">${ph.name}</div><div class="ph-weeks">Weeks ${ps}–${pe}</div></div><div class="ph-bar"><div class="ph-fill" style="width:${pct}%"></div></div><div class="ph-pct">${pct}%</div><div class="ph-chevron">▶</div></div>
<div class="ph-body"><div class="ph-inner">${ph.weeks.map((wk, wi) => {
            let gw = pi * 4 + wi + 1, wp = calcWeekPct(pi, wi);
            return `<div class="wk-row"><div class="wk-lbl">${wk.label}</div><div class="wk-focus">${wk.focus}</div><div class="wk-mini"><div class="wk-mini-fill" style="width:${wp}%"></div></div><div class="wk-pct">${wp}%</div></div>`
        }).join('')}</div></div></div>`
    });
    h += `</div>`;
    // Summary metrics
    h += `<div class="card"><div class="card-title">Lifetime Metrics</div>
<div class="sm-grid">
<div class="sm" onclick="editOverall('cases')" style="cursor:pointer"><div class="sm-val" style="display:flex;align-items:center;justify-content:center;gap:12px;"><button class="adj-btn" onclick="event.stopPropagation();adjOM('cases',-1)">-</button><span onclick="editOverall('cases')">${S.overallMetrics.cases || 0}</span><button class="adj-btn" onclick="event.stopPropagation();adjOM('cases',1)">+</button></div><div class="sm-lbl">Total Cases</div></div>
<div class="sm" onclick="editOverall('apps')" style="cursor:pointer"><div class="sm-val" style="display:flex;align-items:center;justify-content:center;gap:12px;"><button class="adj-btn" onclick="event.stopPropagation();adjOM('apps',-1)">-</button><span onclick="editOverall('apps')">${S.overallMetrics.apps || 0}</span><button class="adj-btn" onclick="event.stopPropagation();adjOM('apps',1)">+</button></div><div class="sm-lbl">Applications</div></div>
<div class="sm" onclick="editOverall('mocks')" style="cursor:pointer"><div class="sm-val" style="display:flex;align-items:center;justify-content:center;gap:12px;"><button class="adj-btn" onclick="event.stopPropagation();adjOM('mocks',-1)">-</button><span onclick="editOverall('mocks')">${S.overallMetrics.mocks || 0}</span><button class="adj-btn" onclick="event.stopPropagation();adjOM('mocks',1)">+</button></div><div class="sm-lbl">Mock Interviews</div></div>
<div class="sm"><div class="sm-val">${calcOverallQuizPct()}%</div><div class="sm-lbl">Quiz Average</div></div>
</div></div>`;
    el.innerHTML = h
}
// ---- TAB 3: MOCK INTERVIEWS ----
function renderTab3() {
    let el = document.getElementById('tab3'), h = '';
    if (!S.mockInterviewsState) S.mockInterviewsState = { co: 'All', cat: 'All', lv: 'All', role: 'All', status: 'All' };
    let st = S.mockInterviewsState;
    if (!st.status) st.status = 'All';
    if (!S.mocksDone) S.mocksDone = {};

    let companies = ['All', ...[...new Set(MOCK_INTERVIEWS.map(m => m.co))].sort()];
    let categories = ['All', ...[...new Set(MOCK_INTERVIEWS.map(m => m.cat))].sort()];
    let levels = ['All', 'Easy', 'Medium', 'Hard'];
    let roles = ['All', ...[...new Set(MOCK_INTERVIEWS.map(m => m.role))].sort()];
    let selS = 'background:var(--bg3);color:var(--t1);border:1px solid var(--border);padding:5px 10px;border-radius:6px;font-size:11px;outline:none;cursor:pointer;font-family:inherit';

    let doneCount = Object.values(S.mocksDone).filter(Boolean).length;
    h += `<div class="card"><div class="card-title">Mock Interviews <span style="margin-left:auto;font-size:11px;color:var(--accent2);font-weight:500">${doneCount} practiced</span></div>
            <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">
                <select style="${selS}" onchange="updMockFlt('co', this.value)"><option disabled>Company</option>${companies.map(c => `<option ${st.co === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS}" onchange="updMockFlt('cat', this.value)"><option disabled>Category</option>${categories.map(c => `<option ${st.cat === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS}" onchange="updMockFlt('lv', this.value)"><option disabled>Difficulty</option>${levels.map(c => `<option ${st.lv === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS}" onchange="updMockFlt('role', this.value)"><option disabled>Role</option>${roles.map(c => `<option ${st.role === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS};border-color:var(--accent)" onchange="updMockFlt('status', this.value)"><option ${st.status === 'All' ? 'selected' : ''}>All</option><option ${st.status === 'Done' ? 'selected' : ''}>Done</option><option ${st.status === 'Not Done' ? 'selected' : ''}>Not Done</option></select>
            </div>`;

    let filtered = MOCK_INTERVIEWS.filter(m => (st.co === 'All' || m.co === st.co) && (st.cat === 'All' || m.cat === st.cat) && (st.lv === 'All' || m.level === st.lv) && (st.role === 'All' || m.role === st.role));
    // status filter
    let mockKey = m => 'mock_' + m.q.substring(0, 40).replace(/[^a-zA-Z0-9]/g, '_');
    if (st.status === 'Done') filtered = filtered.filter(m => S.mocksDone[mockKey(m)]);
    if (st.status === 'Not Done') filtered = filtered.filter(m => !S.mocksDone[mockKey(m)]);

    h += `<div style="font-size:11px;color:var(--t3);margin-bottom:10px;font-weight:600">Showing ${filtered.length} questions</div>`;

    let accentColors = ['var(--accent)', 'var(--cyan)', 'var(--green)', 'var(--amber)', 'var(--pink)'];
    filtered.forEach((m, i) => {
        let mId = 'mki_' + i + '_' + m.co.substring(0, 2);
        let mk = mockKey(m);
        let isDone = !!S.mocksDone[mk];
        let open = !!S.expanded[mId];
        let lvColor = m.level === 'Easy' ? 'var(--green)' : m.level === 'Medium' ? 'var(--amber)' : 'var(--red)';
        let leftColor = accentColors[i % accentColors.length];
        h += `<div style="background:var(--bg2);border:1px solid ${isDone ? 'var(--green)' : 'var(--border)'};border-left:3px solid ${isDone ? 'var(--green)' : leftColor};border-radius:8px;padding:12px 14px;margin-bottom:8px;transition:all .2s;${isDone ? 'opacity:.7;' : ''}">
                <div style="display:flex;align-items:flex-start;gap:10px">
                    <input type="checkbox" ${isDone ? 'checked' : ''} onclick="event.stopPropagation();toggleMockDone('${mk}')" style="cursor:pointer;width:16px;height:16px;accent-color:var(--accent);margin-top:2px;flex-shrink:0">
                    <div style="flex:1;cursor:pointer" onclick="toggleMki('${mId}')">
                        <div style="display:flex;gap:5px;margin-bottom:6px;flex-wrap:wrap;font-size:10px;font-weight:700">
                            <span style="background:${lvColor};color:#fff;padding:1px 7px;border-radius:10px">${m.level}</span>
                            <span style="background:var(--bg3);border:1px solid var(--border);color:var(--t1);padding:1px 7px;border-radius:10px">${m.co}</span>
                            <span style="background:var(--bg3);border:1px solid var(--border);color:var(--t1);padding:1px 7px;border-radius:10px">${m.role}</span>
                            <span style="background:var(--accent);color:#fff;padding:1px 7px;border-radius:10px">${m.cat}</span>
                        </div>
                        <div style="font-weight:600;font-size:13px;line-height:1.4;${isDone ? 'text-decoration:line-through;color:var(--t3)' : ''}">${m.q}</div>
                        ${open ? `<div style="font-size:12px;color:var(--t2);margin-top:8px;padding:8px 12px;border-left:3px solid var(--accent);background:rgba(31,41,55,0.5);border-radius:4px"><strong>Hints:</strong><br>${m.flow}</div>` : ''}
                    </div>
                </div>
                </div>`;
    });
    h += `</div>`;
    el.innerHTML = h;
}


function renderTab4() {
    let el = document.getElementById('tab4'), h = '';

    if (!S.casesState) S.casesState = { co: 'All', cat: 'All', lv: 'All', status: 'All' };
    let st = S.casesState;
    if (!st.status) st.status = 'All';
    if (!S.casesCompleted) S.casesCompleted = {};

    let companies = ['All', ...[...new Set(MOCK_CASES.map(c => c.co))].sort()];
    let categories = ['All', ...[...new Set(MOCK_CASES.map(c => c.cat))].sort()];
    let levels = ['All', 'Easy', 'Medium', 'Hard'];
    let selS = 'background:var(--bg3);color:var(--t1);border:1px solid var(--border);padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-family:inherit';

    let doneCount = Object.values(S.casesCompleted).filter(Boolean).length;
    h += `<div class="card"><div class="card-title">Case Studies <span style="margin-left:auto;font-size:11px;color:var(--accent2);font-weight:500">${doneCount} completed</span></div>
            <div style="font-size:12px;color:var(--t2);margin-bottom:10px;">Practice on a whiteboard or Google Doc. Treat them as real take-home assignments.</div>
            <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">
                <select style="${selS}" onchange="S.casesState.co=this.value;save();renderTab4()">${companies.map(c => `<option ${st.co === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS}" onchange="S.casesState.cat=this.value;save();renderTab4()">${categories.map(c => `<option ${st.cat === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS}" onchange="S.casesState.lv=this.value;save();renderTab4()">${levels.map(c => `<option ${st.lv === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
                <select style="${selS};border-color:var(--accent)" onchange="S.casesState.status=this.value;save();renderTab4()"><option ${st.status === 'All' ? 'selected' : ''}>All</option><option ${st.status === 'Done' ? 'selected' : ''}>Done</option><option ${st.status === 'Not Done' ? 'selected' : ''}>Not Done</option></select>
            </div>`;

    let filtered = MOCK_CASES.filter(c => (st.co === 'All' || c.co === st.co) && (st.cat === 'All' || c.cat === st.cat) && (st.lv === 'All' || c.level === st.lv));
    // status filter
    if (st.status === 'Done') filtered = filtered.filter(c => S.casesCompleted['case_' + c.title]);
    if (st.status === 'Not Done') filtered = filtered.filter(c => !S.casesCompleted['case_' + c.title]);

    h += `<div style="font-size:11px;color:var(--t3);margin-bottom:10px;font-weight:600">Showing ${filtered.length} cases</div>`;
    h += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">`;
    filtered.forEach((c, i) => {
        let lvColor = c.level === 'Easy' ? 'var(--green)' : c.level === 'Medium' ? 'var(--amber)' : 'var(--red)';
        let isDone = S.casesCompleted && S.casesCompleted['case_' + c.title];

        h += `
                <div style="background:var(--bg2);border:1px solid ${isDone ? 'var(--green)' : 'var(--border)'};border-radius:8px;padding:14px;display:flex;flex-direction:column;position:relative;transition:all .2s;${isDone ? 'opacity:.7;' : ''}">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
                        <div style="display:flex;gap:5px;flex-wrap:wrap;font-size:10px;font-weight:700">
                            <span style="background:${lvColor};color:#fff;padding:1px 7px;border-radius:10px">${c.level}</span>
                            <span style="background:var(--bg3);border:1px solid var(--border);padding:1px 7px;border-radius:10px">${c.cat}</span>
                            <span style="background:var(--blue);color:#fff;padding:1px 7px;border-radius:10px">${c.co}</span>
                        </div>
                        <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleCaseDone('${c.title.replace(/'/g, "\\'")}')" style="cursor:pointer;width:16px;height:16px;accent-color:var(--accent)">
                    </div>
                    <div style="font-weight:700;font-size:13px;color:${isDone ? 'var(--t3)' : 'var(--t1)'};margin-bottom:6px;line-height:1.4;${isDone ? 'text-decoration:line-through;' : ''}">${c.title}</div>
                    <div style="font-size:12px;color:var(--t2);line-height:1.5;flex-grow:1">${c.desc}</div>
                </div>`;
    });
    h += `</div></div>`;

    h += `<div class="card" style="margin-top:16px"><div class="card-title">🔗 External Case Study Libraries</div>
            <div style="display:flex;flex-direction:column;gap:8px">
                <a href="https://growth.design/case-studies" target="_blank" style="color:var(--accent);font-weight:600;text-decoration:none;font-size:12px">1. Growth.Design (Interactive UX/Psychology Cases) ↗</a>
                <a href="https://www.theproductfolks.com/teardowns" target="_blank" style="color:var(--accent);font-weight:600;text-decoration:none;font-size:12px">2. The Product Folks - Indian Startup Teardowns ↗</a>
                <a href="https://www.tryexponent.com/questions" target="_blank" style="color:var(--accent);font-weight:600;text-decoration:none;font-size:12px">3. Exponent PM Interview Database ↗</a>
            </div></div>`;

    el.innerHTML = h;
}

function toggleCaseDone(tit) {
    if (!S.casesCompleted) S.casesCompleted = {};
    S.casesCompleted['case_' + tit] = !S.casesCompleted['case_' + tit];

    // Also auto-increment lifetime cases metrics if checked!
    if (S.casesCompleted['case_' + tit]) {
        S.overallMetrics.cases = (S.overallMetrics.cases || 0) + 1;
    } else {
        S.overallMetrics.cases = Math.max(0, (S.overallMetrics.cases || 0) - 1);
    }
    save();
    render();
}

function calcOverallQuizPct() { let t = 0, c = 0; PHASES.forEach((ph, pi) => ph.weeks.forEach((wk, wi) => { if (wk.quiz) wk.quiz.forEach((q, qi) => { t++; if (S.quizAnswers[`q${pi}${wi}${qi}`] === q.answer) c++ }) })); return t ? Math.round(c / t * 100) : 0 }
// ---- INTERACTIONS ----
function updMockFlt(k, v) { if (!S.mockInterviewsState) S.mockInterviewsState = { co: 'All', cat: 'All', lv: 'All', role: 'All', status: 'All' }; S.mockInterviewsState[k] = v; save(); renderTab3(); }
function toggleMki(mId) { S.expanded[mId] = !S.expanded[mId]; save(); renderTab3(); }
function toggleMockDone(mk) { if (!S.mocksDone) S.mocksDone = {}; S.mocksDone[mk] = !S.mocksDone[mk]; if (S.mocksDone[mk]) { S.overallMetrics.mocks = (S.overallMetrics.mocks || 0) + 1; } else { S.overallMetrics.mocks = Math.max(0, (S.overallMetrics.mocks || 0) - 1); } save(); renderTab3(); }

function toggleItem(k) { S.items[k] = !S.items[k]; save(); render() }
function toggleArt(k) { S.artifacts[k] = !S.artifacts[k]; save(); render() }
function togglePh(pi) { S.expanded[pi] = !S.expanded[pi]; save(); renderTab2() }
function toggleIb(i) { S.expanded['ib_' + i] = !S.expanded['ib_' + i]; save(); renderTab1() }
function answerQ(qk, sel, correct) { S.quizAnswers[qk] = sel; save(); render() }
function addLog() { let t = document.getElementById('dlText').value.trim(), c = document.getElementById('dlCat').value; if (!t) return; S.decisionLogs.push({ cat: c, text: t, time: new Date().toLocaleString() }); save(); render() }
function delLog(i) { S.decisionLogs.splice(i, 1); save(); render() }
function editOverall(key) {
    let labels = { cases: 'Total Cases Solved', apps: 'Total Applications Sent', mocks: 'Total Mock Interviews' };
    editingM = 'overall_' + key;
    document.getElementById('mmT').textContent = 'Update ' + labels[key];
    document.getElementById('mmD').textContent = 'Lifetime total';
    document.getElementById('mmI').value = S.overallMetrics[key] || 0;
    showModal('metricMo'); setTimeout(() => document.getElementById('mmI').focus(), 100)
}
let origSaveMM = saveMM;
saveMM = function () {
    if (editingM && editingM.startsWith('overall_')) {
        let key = editingM.split('_')[1];
        S.overallMetrics[key] = Math.max(0, parseInt(document.getElementById('mmI').value) || 0);
        save(); render(); hideModal('metricMo'); editingM = null; return
    }
    if (editingM) { setWM(editingM, Math.max(0, parseInt(document.getElementById('mmI').value) || 0)); render() }
    hideModal('metricMo'); editingM = null
};
// Skill quiz
function openSkillQuiz(skillId, level) {
    let el = document.getElementById('skq-' + skillId);
    if (!el) return;
    let quizData = SKILL_QUIZZES[skillId] && SKILL_QUIZZES[skillId][level];
    if (!quizData) { el.innerHTML = '<p style="font-size:12px;color:var(--t3);padding:8px">Quiz coming soon for this level.</p>'; el.classList.add('show'); return }
    let h = `<h4 style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:8px">Level ${level} Quiz</h4>`;
    let answered = 0, correct = 0;
    quizData.forEach((q, qi) => {
        let qk = `sk_${skillId}_${level}_${qi}`, ans = S.skillQuizAnswers[qk];
        if (ans !== undefined) { answered++; if (ans === q.answer) correct++ }
        h += `<div class="qq"><p>${qi + 1}. ${q.q}</p>${q.options.map((o, oi) => { let cls = 'qo'; if (ans !== undefined) { if (oi === q.answer) cls += ' correct'; else if (oi === ans) cls += ' wrong' } return `<span class="${cls}" onclick="answerSkillQ('${skillId}',${level},'${qk}',${oi},${q.answer})">${o}</span>` }).join('')}</div>`
    });
    if (answered === quizData.length) {
        let pct = Math.round(correct / quizData.length * 100), cls = pct >= 70 ? 'good' : pct >= 40 ? 'mid' : 'bad';
        h += `<div class="qscore ${cls}">Score: ${correct}/${quizData.length} (${pct}%) — ${pct >= 70 ? 'Level ' + level + ' Passed! ✅' : 'Try again after studying 📚'}</div>`;
        if (pct >= 70) { S.skillLevels[skillId + '_' + level] = true; save() } else {
            S.skillLevels[skillId + '_' + level] = false; save()
            // Show resources for this skill
            let allSkills = [...CORE_SKILLS, ...AI_SKILLS]; let sk = allSkills.find(s => s.id === skillId);
            if (SKILL_RESOURCES[skillId]) {
                h += `<div class="res-box" style="margin-top:8px"><h4>📚 Study These</h4>${SKILL_RESOURCES[skillId].map(r => `<a href="${r.url}" target="_blank">${r.title}</a>`).join('')}</div>`
            }
        }
    }
    h += `<button style="margin-top:8px;padding:4px 12px;font-size:11px;background:var(--bg3);border:1px solid var(--border);color:var(--t3);border-radius:6px;cursor:pointer;font-family:inherit" onclick="resetSkillQuiz('${skillId}',${level})">↻ Retry</button>`;
    el.innerHTML = h; el.classList.add('show')
}
function answerSkillQ(skillId, level, qk, sel, correct) {
    S.skillQuizAnswers[qk] = sel; save(); openSkillQuiz(skillId, level)
}
function resetSkillQuiz(skillId, level) {
    let quizData = SKILL_QUIZZES[skillId] && SKILL_QUIZZES[skillId][level];
    if (quizData) quizData.forEach((_, qi) => { delete S.skillQuizAnswers[`sk_${skillId}_${level}_${qi}`] });
    S.skillLevels[skillId + '_' + level] = false; save(); openSkillQuiz(skillId, level); render()
}
render();