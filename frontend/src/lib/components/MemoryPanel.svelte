<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listFacts,
		editFact,
		deleteFact,
		listArchivedFacts,
		restoreFact,
		purgeFact,
		exportFacts,
		importFacts,
		listPending,
		approvePending,
		rejectPending,
		type Fact,
		type PendingFact
	} from '$lib/api';
	import { downloadJson, pickJsonFile } from '$lib/io';
	import Icon from './Icon.svelte';

	let pending = $state<PendingFact[]>([]);

	async function loadPending() {
		try {
			pending = await listPending();
		} catch (e) {
			console.error('falha a carregar pendentes', e);
		}
	}
	async function approve(p: PendingFact) {
		pending = pending.filter((x) => x.id !== p.id);
		await approvePending(p.id);
		await load();
	}
	async function reject(p: PendingFact) {
		pending = pending.filter((x) => x.id !== p.id);
		await rejectPending(p.id);
	}

	let { onClose, inline = false }: { onClose?: () => void; inline?: boolean } = $props();

	let facts = $state<Fact[]>([]);
	let archived = $state<Fact[]>([]);
	let showArchived = $state(false);
	let query = $state('');
	let typeFilter = $state<string | null>(null);
	let loading = $state(false);
	let editingId = $state<number | null>(null);
	let editValue = $state('');

	const TYPES = ['preference', 'profile', 'financial', 'language', 'other'];
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	const shown = $derived(typeFilter ? facts.filter((f) => f.fact_type === typeFilter) : facts);

	onMount(() => {
		load();
		loadPending();
	});

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
		// Apagar = arquivar (recuperável). Sem confirmação: é reversível.
		await deleteFact(f.id);
		facts = facts.filter((x) => x.id !== f.id);
		if (showArchived) await loadArchived();
	}

	async function loadArchived() {
		try {
			archived = await listArchivedFacts();
		} catch (e) {
			console.error('falha a listar arquivados', e);
		}
	}
	async function toggleArchived() {
		showArchived = !showArchived;
		if (showArchived) await loadArchived();
	}
	async function restore(f: Fact) {
		archived = archived.filter((x) => x.id !== f.id);
		await restoreFact(f.id);
		await load();
	}
	async function purge(f: Fact) {
		if (!confirm('Apagar DEFINITIVAMENTE? Esta ação não é recuperável.')) return;
		archived = archived.filter((x) => x.id !== f.id);
		await purgeFact(f.id);
	}

	async function doExport() {
		try {
			downloadJson('penelope-memoria.json', await exportFacts());
		} catch (e) {
			console.error('export falhou', e);
		}
	}
	async function doImport() {
		try {
			const data = await pickJsonFile();
			const arr = Array.isArray(data) ? data : (data as any)?.facts;
			if (!Array.isArray(arr)) {
				alert('ficheiro inválido: esperado uma lista de factos');
				return;
			}
			const { added } = await importFacts(arr);
			alert(`${added} facto(s) importado(s).`);
			query = '';
			await load();
		} catch (e) {
			alert('importação falhou: ficheiro inválido?');
		}
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
			<div class="head-actions">
				<button
					class="io-btn"
					class:active={showArchived}
					onclick={toggleArchived}
					title="Arquivados"
				>
					<Icon name="archive" size={14} /> {showArchived ? 'ativos' : 'arquivados'}
				</button>
				<button class="io-btn" onclick={doImport} title="Importar">
					<Icon name="upload" size={14} /> importar
				</button>
				<button class="io-btn" onclick={doExport} title="Exportar">
					<Icon name="download" size={14} /> exportar
				</button>
				{#if !inline}
					<button class="close" onclick={() => onClose?.()} aria-label="Fechar">×</button>
				{/if}
			</div>
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

		{#if pending.length}
			<div class="pending">
				<div class="pending-head">
					<Icon name="brain" size={13} /> a aprovar <span class="count">{pending.length}</span>
				</div>
				{#each pending as p (p.id)}
					<div class="pend-item">
						<span class="tag tag-{p.fact_type}">{p.fact_type}</span>
						<span class="pend-text">{p.text}</span>
						<div class="pend-actions">
							<button class="ok" onclick={() => approve(p)} title="Aprovar" aria-label="Aprovar">✓</button>
							<button class="no" onclick={() => reject(p)} title="Rejeitar" aria-label="Rejeitar">✕</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}

		{#if showArchived}
			<div class="fact-list">
				{#if archived.length === 0}
					<p class="muted">nenhum facto arquivado</p>
				{/if}
				{#each archived as f (f.id)}
					<div class="fact">
						<span class="tag tag-{f.fact_type}">{f.fact_type}</span>
						<span class="fact-text archived-text">{f.text}</span>
						<div class="fact-actions">
							<button onclick={() => restore(f)} title="Restaurar" aria-label="Restaurar">↺</button>
							<button onclick={() => purge(f)} title="Apagar definitivo" aria-label="Apagar definitivo">🗑</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
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
		{/if}
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
	.head-actions {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.io-btn {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 11px;
		padding: 5px 9px;
		border-radius: 8px;
		cursor: pointer;
		transition: color 0.14s, border-color 0.14s;
	}
	.io-btn:hover {
		color: var(--accent);
		border-color: var(--accent);
	}
	.io-btn.active {
		color: var(--accent);
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
	}
	.archived-text {
		opacity: 0.7;
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

	.pending {
		margin: 4px 14px 0;
		padding: 8px;
		border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
		border-radius: 11px;
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.pending-head {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		color: var(--accent);
		padding: 2px 4px 8px;
	}
	.pend-item {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		padding: 7px 4px;
	}
	.pend-text {
		flex: 1;
		font-family: var(--font-body);
		font-size: 13.5px;
		color: var(--fg-strong);
		line-height: 1.4;
	}
	.pend-actions {
		display: flex;
		gap: 4px;
	}
	.pend-actions button {
		width: 24px;
		height: 24px;
		border-radius: 7px;
		border: 1px solid var(--border);
		background: transparent;
		cursor: pointer;
		font-size: 12px;
		line-height: 1;
	}
	.pend-actions .ok {
		color: var(--green);
		border-color: color-mix(in srgb, var(--green) 45%, transparent);
	}
	.pend-actions .ok:hover {
		background: color-mix(in srgb, var(--green) 18%, transparent);
	}
	.pend-actions .no {
		color: var(--red);
		border-color: color-mix(in srgb, var(--red) 45%, transparent);
	}
	.pend-actions .no:hover {
		background: color-mix(in srgb, var(--red) 18%, transparent);
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
