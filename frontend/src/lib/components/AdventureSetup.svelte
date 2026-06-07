<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';
	import { listAdventures, type AdventureMeta } from '$lib/api';

	let {
		onNew,
		onContinue,
		onClose
	}: {
		onNew: () => void;
		onContinue: (id: string) => void;
		onClose: () => void;
	} = $props();

	let screen = $state<'choice' | 'continue'>('choice');
	let adventures = $state<AdventureMeta[]>([]);
	let loading = $state(false);

	async function openContinue() {
		screen = 'continue';
		loading = true;
		try {
			adventures = await listAdventures();
		} catch (e) {
			adventures = [];
		} finally {
			loading = false;
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

	onMount(() => {
		const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});
</script>

<div
	class="overlay"
	role="button"
	tabindex="-1"
	onclick={onClose}
	onkeydown={(e) => e.key === 'Enter' && onClose()}
>
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal" onclick={(e) => e.stopPropagation()}>
		<header>
			<h3><Icon name="dice" size={17} /> AI Dungeon</h3>
			<button class="x" onclick={onClose} aria-label="Fechar"><Icon name="x" size={17} /></button>
		</header>

		{#if screen === 'choice'}
			<p class="lead">Uma aventura de texto guiada por um Mestre-de-Jogo. Como queres começar?</p>
			<div class="choices">
				<button class="choice" onclick={onNew}>
					<Icon name="plus" size={20} />
					<span class="ct">Nova aventura</span>
					<span class="cd">Respondes a duas perguntas e o MJ tece o mundo.</span>
				</button>
				<button class="choice" onclick={openContinue}>
					<Icon name="play" size={20} />
					<span class="ct">Continuar</span>
					<span class="cd">Retoma uma história guardada.</span>
				</button>
			</div>
		{:else}
			<button class="back" onclick={() => (screen = 'choice')}>← voltar</button>
			{#if loading}
				<p class="empty">a carregar…</p>
			{:else if adventures.length === 0}
				<p class="empty">ainda não há aventuras guardadas.</p>
			{:else}
				<div class="list">
					{#each adventures as a (a.id)}
						<button class="adv" onclick={() => onContinue(a.id)}>
							<span class="adv-title">{a.title || 'Aventura sem título'}</span>
							<span class="adv-meta">{a.turn_count} turnos · {relTime(a.updated_at)}</span>
							{#if a.scenario_summary}<span class="adv-sum">{a.scenario_summary}</span>{/if}
						</button>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 60;
		display: grid;
		place-items: center;
		background: color-mix(in srgb, #000 55%, transparent);
		backdrop-filter: blur(3px);
		padding: 20px;
		border: none;
	}
	.modal {
		width: 100%;
		max-width: 460px;
		max-height: 80vh;
		overflow-y: auto;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 16px;
		box-shadow: var(--shadow-panel);
		padding: 16px 18px 18px;
		animation: pen-pop 0.22s cubic-bezier(0.22, 0.61, 0.36, 1) both;
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8px;
	}
	header h3 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0;
		font-size: 16px;
		color: var(--fg-strong);
	}
	header h3 :global(svg) {
		color: var(--accent);
	}
	.x {
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		border: none;
		border-radius: 8px;
		background: transparent;
		color: var(--fg-muted);
		cursor: pointer;
	}
	.x:hover {
		color: var(--fg-strong);
		background: color-mix(in srgb, var(--fg) 8%, transparent);
	}
	.lead {
		margin: 0 0 14px;
		font-size: 13px;
		color: var(--fg-muted);
		line-height: 1.5;
	}
	.choices {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 10px;
	}
	.choice {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 6px;
		text-align: left;
		padding: 14px;
		background: color-mix(in srgb, var(--panel-2) 60%, transparent);
		border: 1px solid var(--border);
		border-radius: 12px;
		cursor: pointer;
		color: var(--fg);
		transition: border-color 0.14s, background 0.14s;
	}
	.choice:hover {
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.choice :global(svg) {
		color: var(--accent);
	}
	.ct {
		font-size: 14px;
		font-weight: 700;
		color: var(--fg-strong);
	}
	.cd {
		font-size: 11.5px;
		color: var(--fg-muted);
		line-height: 1.4;
	}
	.back {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 12.5px;
		cursor: pointer;
		padding: 2px 0 10px;
	}
	.back:hover {
		color: var(--accent);
	}
	.empty {
		color: var(--fg-muted);
		font-size: 13px;
		padding: 16px 4px;
		text-align: center;
	}
	.list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.adv {
		display: flex;
		flex-direction: column;
		gap: 3px;
		text-align: left;
		padding: 11px 13px;
		background: color-mix(in srgb, var(--panel-2) 55%, transparent);
		border: 1px solid var(--border);
		border-radius: 11px;
		cursor: pointer;
		transition: border-color 0.14s, background 0.14s;
	}
	.adv:hover {
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 9%, transparent);
	}
	.adv-title {
		font-size: 13.5px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.adv-meta {
		font-size: 11px;
		color: var(--fg-muted);
	}
	.adv-sum {
		font-size: 11.5px;
		color: var(--fg-muted);
		line-height: 1.4;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}
</style>
