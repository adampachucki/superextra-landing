import { browser } from '$app/environment';

type ThemeMode = 'light' | 'dark' | 'system';

let mode = $state<ThemeMode>(browser ? (localStorage.getItem('se_theme') as ThemeMode) || 'light' : 'light');

function apply() {
	if (!browser) return;
	const isDark =
		mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
	document.documentElement.classList.toggle('dark', isDark);
}

if (browser) {
	apply();
	matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		if (mode === 'system') apply();
	});
}

export const theme = {
	get mode() {
		return mode;
	},
	get isDark() {
		if (!browser) return false;
		return document.documentElement.classList.contains('dark');
	},
	cycle() {
		const next: ThemeMode = mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system';
		mode = next;
		if (next === 'system') {
			localStorage.removeItem('se_theme');
		} else {
			localStorage.setItem('se_theme', next);
		}
		apply();
	}
};
