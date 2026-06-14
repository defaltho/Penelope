<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import NotesView from './NotesView.svelte';
	import TasksView from './TasksView.svelte';

	let activeTab = $state<'notes' | 'tasks'>('notes');
</script>

<div class="workspace">
	<div class="tab-bar">
		<button class="tab" class:on={activeTab === 'notes'} onclick={() => (activeTab = 'notes')}>
			<Icon name="sticky-note" size={14} /> Notas
		</button>
		<button class="tab" class:on={activeTab === 'tasks'} onclick={() => (activeTab = 'tasks')}>
			<Icon name="list-checks" size={14} /> Tarefas
		</button>
	</div>
	<div class="tab-content">
		{#if activeTab === 'notes'}
			<NotesView />
		{:else}
			<TasksView />
		{/if}
	</div>
</div>

<style>
	.workspace {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		display: flex;
		flex-direction: column;
	}
	.tab-bar {
		display: flex;
		gap: 4px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--border);
		background: var(--panel-2);
		flex: none;
	}
	.tab {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 6px 14px;
		border-radius: 20px;
		border: 1px solid var(--border);
		background: transparent;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.14s, color 0.14s, border-color 0.14s;
	}
	.tab:hover {
		color: var(--fg-strong);
		border-color: var(--fg-muted);
	}
	.tab.on {
		background: color-mix(in srgb, var(--accent) 16%, transparent);
		color: var(--accent);
		border-color: var(--accent);
	}
	.tab :global(svg) {
		flex: none;
	}
	.tab-content {
		flex: 1;
		min-height: 0;
		display: flex;
	}
</style>
