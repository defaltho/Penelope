<script lang="ts">
	import Icon from './Icon.svelte';
	import type { ConversationSummary } from '$lib/api';

	let {
		activeView,
		onSelectView,
		conversations = [],
		activeConvoId = null,
		onSelectConvo,
		onNewChat,
		onRenameConvo,
		onDeleteConvo,
		onToggle,
		onCycleTheme,
		onOpenSearch
	}: {
		activeView: string;
		onSelectView: (v: string) => void;
		conversations: ConversationSummary[];
		activeConvoId: number | null;
		onSelectConvo: (id: number) => void;
		onNewChat: () => void;
		onRenameConvo: (id: number, title: string) => void;
		onDeleteConvo: (id: number) => void;
		onToggle: () => void;
		onCycleTheme: () => void;
		onOpenSearch: () => void;
	} = $props();

	const nav = [
		{ id: 'memory', icon: 'brain', label: 'Memória' },
		{ id: 'skills', icon: 'lightbulb', label: 'Skills' },
		{ id: 'compare', icon: 'columns', label: 'Compare' },
		{ id: 'gallery', icon: 'image', label: 'Galeria' },
		{ id: 'notes', icon: 'sticky-note', label: 'Notas' },
		{ id: 'tasks', icon: 'list-checks', label: 'Tarefas' },
		{ id: 'pipeline', icon: 'file-text', label: 'Pipeline' }
	];

	let editingId = $state<number | null>(null);
	let editValue = $state('');

	function label(c: ConversationSummary) {
		return (c.title || c.snippet || 'Nova conversa').trim();
	}
	function relTime(iso: string) {
		const t = Date.parse(iso.replace(' ', 'T') + 'Z');
		if (isNaN(t)) return '';
		const d = (Date.now() - t) / 1000;
		if (d < 60) return 'agora';
		if (d < 3600) return `${Math.floor(d / 60)}m`;
		if (d < 86400) return `${Math.floor(d / 3600)}h`;
		return `${Math.floor(d / 86400)}d`;
	}
	function startRename(c: ConversationSummary, e: Event) {
		e.stopPropagation();
		editingId = c.id;
		editValue = label(c);
	}
	function commitRename() {
		if (editingId != null && editValue.trim()) onRenameConvo(editingId, editValue.trim());
		editingId = null;
	}
	function onRenameKey(e: KeyboardEvent) {
		if (e.key === 'Enter') commitRename();
		else if (e.key === 'Escape') editingId = null;
	}
	function confirmDelete(c: ConversationSummary, e: Event) {
		e.stopPropagation();
		if (confirm(`Apagar "${label(c)}"?`)) onDeleteConvo(c.id);
	}
</script>

