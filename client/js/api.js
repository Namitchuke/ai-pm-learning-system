// API wrapper for the AI PM Learning System
const API = {
    async getMe() {
        const res = await fetch('/auth/me');
        if (!res.ok) { window.location.href = '/'; return null; }
        return (await res.json()).user;
    },

    async getProgress() {
        const res = await fetch('/api/progress');
        if (!res.ok) throw new Error('Failed to load progress');
        return res.json();
    },

    async saveProgress(data) {
        const res = await fetch('/api/progress', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Failed to save progress');
        return res.json();
    },

    async getPhases() {
        const res = await fetch('/api/content/phases');
        if (!res.ok) throw new Error('Failed to load phases');
        return res.json();
    },

    async getQuizzes() {
        const res = await fetch('/api/content/quizzes');
        if (!res.ok) throw new Error('Failed to load quizzes');
        return res.json();
    },

    async getInterviews() {
        const res = await fetch('/api/content/interviews');
        if (!res.ok) throw new Error('Failed to load interviews');
        return res.json();
    },

    async getCases() {
        const res = await fetch('/api/content/cases');
        if (!res.ok) throw new Error('Failed to load cases');
        return res.json();
    },

    async logout() {
        await fetch('/auth/logout', { method: 'POST' });
        window.location.href = '/';
    }
};
