<script lang="ts">
	import { onMount } from 'svelte';
	import NavSidebar from '$lib/components/NavSidebar.svelte';
	import SearchPalette from '$lib/components/SearchPalette.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import ChatView from '$lib/views/ChatView.svelte';
	import MemoryPanel from '$lib/components/MemoryPanel.svelte';
	import GalleryPanel from '$lib/components/GalleryPanel.svelte';
	import SkillsPanel from '$lib/components/SkillsPanel.svelte';
	import AgentsView from '$lib/views/AgentsView.svelte';
	import WorkspaceView from '$lib/views/WorkspaceView.svelte';
	import CompareView from '$lib/views/CompareView.svelte';
	import DocumentsView from '$lib/views/DocumentsView.svelte';
	import SettingsView from '$lib/views/SettingsView.svelte';
	import Onboarding from '$lib/components/Onboarding.svelte';
	import { applyTheme, loadTheme, applyAnimation } from '$lib/theme';
	import {
		listConversations,
		renameConversation,
		deleteConversation,
		getSettings,
		type ConversationSummary
	} from '$lib/api';

	let activeView = $state('chat');
	let sidebarOpen = $state(true);
	let showSearch = $state(false);
	let showOnboarding = $state(false);
	let userName = $state('');

	let conversations = $state<ConversationSummary[]>([]);
	let chatConvoId = $state<number | null>(null); // ligado ao ChatView
	let openConvoId = $state<number | null>(null); // sinal para abrir
	let newSignal = $state(0); // sinal para nova conversa
	onMount(() => {
		refreshConversations();
		const th = loadTheme();
		applyTheme(th);
		applyAnimation(th, true);
		getSettings()
			.then((s) => {
				userName = s.user_name || '';
				applyAnimation(th, s.ui_anim);
				if (!s.onboarded) showOnboarding = true;
			})
			.catch(() => {});
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

</script>

<div class="shell">
	{#if sidebarOpen && activeView !== 'settings'}
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
			onOpenSearch={() => (showSearch = true)}
			{userName}
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
		{:else if activeView === 'workspace'}
			<WorkspaceView />
		{:else if activeView === 'gallery'}
			<GalleryPanel inline onOpenConversation={selectConvo} />
		{:else if activeView === 'documents'}
			<DocumentsView />
		{:else if activeView === 'agents'}
			<AgentsView />
		{:else if activeView === 'compare'}
			<CompareView />
		{:else if activeView === 'settings'}
			<SettingsView onClose={() => (activeView = 'chat')} />
		{/if}
	</div>
</div>

{#if showSearch}
	<SearchPalette onClose={() => (showSearch = false)} onOpen={selectConvo} />
{/if}

{#if showOnboarding}
	<Onboarding
		onDone={(n) => {
			userName = n;
			showOnboarding = false;
		}}
	/>
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