<aside class="nav-sidebar">
	<header class="ns-head">
		<span class="brand"><span class="bdot"></span>penelope</span>
		<button class="ham" onclick={onToggle} title="Esconder" aria-label="Esconder barra lateral">
			<Icon name="menu" size={17} />
		</button>
	</header>

	<div class="ns-scroll">
		<button class="row action" onclick={onNewChat}>
			<Icon name="plus" size={17} stroke={2.2} /><span>Nova conversa</span>
		</button>
		<button class="row action" onclick={onOpenSearch}>
			<Icon name="search" size={16} /><span>Pesquisa</span>
		</button>

		<button
			class="row section"
			class:active={activeView === 'chat'}
			onclick={() => onSelectView('chat')}
		>
			<Icon name="message-square" size={16} /><span>Chats</span>
		</button>

		<div class="convs">
			{#each conversations as c (c.id)}
				<div
					class="conv"
					class:active={activeView === 'chat' && c.id === activeConvoId}
					role="button"
					tabindex="0"
					onclick={() => onSelectConvo(c.id)}
					onkeydown={(e) => e.key === 'Enter' && onSelectConvo(c.id)}
				>
					{#if editingId === c.id}
						<!-- svelte-ignore a11y_autofocus -->
						<input
							class="conv-edit"
							bind:value={editValue}
							onkeydown={onRenameKey}
							onblur={commitRename}
							onclick={(e) => e.stopPropagation()}
							autofocus
						/>
					{:else}
						<Icon name="message-square" size={13} />
						<span class="conv-title">{label(c)}</span>
						<span class="conv-time">{relTime(c.updated_at)}</span>
						<span class="conv-actions">
							<button onclick={(e) => startRename(c, e)} aria-label="Renomear" title="Renomear">✎</button>
							<button onclick={(e) => confirmDelete(c, e)} aria-label="Apagar" title="Apagar">🗑</button>
						</span>
					{/if}
				</div>
			{/each}
			{#if conversations.length === 0}
				<p class="empty">sem conversas</p>
			{/if}
		</div>

		{#each nav as v (v.id)}
			<button
				class="row"
				class:active={activeView === v.id}
				onclick={() => onSelectView(v.id)}
			>
				<Icon name={v.icon} size={16} /><span>{v.label}</span>
			</button>
		{/each}

		<button class="row" onclick={onCycleTheme}>
			<Icon name="palette" size={16} /><span>Tema</span>
		</button>
	</div>

	<footer class="ns-foot">
		<button class="row" class:active={activeView === 'settings'} onclick={() => onSelectView('settings')}>
			<Icon name="settings" size={16} /><span>Definições</span>
		</button>
	</footer>
</aside>

<style>
	.nav-sidebar {
		width: 268px;
		flex: none;
		height: 100dvh;
		display: flex;
		flex-direction: column;
		background: var(--panel-2);
		border-right: 1px solid var(--border);
		font-family: var(--font-ui);
	}

	.ns-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		min-height: 48px;
		padding: 12px 14px;
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 9px;
		font-size: 17px;
		font-weight: 700;
		color: var(--fg-strong);
		letter-spacing: 0.3px;
	}
	.bdot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 9px var(--accent);
	}
	.ham {
		display: grid;
		place-items: center;
		width: 32px;
		height: 32px;
		border-radius: 8px;
		border: none;
		background: transparent;
		color: var(--fg-muted);
		cursor: pointer;
	}
	.ham:hover {
		color: var(--fg-strong);
		background: color-mix(in srgb, var(--fg) 8%, transparent);
	}

	.ns-scroll {
		flex: 1;
		overflow-y: auto;
		padding: 4px 8px 8px;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-ui);
		font-size: 14px;
		padding: 9px 10px;
		border-radius: 9px;
		cursor: pointer;
		transition: background 0.13s, color 0.13s;
	}
	.row span {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.row :global(svg) {
		flex: none;
		color: var(--fg-muted);
	}
	.row:hover {
		background: color-mix(in srgb, var(--fg) 6%, transparent);
	}
	.row:hover :global(svg) {
		color: var(--fg);
	}
	.row.active {
		background: color-mix(in srgb, var(--accent) 16%, transparent);
		color: var(--accent);
	}
	.row.active :global(svg) {
		color: var(--accent);
	}
	.row.action span {
		color: var(--fg-strong);
	}
	.row.section {
		margin-top: 4px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.convs {
		display: flex;
		flex-direction: column;
		margin: 2px 0 6px;
		padding-left: 6px;
		border-left: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
		margin-left: 16px;
	}
	.conv {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 7px 8px;
		border-radius: 8px;
		cursor: pointer;
	}
	.conv :global(svg) {
		flex: none;
		color: var(--fg-muted);
	}
	.conv:hover {
		background: color-mix(in srgb, var(--fg) 6%, transparent);
	}
	.conv.active {
		background: color-mix(in srgb, var(--accent) 14%, transparent);
	}
	.conv.active .conv-title {
		color: var(--accent);
	}
	.conv-title {
		flex: 1;
		min-width: 0;
		font-size: 12.5px;
		color: var(--fg);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.conv-time {
		font-size: 10px;
		color: var(--fg-muted);
	}
	.conv-actions {
		display: none;
		gap: 1px;
	}
	.conv:hover .conv-actions {
		display: flex;
	}
	.conv:hover .conv-time {
		display: none;
	}
	.conv-actions button {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 11px;
		padding: 2px 3px;
	}
	.conv-actions button:hover {
		color: var(--fg-strong);
	}
	.conv-edit {
		flex: 1;
		background: var(--bg);
		border: 1px solid var(--accent);
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 12.5px;
		padding: 5px 7px;
		border-radius: 7px;
		outline: none;
	}
	.empty {
		color: var(--fg-muted);
		font-size: 11.5px;
		padding: 8px 6px;
		margin: 0;
	}

	.ns-foot {
		border-top: 1px solid var(--border);
		padding: 8px;
	}
</style>
