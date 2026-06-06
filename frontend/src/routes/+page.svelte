<script lang="ts">
	import { onMount } from 'svelte';
	import NavSidebar from '$lib/components/NavSidebar.svelte';
	import SearchPalette from '$lib/components/SearchPalette.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import ChatView from '$lib/views/ChatView.svelte';
	import MemoryPanel from '$lib/components/MemoryPanel.svelte';
	import GalleryPanel from '$lib/components/GalleryPanel.svelte';
	import SkillsPanel from '$lib/components/SkillsPanel.svelte';
	import PipelinePanel from '$lib/components/PipelinePanel.svelte';
	import NotesView from '$lib/views/NotesView.svelte';
	import TasksView from '$lib/views/TasksView.svelte';
	import CompareView from '$lib/views/CompareView.svelte';
	import SettingsView from '$lib/views/SettingsView.svelte';
	import {
		listConversations,
		renameConversation,
		deleteConversation,
		type ConversationSummary
	} from '$lib/api';

	let activeView = $state('chat');
	let sidebarOpen = $state(true);
	let showSearch = $state(false);

	let conversations = $state<ConversationSummary[]>([]);
	let chatConvoId = $state<number | null>(null); // ligado ao ChatView
	let openConvoId = $state<number | null>(null); // sinal para abrir
	let newSignal = $state(0); // sinal para nova conversa

	onMount(() => {
		refreshConversations();
		themeIdx = loadThemeIndex();
		applyTheme(themeIdx);
		const onKey = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
				e.preventDefault();
				showSearch = true;
			}
		};
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});

	async function refreshConversations() {
		try {
			conversations = await listConversations();
		} catch (e) {
			console.error('falha a listar conversas', e);
		}
	}

	function selectConvo(id: number) {
		openConvoId = id;
		activeView = 'chat';
	}
	function newChat() {
		newSignal += 1;
		activeView = 'chat';
	}
	async function renameConvo(id: number, title: string) {
		await renameConversation(id, title);
		await refreshConversations();
	}
	async function deleteConvo(id: number) {
		await deleteConversation(id);
		if (id === chatConvoId) newChat();
		await refreshConversations();
	}

	// ---- Tema (cicla a cor de acento; persiste em localStorage) ----
	const THEMES = [
		{ accent: '#00aaff', hover: '#66c7ff' },
		{ accent: '#50fa7b', hover: '#7dffa0' },
		{ accent: '#e06c75', hover: '#ff8a93' },
		{ accent: '#c678dd', hover: '#d99bee' }
	];
	function loadThemeIndex(): number {
		const v = typeof localStorage !== 'undefined' ? localStorage.getItem('pen-theme') : null;
		return v ? Number(v) % THEMES.length : 0;
	}
	function applyTheme(i: number) {
		const t = THEMES[i];
		document.documentElement.style.setProperty('--accent', t.accent);
		document.documentElement.style.setProperty('--accent-hover', t.hover);
	}
	let themeIdx = $state(0);
	function cycleTheme() {
		themeIdx = (themeIdx + 1) % THEMES.length;
		applyTheme(themeIdx);
		try {
			localStorage.setItem('pen-theme', String(themeIdx));
		} catch {}
	}
</script>

<div class="shell">
	{#if sidebarOpen}
		<NavSidebar
			{activeView}
			onSelectView={(v) => (activeView = v)}
			{conversations}
			activeConvoId={chatConvoId}
			onSelectConvo={selectConvo}
			onNewChat={newChat}
			onRenameConvo={renameConvo}
			onDeleteConvo={deleteConvo}
			onToggle={() => (sidebarOpen = false)}
			onCycleTheme={cycleTheme}
			onOpenSearch={() => (showSearch = true)}
		/>
	{/if}

	<div class="content">
		{#if !sidebarOpen}
			<button
				class="reopen"
				onclick={() => (sidebarOpen = true)}
				title="Mostrar barra lateral"
				aria-label="Mostrar barra lateral"
			>
				<Icon name="menu" size={18} />
			</button>
		{/if}

		<div class="chat-host" class:hidden={activeView !== 'chat'}>
			<ChatView
				{openConvoId}
				{newSignal}
				bind:conversationId={chatConvoId}
				onConversationsChanged={refreshConversations}
			/>
		</div>

		{#if activeView === 'memory'}
			<MemoryPanel inline />
		{:else if activeView === 'skills'}
			<SkillsPanel inline />
		{:else if activeView === 'notes'}
			<NotesView />
		{:else if activeView === 'tasks'}
			<TasksView />
		{:else if activeView === 'gallery'}
			<GalleryPanel inline onOpenConversation={selectConvo} />
		{:else if activeView === 'pipeline'}
			<PipelinePanel inline />
		{:else if activeView === 'compare'}
			<CompareView />
		{:else if activeView === 'settings'}
			<SettingsView />
		{/if}
	</div>
</div>

{#if showSearch}
	<SearchPalette onClose={() => (showSearch = false)} onOpen={selectConvo} />
{/if}

<style>
	.shell {
		display: flex;
		height: 100dvh;
	}
	.content {
		position: relative;
		flex: 1;
		min-width: 0;
		display: flex;
	}
	.chat-host {
		flex: 1;
		min-width: 0;
		display: flex;
	}
	.chat-host.hidden {
		display: none;
	}
	.reopen {
		position: absolute;
		top: 12px;
		left: 12px;
		z-index: 40;
		display: grid;
		place-items: center;
		width: 34px;
		height: 34px;
		border-radius: 9px;
		border: 1px solid var(--border);
		background: color-mix(in srgb, var(--panel) 80%, transparent);
		backdrop-filter: blur(6px);
		color: var(--fg-muted);
		cursor: pointer;
	}
	.reopen:hover {
		color: var(--accent);
		border-color: var(--accent);
	}
</style>
