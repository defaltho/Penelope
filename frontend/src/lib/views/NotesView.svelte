<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listNotes,
		createNote,
		updateNote,
		deleteNote,
		type Note
	} from '$lib/api';

	let notes = $state<Note[]>([]);
	let selectedId = $state<number | null>(null);
	let title = $state('');
	let content = $state('');
	let loading = $state(true);
	let saveTimer: ReturnType<typeof setTimeout> | undefined;

	const selected = $derived(notes.find((n) => n.id === selectedId) ?? null);

	onMount(load);

	async function load() {
		loading = true;
		try {
			notes = await listNotes();
			if (notes.length && selectedId == null) open(notes[0]);
		} finally {
			loading = false;
		}
	}

	function open(n: Note) {
		selectedId = n.id;
		title = n.title;
		content = n.content;
	}

	async function add() {
		const { id } = await createNote('Nova nota', '');
		await load();
		const n = notes.find((x) => x.id === id);
		if (n) open(n);
	}

	function scheduleSave() {
		if (selectedId == null) return;
		clearTimeout(saveTimer);
		saveTimer = setTimeout(save, 500);
	}
	async function save() {
		if (selectedId == null) return;
		const id = selectedId;
		await updateNote(id, { title, content });
		const n = notes.find((x) => x.id === id);
		if (n) {
			n.title = title;
			n.content = content;
		}
	}

	async function togglePin(n: Note, e: Event) {
		e.stopPropagation();
		await updateNote(n.id, { pinned: !n.pinned });
		await load();
	}

	async function remove(n: Note, e: Event) {
		e.stopPropagation();
		if (!confirm('Apagar esta nota?')) return;
		await deleteNote(n.id);
		if (selectedId === n.id) {
			selectedId = null;
			title = '';
			content = '';
		}
		await load();
	}

	function preview(n: Note): string {
		return (n.content || '').replace(/\n/g, ' ').slice(0, 60) || 'sem conteúdo';
	}
</script>

<div class="view notes">
	<div class="list-col">
		<div class="list-head">
			<span>Notas</span>
			<button class="add" onclick={add} title="Nova nota" aria-label="Nova nota">+</button>
		</div>
		<div class="list">
			{#if loading}
				<p class="muted">a carregar…</p>
			{:else if notes.length === 0}
				<p class="muted">sem notas. cria a primeira.</p>
			{/if}
			{#each notes as n (n.id)}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<div class="note-item" class:active={n.id === selectedId} onclick={() => open(n)}>
					<div class="ni-top">
						<span class="ni-title">{n.title || 'sem título'}</span>
						<span class="ni-actions">
							<button
								class="pin"
								class:on={n.pinned}
								onclick={(e) => togglePin(n, e)}
								title="Fixar"
								aria-label="Fixar">★</button
							>
							<button onclick={(e) => remove(n, e)} title="Apagar" aria-label="Apagar">🗑</button>
						</span>
					</div>
					<span class="ni-preview">{preview(n)}</span>
				</div>
			{/each}
		</div>
	</div>

	<div class="editor-col">
		{#if selected}
			<input class="title-in" placeholder="título" bind:value={title} oninput={scheduleSave} />
			<textarea
				class="content-in"
				placeholder="escreve a tua nota… (markdown)"
				bind:value={content}
				oninput={scheduleSave}
			></textarea>
			<div class="ed-foot">guardado automaticamente</div>
		{:else}
			<div class="empty-ed">seleciona ou cria uma nota</div>
		{/if}
	</div>
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		min-height: 0;
		display: flex;
	}
	.list-col {
		width: 280px;
		flex: none;
		border-right: 1px solid var(--border);
		background: var(--panel-2);
		display: flex;
		flex-direction: column;
	}
	.list-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 16px 12px;
		font-weight: 600;
		color: var(--fg-strong);
		border-bottom: 1px solid var(--border);
	}
	.add {
		width: 28px;
		height: 28px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: transparent;
		color: var(--fg-muted);
		font-size: 17px;
		line-height: 1;
		cursor: pointer;
	}
	.add:hover {
		color: var(--accent);
		border-color: var(--accent);
	}
	.list {
		flex: 1;
		overflow-y: auto;
		padding: 8px;
	}
	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		margin: 24px 0;
	}
	.note-item {
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		border-radius: 10px;
		padding: 10px;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-bottom: 2px;
	}
	.note-item:hover {
		background: color-mix(in srgb, var(--fg) 6%, transparent);
	}
	.note-item.active {
		background: color-mix(in srgb, var(--accent) 14%, transparent);
		box-shadow: inset 2px 0 0 var(--accent);
	}
	.ni-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 6px;
	}
	.ni-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--fg-strong);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.ni-actions {
		display: flex;
		gap: 2px;
		opacity: 0;
		transition: opacity 0.12s;
	}
	.note-item:hover .ni-actions,
	.note-item.active .ni-actions {
		opacity: 1;
	}
	.ni-actions button {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 11px;
		padding: 2px 3px;
	}
	.ni-actions .pin.on {
		color: var(--warn, #f0ad4e);
	}
	.ni-actions button:hover {
		color: var(--fg-strong);
	}
	.ni-preview {
		font-size: 11.5px;
		color: var(--fg-muted);
		font-family: var(--font-body);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.editor-col {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		padding: 24px clamp(20px, 6vw, 80px);
	}
	.title-in {
		background: transparent;
		border: none;
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 22px;
		font-weight: 600;
		padding: 0 0 12px;
		outline: none;
		border-bottom: 1px solid var(--border);
		margin-bottom: 16px;
	}
	.content-in {
		flex: 1;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-body);
		font-size: 15px;
		line-height: 1.6;
		resize: none;
		outline: none;
	}
	.content-in::placeholder,
	.title-in::placeholder {
		color: var(--fg-muted);
	}
	.ed-foot {
		font-size: 10.5px;
		color: var(--fg-muted);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		padding-top: 12px;
	}
	.empty-ed {
		margin: auto;
		color: var(--fg-muted);
		font-size: 14px;
	}
</style>
