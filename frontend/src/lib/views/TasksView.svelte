<script lang="ts">
	import { onMount } from 'svelte';
	import { listTasks, createTask, updateTask, deleteTask, type Task } from '$lib/api';

	let tasks = $state<Task[]>([]);
	let loading = $state(true);
	let newText = $state('');

	const pending = $derived(tasks.filter((t) => !t.done));
	const done = $derived(tasks.filter((t) => t.done));

	onMount(load);

	async function load() {
		loading = true;
		try {
			tasks = await listTasks();
		} finally {
			loading = false;
		}
	}

	async function add() {
		const text = newText.trim();
		if (!text) return;
		newText = '';
		await createTask(text);
		await load();
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter') add();
	}

	async function toggle(t: Task) {
		const done = t.done ? 0 : 1;
		t.done = done;
		await updateTask(t.id, { done: !!done });
		await load();
	}
	async function remove(t: Task) {
		await deleteTask(t.id);
		tasks = tasks.filter((x) => x.id !== t.id);
	}
</script>

<div class="view tasks">
	<div class="inner">
		<header class="head">
			<h2><span class="dot"></span>Tarefas <span class="count">{pending.length}</span></h2>
		</header>

		<div class="add-row">
			<input
				class="add-in"
				placeholder="adicionar tarefa…"
				bind:value={newText}
				onkeydown={onKey}
			/>
			<button class="add-btn" onclick={add} disabled={!newText.trim()}>+</button>
		</div>

		<div class="list">
			{#if loading}
				<p class="muted">a carregar…</p>
			{:else if tasks.length === 0}
				<p class="muted">sem tarefas. adiciona a primeira acima.</p>
			{/if}

			{#each pending as t (t.id)}
				<div class="task">
					<button class="check" onclick={() => toggle(t)} aria-label="Concluir"></button>
					<span class="t-text">{t.text}</span>
					<button class="del" onclick={() => remove(t)} aria-label="Apagar">🗑</button>
				</div>
			{/each}

			{#if done.length}
				<div class="done-label">concluídas ({done.length})</div>
				{#each done as t (t.id)}
					<div class="task is-done">
						<button class="check on" onclick={() => toggle(t)} aria-label="Reabrir">✓</button>
						<span class="t-text">{t.text}</span>
						<button class="del" onclick={() => remove(t)} aria-label="Apagar">🗑</button>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		overflow-y: auto;
	}
	.inner {
		max-width: 680px;
		margin: 0 auto;
		padding: 28px 24px 60px;
	}
	.head h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0 0 18px;
		font-size: 18px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.head .dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent);
	}
	.count {
		font-size: 13px;
		font-weight: 400;
		color: var(--fg-muted);
	}

	.add-row {
		display: flex;
		gap: 8px;
		margin-bottom: 20px;
	}
	.add-in {
		flex: 1;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14px;
		padding: 10px 14px;
		border-radius: 11px;
		outline: none;
	}
	.add-in:focus {
		border-color: var(--accent);
	}
	.add-btn {
		width: 42px;
		flex: none;
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font-size: 20px;
		border-radius: 11px;
		cursor: pointer;
	}
	.add-btn:disabled {
		opacity: 0.35;
		cursor: default;
	}

	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		margin: 28px 0;
	}
	.task {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 11px 12px;
		border: 1px solid var(--border);
		border-radius: 11px;
		margin-bottom: 8px;
		background: color-mix(in srgb, var(--panel) 60%, transparent);
	}
	.task.is-done {
		opacity: 0.55;
	}
	.check {
		width: 20px;
		height: 20px;
		flex: none;
		border-radius: 6px;
		border: 1.5px solid var(--fg-muted);
		background: transparent;
		color: var(--panel-2);
		font-size: 12px;
		line-height: 1;
		cursor: pointer;
		display: grid;
		place-items: center;
		transition: background 0.14s, border-color 0.14s;
	}
	.check:hover {
		border-color: var(--accent);
	}
	.check.on {
		background: var(--green);
		border-color: var(--green);
	}
	.t-text {
		flex: 1;
		font-family: var(--font-body);
		font-size: 14px;
		color: var(--fg-strong);
	}
	.is-done .t-text {
		text-decoration: line-through;
		color: var(--fg-muted);
	}
	.del {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 12px;
		opacity: 0;
		transition: opacity 0.12s;
	}
	.task:hover .del {
		opacity: 1;
	}
	.del:hover {
		color: var(--red);
	}
	.done-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--fg-muted);
		margin: 20px 0 10px;
	}
</style>
