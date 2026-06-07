<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { listAdventures, deleteAdventure, patchAdventure, type AdventureMeta } from '$lib/api';

	let { onContinue = (_id: string) => {} }: { onContinue?: (id: string) => void } = $props();

	let adventures = $state<AdventureMeta[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function refresh() {
		loading = true;
		try {
			adventures = await listAdventures();
			error = null;
		} catch (e) {
			error = 'falha a carregar as aventuras';
		} finally {
			loading = false;
		}
	}

	onMount(refresh);

	async function remove(a: AdventureMeta) {
		if (!confirm(`Apagar a aventura "${a.title || 'sem título'}"? Isto é irreversível.`)) return;
		try {
			await deleteAdventure(a.id);
			await refresh();
		} catch (e) {
			error = 'falha a apagar';
		}
	}

	async function rename(a: AdventureMeta) {
		const novo = prompt('Novo título:', a.title);
		if (novo == null || !novo.trim()) return;
		try {
			await patchAdventure(a.id, { title: novo.trim() });
			await refresh();
		} catch (e) {
			error = 'falha a renomear';
		}
	}

	function relTime(iso: string) {
		const t = Date.parse((iso || '').replace(' ', 'T'));
		if (isNaN(t)) return '';
		const d = (Date.now() - t) / 1000;
		if (d < 60) return 'agora';
		if (d < 3600) return `${Math.floor(d / 60)}m`;
		if (d < 86400) return `${Math.floor(d / 3600)}h`;
		return `${Math.floor(d / 86400)}d`;
	}
</script>

<div class="view adventures">
	<header class="head">
		<h2><Icon name="dice" size={18} /> Aventuras</h2>
		<p class="sub">as tuas histórias de AI Dungeon. Cada uma é guardada num ficheiro próprio.</p>
	</header>

	{#if error}<p class="err">{error}</p>{/if}

	{#if loading}
		<p class="empty">a carregar…</p>
	{:else if adventures.length === 0}
		<div class="empty-state">
			<Icon name="dice" size={34} />
			<p>Ainda não tens aventuras.</p>
			<p class="hint">No chat, escreve <code>/aidungeon</code> para começar uma.</p>
		</div>
	{:else}
		<div class="grid">
			{#each adventures as a (a.id)}
				<div class="card">
					<div class="card-top">
						<span class="title">{a.title || 'Aventura sem título'}</span>
						<span class="time">{relTime(a.updated_at)}</span>
					</div>
					{#if a.scenario_summary}<p class="sum">{a.scenario_summary}</p>{/if}
					<div class="meta">
						<span>{a.turn_count} turnos</span>
						{#if a.model}<span class="model" title={a.model}>{a.model.split('/').pop()}</span>{/if}
					</div>
					<div class="actions">
						<button class="primary" onclick={() => onContinue(a.id)}>
							<Icon name="play" size={13} /> Continuar
						</button>
						<button onclick={() => rename(a)} title="Renomear" aria-label="Renomear"><Icon name="file-text" size={14} /></button>
						<button class="danger" onclick={() => remove(a)} title="Apagar" aria-label="Apagar"><Icon name="x" size={14} /></button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		overflow-y: auto;
		padding: 26px 28px;
		font-family: var(--font-ui);
	}
	.head h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0;
		font-size: 19px;
		color: var(--fg-strong);
	}
	.head h2 :global(svg) {
		color: var(--accent);
	}
	.sub {
		margin: 4px 0 18px;
		font-size: 13px;
		color: var(--fg-muted);
	}
	.err {
		color: var(--red);
		font-size: 13px;
	}
	.empty,
	.empty-state {
		color: var(--fg-muted);
		text-align: center;
		padding: 40px 0;
	}
	.empty-state :global(svg) {
		color: color-mix(in srgb, var(--accent) 60%, transparent);
		margin-bottom: 10px;
	}
	.empty-state p {
		margin: 4px 0;
		font-size: 14px;
	}
	.empty-state .hint {
		font-size: 12.5px;
	}
	code {
		font-family: var(--font-body);
		background: color-mix(in srgb, var(--fg) 9%, transparent);
		padding: 1px 6px;
		border-radius: 6px;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: 14px;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 14px 15px;
		background: color-mix(in srgb, var(--panel) 60%, transparent);
		border: 1px solid var(--border);
		border-radius: 13px;
	}
	.card-top {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 8px;
	}
	.title {
		font-size: 14.5px;
		font-weight: 700;
		color: var(--fg-strong);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.time {
		flex: none;
		font-size: 11px;
		color: var(--fg-muted);
	}
	.sum {
		margin: 0;
		font-size: 12px;
		color: var(--fg-muted);
		line-height: 1.45;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
	}
	.meta {
		display: flex;
		gap: 10px;
		font-size: 11px;
		color: var(--fg-muted);
		align-items: center;
	}
	.meta .model {
		max-width: 140px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		opacity: 0.8;
	}
	.actions {
		display: flex;
		gap: 6px;
		margin-top: 2px;
	}
	.actions button {
		display: inline-grid;
		grid-auto-flow: column;
		place-items: center;
		gap: 5px;
		height: 30px;
		min-width: 30px;
		padding: 0 9px;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 9px;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		transition: color 0.13s, border-color 0.13s, background 0.13s;
	}
	.actions button.primary {
		flex: 1;
		color: var(--accent);
	}
	.actions button:hover {
		color: var(--accent);
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.actions button.danger:hover {
		color: #ffd9d4;
		border-color: var(--red);
		background: color-mix(in srgb, var(--red) 16%, transparent);
	}
</style>
