<script lang="ts">
	import { onMount } from 'svelte';
	import { listFacts, editFact, deleteFact, type Fact } from '$lib/api';

	let { onClose, inline = false }: { onClose?: () => void; inline?: boolean } = $props();

	let facts = $state<Fact[]>([]);
	let query = $state('');
	let typeFilter = $state<string | null>(null);
	let loading = $state(false);
	let editingId = $state<number | null>(null);
	let editValue = $state('');

	const TYPES = ['preference', 'profile', 'financial', 'language', 'other'];
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	const shown = $derived(typeFilter ? facts.filter((f) => f.fact_type === typeFilter) : facts);

	onMount(load);

	async function load() {
		loading = true;
		try {
			facts = await listFacts(query.trim() || undefined);
		} catch (e) {
			console.error('falha a listar factos', e);
		} finally {
			loading = false;
		}
	}

	function onSearchInput() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(load, 250);
	}

	function startEdit(f: Fact) {
		editingId = f.id;
		editValue = f.text;
	}
	async function commitEdit() {
		if (editingId != null && editValue.trim()) {
			const id = editingId;
			const text = editValue.trim();
			editingId = null;
			await editFact(id, text);
			const f = facts.find((x) => x.id === id);
			if (f) f.text = text;
		} else {
			editingId = null;
		}
	}
	function onEditKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) commitEdit();
		else if (e.key === 'Escape') editingId = null;
	}
	async function remove(f: Fact) {
		if (!confirm('Apagar este facto?')) return;
		await deleteFact(f.id);
		facts = facts.filter((x) => x.id !== f.id);
	}
</script>

<div
	class="overlay"
	class:inline
	role="presentation"
	onclick={(e) => {
		if (!inline && e.target === e.currentTarget) onClose?.();
	}}
>
	<div class="panel" class:inline role="dialog" aria-label="Memória">
		<header class="panel-head">
			<h2><span class="dot"></span>Memória <span class="count">{facts.length}</span></h2>
			{#if !inline}
				<button class="close" onclick={() => onClose?.()} aria-label="Fechar">×</button>
			{/if}
		</header>

		<div class="controls">
			<input
				class="search"
				placeholder="pesquisar factos…"
				bind:value={query}
				oninput={onSearchInput}
			/>
			<div class="chips">
				<button class="chip" class:active={typeFilter === null} onclick={() => (typeFilter = null)}>
					todos
				</button>
				{#each TYPES as t}
					<button class="chip" class:active={typeFilter === t} onclick={() => (typeFilter = t)}>
						{t}
					</button>
				{/each}
			</div>
		</div>

		<div class="fact-list">
			{#if loading}
				<p class="muted">a carregar…</p>
			{:else if shown.length === 0}
				<p class="muted">nenhum facto {query ? 'para esta pesquisa' : 'ainda'}</p>
			{/if}

			{#each shown as f (f.id)}
				<div class="fact">
					<span class="tag tag-{f.fact_type}">{f.fact_type}</span>
					{#if editingId === f.id}
						<!-- svelte-ignore a11y_autofocus -->
						<textarea
							class="edit"
							bind:value={editValue}
							onkeydown={onEditKey}
							onblur={commitEdit}
							autofocus
						></textarea>
					{:else}
						<span class="fact-text">{f.text}</span>
						<div class="fact-actions">
							<button onclick={() => startEdit(f)} title="Editar" aria-label="Editar">✎</button>
							<button onclick={() => remove(f)} title="Apagar" aria-label="Apagar">🗑</button>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, #000 55%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 50;
		padding: 20px;
	}
	.panel {
		width: 100%;
		max-width: 560px;
		max-height: 80dvh;
		display: flex;
		flex-direction: column;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
	}

	/* Modo vista (sem moldura de modal): preenche a área à direita do rail. */
	.overlay.inline {
		position: static;
		inset: auto;
		flex: 1;
		min-width: 0;
		padding: 0;
		background: transparent;
		backdrop-filter: none;
		-webkit-backdrop-filter: none;
		animation: none;
	}
	.panel.inline {
		flex: 1;
		max-width: none;
		max-height: none;
		height: 100dvh;
		border: none;
		border-radius: 0;
		box-shadow: none;
		animation: none;
	}

	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 18px;
		border-bottom: 1px solid var(--border);
	}
	.panel-head h2 {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.panel-head .dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent);
	}
	.count {
		color: var(--fg-muted);
		font-size: 12px;
		font-weight: 400;
	}
	.close {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
	}
	.close:hover {
		color: var(--fg-strong);
	}

	.controls {
		padding: 12px 18px;
		border-bottom: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.search {
		background: var(--bg);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font: inherit;
		font-size: 13px;
		padding: 8px 12px;
		border-radius: 10px;
		outline: none;
	}
	.search:focus {
		border-color: var(--accent);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.chip {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font: inherit;
		font-size: 11px;
		padding: 4px 10px;
		border-radius: 999px;
		cursor: pointer;
	}
	.chip.active {
		color: var(--accent);
		border-color: var(--accent);
	}

	.fact-list {
		flex: 1;
		overflow-y: auto;
		padding: 10px 18px 18px;
	}
	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		margin: 24px 0;
	}
	.fact {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		padding: 10px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
	}
	.fact-text {
		flex: 1;
		font-family: var(--font-body);
		font-size: 14px;
		color: var(--fg-strong);
		line-height: 1.4;
	}
	.fact-actions {
		display: flex;
		gap: 2px;
		opacity: 0;
		transition: opacity 0.12s;
	}
	.fact:hover .fact-actions {
		opacity: 1;
	}
	.fact-actions button {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 12px;
		padding: 2px 4px;
	}
	.fact-actions button:hover {
		color: var(--fg-strong);
	}
	.edit {
		flex: 1;
		background: var(--bg);
		border: 1px solid var(--accent);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14px;
		padding: 6px 8px;
		border-radius: 8px;
		resize: vertical;
		min-height: 38px;
		outline: none;
	}

	.tag {
		flex: none;
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		padding: 3px 7px;
		border-radius: 6px;
		margin-top: 2px;
		background: color-mix(in srgb, var(--fg) 12%, transparent);
		color: var(--fg-muted);
	}
	.tag-financial {
		background: color-mix(in srgb, var(--green) 20%, transparent);
		color: var(--green);
	}
	.tag-preference {
		background: color-mix(in srgb, var(--accent) 20%, transparent);
		color: var(--accent);
	}
	.tag-language {
		background: color-mix(in srgb, var(--warn, #f0ad4e) 22%, transparent);
		color: var(--warn, #f0ad4e);
	}
</style>
