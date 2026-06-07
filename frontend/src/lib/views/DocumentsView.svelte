<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';
	import {
		listDocuments,
		createDocument,
		updateDocument,
		deleteDocument,
		assistDocument,
		type Doc
	} from '$lib/api';

	let docs = $state<Doc[]>([]);
	let selectedId = $state<number | null>(null);
	let title = $state('');
	let content = $state('');
	let loading = $state(true);
	let saveTimer: ReturnType<typeof setTimeout> | undefined;

	let instruction = $state('');
	let assisting = $state(false);
	let prevContent = $state<string | null>(null);

	const selected = $derived(docs.find((d) => d.id === selectedId) ?? null);

	const EXAMPLES = ['Resume', 'Corrige a gramática', 'Torna mais formal', 'Continua a escrever'];

	onMount(load);

	async function load() {
		loading = true;
		try {
			docs = await listDocuments();
			if (docs.length && selectedId == null) open(docs[0]);
		} finally {
			loading = false;
		}
	}

	function open(d: Doc) {
		selectedId = d.id;
		title = d.title;
		content = d.content;
		prevContent = null;
	}

	async function add() {
		const { id } = await createDocument('Novo documento', '');
		await load();
		const d = docs.find((x) => x.id === id);
		if (d) open(d);
	}

	function scheduleSave() {
		if (selectedId == null) return;
		clearTimeout(saveTimer);
		saveTimer = setTimeout(save, 600);
	}
	async function save() {
		if (selectedId == null) return;
		const id = selectedId;
		await updateDocument(id, { title, content });
		const d = docs.find((x) => x.id === id);
		if (d) {
			d.title = title;
			d.content = content;
		}
	}

	async function remove(d: Doc, e: Event) {
		e.stopPropagation();
		if (!confirm('Apagar este documento?')) return;
		await deleteDocument(d.id);
		if (selectedId === d.id) {
			selectedId = null;
			title = '';
			content = '';
		}
		await load();
	}

	async function runAssist(instr?: string) {
		const ins = (instr ?? instruction).trim();
		if (!ins || assisting) return;
		assisting = true;
		try {
			const r = await assistDocument(content, ins);
			prevContent = content;
			content = r.text;
			instruction = '';
			scheduleSave();
		} catch (e) {
			console.error('assist falhou', e);
		} finally {
			assisting = false;
		}
	}
	function undoAssist() {
		if (prevContent != null) {
			content = prevContent;
			prevContent = null;
			scheduleSave();
		}
	}
</script>

<div class="view docs">
	<div class="list-col">
		<div class="list-head">
			<span>Documentos</span>
			<button class="add" onclick={add} title="Novo" aria-label="Novo">+</button>
		</div>
		<div class="list">
			{#if loading}
				<p class="muted">a carregar…</p>
			{:else if docs.length === 0}
				<p class="muted">sem documentos. cria o primeiro.</p>
			{/if}
			{#each docs as d (d.id)}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<div class="doc-item" class:active={d.id === selectedId} onclick={() => open(d)}>
					<Icon name="file-text" size={14} />
					<span class="di-title">{d.title || 'sem título'}</span>
					<button class="del" onclick={(e) => remove(d, e)} aria-label="Apagar">🗑</button>
				</div>
			{/each}
		</div>
	</div>

	<div class="editor-col">
		{#if selected}
			<input class="title-in" placeholder="título" bind:value={title} oninput={scheduleSave} />
			<textarea
				class="content-in"
				placeholder="escreve… a IA assiste-te com a barra em baixo."
				bind:value={content}
				oninput={scheduleSave}
			></textarea>

			<div class="assist-bar">
				{#if prevContent != null}
					<button class="undo" onclick={undoAssist} title="Desfazer assistência">↶ desfazer</button>
				{/if}
				<div class="ex-row">
					{#each EXAMPLES as ex}
						<button class="ex" onclick={() => runAssist(ex)} disabled={assisting}>{ex}</button>
					{/each}
				</div>
				<div class="ai-input">
					<Icon name="zap" size={15} />
					<input
						placeholder="pede à IA (ex.: 'torna mais curto')…"
						bind:value={instruction}
						onkeydown={(e) => e.key === 'Enter' && runAssist()}
						disabled={assisting}
					/>
					<button class="apply" onclick={() => runAssist()} disabled={assisting || !instruction.trim()}>
						{assisting ? '…' : 'aplicar'}
					</button>
				</div>
			</div>
		{:else}
			<div class="empty-ed">seleciona ou cria um documento</div>
		{/if}
	</div>
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		display: flex;
	}
	.list-col {
		width: 270px;
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
	.doc-item {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 9px 10px;
		border-radius: 9px;
		cursor: pointer;
		margin-bottom: 2px;
	}
	.doc-item :global(svg) {
		flex: none;
		color: var(--fg-muted);
	}
	.doc-item:hover {
		background: color-mix(in srgb, var(--fg) 6%, transparent);
	}
	.doc-item.active {
		background: color-mix(in srgb, var(--accent) 14%, transparent);
		box-shadow: inset 2px 0 0 var(--accent);
	}
	.di-title {
		flex: 1;
		min-width: 0;
		font-size: 13px;
		color: var(--fg-strong);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.del {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 11px;
		opacity: 0;
	}
	.doc-item:hover .del {
		opacity: 1;
	}
	.del:hover {
		color: var(--red);
	}

	.editor-col {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		padding: 22px clamp(18px, 5vw, 60px) 16px;
	}
	.title-in {
		background: transparent;
		border: none;
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 21px;
		font-weight: 600;
		padding: 0 0 12px;
		outline: none;
		border-bottom: 1px solid var(--border);
		margin-bottom: 14px;
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
	.title-in::placeholder,
	.content-in::placeholder {
		color: var(--fg-muted);
	}

	.assist-bar {
		margin-top: 12px;
		padding-top: 12px;
		border-top: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.undo {
		align-self: flex-start;
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 11.5px;
		padding: 4px 10px;
		border-radius: 8px;
		cursor: pointer;
	}
	.undo:hover {
		color: var(--accent);
		border-color: var(--accent);
	}
	.ex-row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.ex {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-body);
		font-size: 12px;
		padding: 5px 11px;
		border-radius: 999px;
		cursor: pointer;
	}
	.ex:hover:not(:disabled) {
		color: var(--accent);
		border-color: var(--accent);
	}
	.ex:disabled {
		opacity: 0.5;
	}
	.ai-input {
		display: flex;
		align-items: center;
		gap: 8px;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 6px 6px 6px 12px;
	}
	.ai-input :global(svg) {
		color: var(--accent);
		flex: none;
	}
	.ai-input input {
		flex: 1;
		background: transparent;
		border: none;
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14px;
		padding: 6px 0;
		outline: none;
	}
	.ai-input input::placeholder {
		color: var(--fg-muted);
	}
	.apply {
		flex: none;
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font: inherit;
		font-size: 12.5px;
		font-weight: 600;
		padding: 8px 16px;
		border-radius: 9px;
		cursor: pointer;
	}
	.apply:disabled {
		opacity: 0.4;
		cursor: default;
	}
	.empty-ed {
		margin: auto;
		color: var(--fg-muted);
		font-size: 14px;
	}
</style>
