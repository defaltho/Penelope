<script lang="ts">
	import { searchMessages, type SearchHit } from '$lib/api';

	let { onClose, onOpen }: { onClose: () => void; onOpen: (conversationId: number) => void } =
		$props();

	let query = $state('');
	let hits = $state<SearchHit[]>([]);
	let active = $state(0);
	let loading = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	const tokens = $derived(query.toLowerCase().match(/\w+/g) ?? []);

	// Agrupar por conversa, preservando a ordem (mais recente primeiro).
	const groups = $derived.by(() => {
		const map = new Map<number, { title: string; time: string; hits: SearchHit[] }>();
		for (const h of hits) {
			if (!map.has(h.conversation_id)) {
				map.set(h.conversation_id, {
					title: (h.conv_title || 'conversa').trim(),
					time: h.created_at,
					hits: []
				});
			}
			map.get(h.conversation_id)!.hits.push(h);
		}
		return [...map.values()];
	});

	// Lista achatada para navegação por teclado.
	const flat = $derived(groups.flatMap((g) => g.hits));

	function onInput() {
		clearTimeout(timer);
		timer = setTimeout(run, 180);
	}
	async function run() {
		const q = query.trim();
		if (!q) {
			hits = [];
			return;
		}
		loading = true;
		try {
			hits = await searchMessages(q);
			active = 0;
		} catch (e) {
			hits = [];
		} finally {
			loading = false;
		}
	}

	function choose(h: SearchHit) {
		onOpen(h.conversation_id);
		onClose();
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onClose();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			active = Math.min(active + 1, flat.length - 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			active = Math.max(active - 1, 0);
		} else if (e.key === 'Enter') {
			e.preventDefault();
			if (flat[active]) choose(flat[active]);
		}
	}

	// Snippet centrado no primeiro match + segmentos para destacar.
	function snippetParts(content: string): { t: string; hit: boolean }[] {
		const text = content.replace(/\s+/g, ' ').trim();
		let pos = -1;
		const low = text.toLowerCase();
		for (const tk of tokens) {
			const i = low.indexOf(tk);
			if (i >= 0 && (pos === -1 || i < pos)) pos = i;
		}
		let start = 0;
		let snip = text;
		if (pos > 40) {
			start = pos - 30;
			snip = '… ' + text.slice(start);
		}
		if (snip.length > 120) snip = snip.slice(0, 120) + ' …';

		if (tokens.length === 0) return [{ t: snip, hit: false }];
		const esc = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
		const re = new RegExp(`(${esc.join('|')})`, 'gi');
		const parts: { t: string; hit: boolean }[] = [];
		let last = 0;
		let m: RegExpExecArray | null;
		while ((m = re.exec(snip))) {
			if (m.index > last) parts.push({ t: snip.slice(last, m.index), hit: false });
			parts.push({ t: m[0], hit: true });
			last = m.index + m[0].length;
			if (m.index === re.lastIndex) re.lastIndex++;
		}
		if (last < snip.length) parts.push({ t: snip.slice(last), hit: false });
		return parts;
	}

	const WD = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
	function relTime(iso: string): string {
		const d = new Date(iso.replace(' ', 'T') + 'Z');
		if (isNaN(d.getTime())) return '';
		const hh = String(d.getHours()).padStart(2, '0');
		const mm = String(d.getMinutes()).padStart(2, '0');
		const days = (Date.now() - d.getTime()) / 86400000;
		if (days < 1 && d.getDate() === new Date().getDate()) return `hoje, ${hh}:${mm}`;
		if (days < 7) return `${WD[d.getDay()]}, ${hh}:${mm}`;
		return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}, ${hh}:${mm}`;
	}
	function headTime(iso: string): string {
		const d = new Date(iso.replace(' ', 'T') + 'Z');
		if (isNaN(d.getTime())) return '';
		return d.toTimeString().slice(0, 8);
	}
</script>

<div
	class="overlay"
	role="presentation"
	onclick={(e) => {
		if (e.target === e.currentTarget) onClose();
	}}
>
	<div class="palette" role="dialog" aria-label="Pesquisa">
		<div class="search-row">
			<!-- svelte-ignore a11y_autofocus -->
			<input
				class="search-in"
				placeholder="pesquisar em todas as conversas…"
				bind:value={query}
				oninput={onInput}
				onkeydown={onKey}
				autofocus
			/>
		</div>

		{#if query.trim()}
			<div class="results">
				{#if loading && hits.length === 0}
					<p class="muted">a pesquisar…</p>
				{:else if hits.length === 0}
					<p class="muted">sem resultados para "{query}"</p>
				{/if}

				{#each groups as g (g.title + g.time)}
					<div class="group">
						<div class="g-head">
							<span class="g-title">{g.title}</span>
							<span class="g-time">{headTime(g.time)}</span>
						</div>
						{#each g.hits as h (h.id)}
							<button
								class="hit"
								class:active={flat[active]?.id === h.id}
								onclick={() => choose(h)}
								onmouseenter={() => (active = flat.findIndex((x) => x.id === h.id))}
							>
								<span class="role">{h.role === 'user' ? 'You' : 'AI'}</span>
								<span class="snip">
									{#each snippetParts(h.content) as p}{#if p.hit}<mark>{p.t}</mark>{:else}{p.t}{/if}{/each}
								</span>
								<span class="time">{relTime(h.created_at)}</span>
							</button>
						{/each}
					</div>
				{/each}
			</div>
		{:else}
			<div class="hintbar">escreve para pesquisar · ↑↓ navegar · ⏎ abrir · esc fechar</div>
		{/if}
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, #000 62%, transparent);
		display: flex;
		justify-content: center;
		align-items: flex-start;
		padding-top: 12vh;
		z-index: 80;
		animation: pen-fade 0.16s ease-out;
	}
	.palette {
		width: 100%;
		max-width: 720px;
		max-height: 70vh;
		display: flex;
		flex-direction: column;
		background: color-mix(in srgb, var(--panel) 96%, #000);
		border: 1px solid var(--border);
		border-radius: 16px;
		box-shadow: var(--shadow-panel);
		overflow: hidden;
		animation: pen-pop 0.2s cubic-bezier(0.22, 0.61, 0.36, 1);
	}

	.search-row {
		padding: 6px;
		border-bottom: 1px solid var(--border);
	}
	.search-in {
		width: 100%;
		background: transparent;
		border: none;
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 18px;
		padding: 14px 16px;
		outline: none;
	}
	.search-in::placeholder {
		color: var(--fg-muted);
	}

	.results {
		overflow-y: auto;
		padding: 6px;
	}
	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		padding: 24px 0;
	}

	.group {
		margin-bottom: 8px;
	}
	.g-head {
		display: flex;
		align-items: baseline;
		gap: 10px;
		padding: 10px 12px 6px;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.4px;
		color: var(--fg-muted);
		text-transform: uppercase;
	}
	.g-title {
		max-width: 70%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.g-time {
		opacity: 0.7;
		font-weight: 400;
	}

	.hit {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 9px;
		padding: 9px 12px;
		cursor: pointer;
		font-family: var(--font-ui);
	}
	.hit.active {
		background: color-mix(in srgb, var(--fg) 7%, transparent);
		border-color: color-mix(in srgb, var(--border) 70%, transparent);
	}
	.role {
		flex: none;
		width: 28px;
		font-size: 11px;
		color: var(--fg-muted);
	}
	.snip {
		flex: 1;
		min-width: 0;
		font-size: 13px;
		color: var(--fg);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.snip :global(mark) {
		background: #f0ad4e;
		color: #1b1b1b;
		border-radius: 3px;
		padding: 0 2px;
		font-weight: 600;
	}
	.time {
		flex: none;
		font-size: 11px;
		color: var(--fg-muted);
	}

	.hintbar {
		padding: 14px 18px;
		font-size: 11.5px;
		color: var(--fg-muted);
		text-align: center;
	}
</style>
