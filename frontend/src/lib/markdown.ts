/**
 * Renderer de Markdown mínimo e local-first (B7). Não é CommonMark completo:
 * cobre o que aparece numa resposta de chat (code fences, inline code, bold,
 * italic, headings, listas, blockquotes, links). Escapa SEMPRE o HTML primeiro,
 * por isso o output de {@html} é seguro mesmo com conteúdo do modelo.
 */

function escapeHtml(s: string): string {
	return s
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
}

function inline(s: string): string {
	// s já vem com HTML escapado. Aplicar transformações inline.
	return (
		s
			// código inline `code`
			.replace(/`([^`]+)`/g, (_m, c) => `<code class="md-ic">${c}</code>`)
			// diálogo entre aspas -> bold (mínimo 2 chars para evitar falsos positivos)
			.replace(/&quot;([^&]{2,}?)&quot;/g, '<strong>&quot;$1&quot;</strong>')
			.replace(/"([^"]{2,})"/g, '<strong>"$1"</strong>')
			// negrito **x** e __x__
			.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
			.replace(/__([^_]+)__/g, '<strong>$1</strong>')
			// itálico *x* e _x_
			.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
			.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>')
			// links [texto](url) — só http(s) para segurança
			.replace(
				/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
				'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
			)
	);
}

export function sanitizePartial(src: string): string {
	let s = src;
	const fences = (s.match(/```/g) || []).length;
	if (fences % 2 === 1) s += '\n```';
	const bolds = (s.match(/\*\*/g) || []).length;
	if (bolds % 2 === 1) s += '**';
	const italics = (s.match(/(?<!\*)\*(?!\*)/g) || []).length;
	if (italics % 2 === 1) s += '*';
	const ticks = (s.match(/(?<!`)`(?!`)/g) || []).length;
	if (ticks % 2 === 1) s += '`';
	return s;
}

export function renderMarkdown(src: string): string {
	const out: string[] = [];
	// Separar blocos de código cercados (```), preservando o conteúdo cru.
	const parts = src.split(/```/);
	for (let i = 0; i < parts.length; i++) {
		if (i % 2 === 1) {
			// Bloco de código: 1ª linha pode ser a linguagem.
			const nl = parts[i].indexOf('\n');
			const lang = nl >= 0 ? parts[i].slice(0, nl).trim() : '';
			const code = nl >= 0 ? parts[i].slice(nl + 1) : parts[i];
			const body = escapeHtml(code.replace(/\n$/, ''));
			out.push(
				`<div class="md-code"><div class="md-code-head"><span class="md-lang">${escapeHtml(
					lang
				)}</span><button class="md-copy" type="button">copiar</button></div><pre><code>${body}</code></pre></div>`
			);
		} else {
			out.push(renderBlocks(parts[i]));
		}
	}
	return out.join('');
}

function isTableSep(line: string): boolean {
	// Linha separadora de tabela: | --- | :--: | ---: |
	return /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/.test(line) && line.includes('-');
}

function splitRow(line: string): string[] {
	let s = line.trim();
	if (s.startsWith('|')) s = s.slice(1);
	if (s.endsWith('|')) s = s.slice(0, -1);
	return s.split('|').map((c) => c.trim());
}

function renderTable(header: string, rows: string[][]): string {
	const ths = splitRow(header)
		.map((c) => `<th>${inline(escapeHtml(c))}</th>`)
		.join('');
	const trs = rows
		.map(
			(r) =>
				`<tr>${r.map((c) => `<td>${inline(escapeHtml(c))}</td>`).join('')}</tr>`
		)
		.join('');
	return `<table class="md-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

function renderBlocks(text: string): string {
	const lines = text.split('\n');
	const html: string[] = [];
	let list: 'ul' | 'ol' | null = null;
	let para: string[] = [];

	const flushPara = () => {
		if (para.length) {
			html.push(`<p>${inline(escapeHtml(para.join(' ')))}</p>`);
			para = [];
		}
	};
	const closeList = () => {
		if (list) {
			html.push(`</${list}>`);
			list = null;
		}
	};

	for (let li = 0; li < lines.length; li++) {
		const raw = lines[li];
		const line = raw.replace(/\s+$/, '');
		if (!line.trim()) {
			flushPara();
			closeList();
			continue;
		}
		// Tabela: linha com '|' seguida de uma linha separadora.
		if (line.includes('|') && li + 1 < lines.length && isTableSep(lines[li + 1])) {
			flushPara();
			closeList();
			const header = line;
			const rows: string[][] = [];
			li += 2; // saltar header + separador
			while (li < lines.length && lines[li].includes('|') && lines[li].trim()) {
				rows.push(splitRow(lines[li]));
				li++;
			}
			li--; // o for volta a incrementar
			html.push(renderTable(header, rows));
			continue;
		}
		const h = line.match(/^(#{1,4})\s+(.*)$/);
		if (h) {
			flushPara();
			closeList();
			const lvl = h[1].length;
			html.push(`<h${lvl} class="md-h">${inline(escapeHtml(h[2]))}</h${lvl}>`);
			continue;
		}
		const ul = line.match(/^\s*[-*]\s+(.*)$/);
		const ol = line.match(/^\s*\d+\.\s+(.*)$/);
		if (ul || ol) {
			flushPara();
			const want = ul ? 'ul' : 'ol';
			if (list !== want) {
				closeList();
				html.push(`<${want} class="md-list">`);
				list = want;
			}
			html.push(`<li>${inline(escapeHtml((ul || ol)![1]))}</li>`);
			continue;
		}
		const bq = line.match(/^\s*>\s?(.*)$/);
		if (bq) {
			flushPara();
			closeList();
			html.push(`<blockquote class="md-bq">${inline(escapeHtml(bq[1]))}</blockquote>`);
			continue;
		}
		para.push(line.trim());
	}
	flushPara();
	closeList();
	return html.join('');
}
