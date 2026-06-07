/** Sistema de temas — réplica da estrutura/lógica do Odysseus:
 *  presets em THEMES, aplicar via CSS variables no :root, persistir em localStorage.
 *  As variáveis secundárias do app.css derivam destas base (color-mix). */

export interface Theme {
	bg: string;
	fg: string;
	panel: string;
	border: string;
	red: string;
	accent: string;
}

// Paletas dos presets do Odysseus (static/js/theme.js), com `accent` adicionado
// para o Penelope (o Odysseus usava fg/red como acento via fallback).
export const THEMES: Record<string, Theme> = {
	dark: { bg: '#0d0e11', fg: '#e6e8ec', panel: '#15171c', border: '#262a31', red: '#e06c75', accent: '#00aaff' },
	light: { bg: '#f0ebe3', fg: '#5a5248', panel: '#faf6f0', border: '#d4cdc2', red: '#c47d5a', accent: '#c47d5a' },
	midnight: { bg: '#0d1117', fg: '#c9d1d9', panel: '#161b22', border: '#30363d', red: '#f85149', accent: '#58a6ff' },
	paper: { bg: '#faf8f5', fg: '#3b3836', panel: '#ffffff', border: '#d5d0c8', red: '#c5ac4a', accent: '#c5ac4a' },
	cyberpunk: { bg: '#0a0a0f', fg: '#0ff0fc', panel: '#12101a', border: '#9b30ff', red: '#e040fb', accent: '#0ff0fc' },
	retrowave: { bg: '#1a1a2e', fg: '#e94560', panel: '#16213e', border: '#533483', red: '#e94560', accent: '#ff6ec7' },
	forest: { bg: '#1b2a1b', fg: '#a8d5a2', panel: '#142414', border: '#3d6b3d', red: '#e06c75', accent: '#7cb871' },
	ocean: { bg: '#0b1a2c', fg: '#64d2ff', panel: '#091422', border: '#1e5074', red: '#e06c75', accent: '#4facfe' },
	ume: { bg: '#2b1b2e', fg: '#f5c2e7', panel: '#1e1420', border: '#6c4675', red: '#f5a0c0', accent: '#f5a0c0' },
	copper: { bg: '#1c1410', fg: '#e8c39e', panel: '#140f0a', border: '#7a5533', red: '#d4764e', accent: '#d4764e' },
	terminal: { bg: '#000000', fg: '#00ff41', panel: '#0a0a0a', border: '#003b00', red: '#00ff41', accent: '#00ff41' },
	organs: { bg: '#0a0406', fg: '#efe1c8', panel: '#15080a', border: '#3a1519', red: '#c83240', accent: '#c83240' },
	lavender: { bg: '#f3eef8', fg: '#3d3551', panel: '#faf7ff', border: '#cec3de', red: '#9b6dcc', accent: '#9b6dcc' },
	gpt: { bg: '#212121', fg: '#ececec', panel: '#171717', border: '#424242', red: '#949494', accent: '#10a37f' },
	claude: { bg: '#262624', fg: '#f5f4f0', panel: '#30302e', border: '#4a4a47', red: '#c6613f', accent: '#c6613f' },
	cute: { bg: '#fff0f5', fg: '#d4608a', panel: '#fff8fa', border: '#f0c0d0', red: '#ff6b9d', accent: '#ff6b9d' }
};

export const DEFAULT_THEME = 'dark';
const LS_KEY = 'penelope-theme';

// Animação de fundo (CSS-only) associada a alguns temas.
export const THEME_ANIM: Record<string, string> = {
	cyberpunk: 'grid',
	retrowave: 'scan',
	ocean: 'waves',
	forest: 'petals',
	ume: 'petals',
	cute: 'sparkles',
	terminal: 'matrix',
	midnight: 'stars',
	organs: 'embers',
	dark: 'stars'
};

/** Liga/desliga a animação de fundo do tema (via data-anim no <html>). */
export function applyAnimation(theme: string, enabled: boolean): void {
	const a = enabled ? THEME_ANIM[theme] || '' : '';
	const root = document.documentElement;
	if (a) root.setAttribute('data-anim', a);
	else root.removeAttribute('data-anim');
}

export function applyTheme(name: string): void {
	const t = THEMES[name] ?? THEMES[DEFAULT_THEME];
	const s = document.documentElement.style;
	s.setProperty('--bg', t.bg);
	s.setProperty('--fg', t.fg);
	s.setProperty('--panel', t.panel);
	s.setProperty('--border', t.border);
	s.setProperty('--red', t.red);
	s.setProperty('--accent', t.accent);
}

export function loadTheme(): string {
	try {
		const v = localStorage.getItem(LS_KEY);
		if (v && THEMES[v]) return v;
	} catch {}
	return DEFAULT_THEME;
}

export function saveTheme(name: string): void {
	try {
		localStorage.setItem(LS_KEY, name);
	} catch {}
}

export function setTheme(name: string): void {
	applyTheme(name);
	saveTheme(name);
}
