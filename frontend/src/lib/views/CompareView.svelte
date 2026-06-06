<script lang="ts">
	import { onMount } from 'svelte';
	import { listModels, compare, type CompareSide } from '$lib/api';

	let models = $state<string[]>([]);
	let modelA = $state('');
	let modelB = $state('');
	let prompt = $state('');
	let busy = $state(false);
	let left = $state<CompareSide | null>(null);
	let right = $state<CompareSide | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			// Excluir modelos de embeddings (não servem para chat/compare).
			models = (await listModels()).filter((m) => !m.includes('embed'));
			// Defaults sensatos: qwen3-vl vs um gemma, se existirem.
			modelA = models.find((m) => m.includes('qwen3-vl')) || models[0] || '';
			modelB =
				models.find((m) => m.includes('gemma') && m !== modelA) ||
				models.find((m) => m !== modelA) ||
				models[0] ||
				'';
		} catch (e) {
			error = 'falha a obter modelos do Ollama';
		}
	});

	async function run() {
		if (!prompt.trim() || !modelA || !modelB || busy) return;
		busy = true;
		error = null;
		left = null;
		right = null;
		try {
			const r = await compare(prompt.trim(), modelA, modelB);
			left = r.left;
			right = r.right;
		} catch (e) {
			error = 'comparação falhou (modelos a carregar? tenta de novo)';
		} finally {
			busy = false;
		}
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run();
	}
</script>

<div class="view compare">
	<header class="head">
		<h2><span class="dot"></span>Compare <span class="sub">dois modelos, mesmo prompt</span></h2>
	</header>

	<div class="controls">
		<div class="selects">
			<select bind:value={modelA} aria-label="Modelo A">
				{#each models as m}<option value={m}>{m}</option>{/each}
			</select>
			<span class="vs">vs</span>
			<select bind:value={modelB} aria-label="Modelo B">
				{#each models as m}<option value={m}>{m}</option>{/each}
			</select>
		</div>
		<div class="prompt-row">
			<textarea
				placeholder="escreve o prompt e Cmd/Ctrl+Enter…"
				bind:value={prompt}
				onkeydown={onKey}
			></textarea>
			<button class="run" onclick={run} disabled={busy || !prompt.trim()}>
				{busy ? 'a correr…' : 'comparar →'}
			</button>
		</div>
		{#if error}<p class="err">{error}</p>{/if}
	</div>

	<div class="panes">
		{#each [left, right] as side, i (i)}
			<div class="pane">
				<div class="pane-head">{side?.model || (i === 0 ? modelA : modelB)}</div>
				<div class="pane-body">
					{#if busy}
						<span class="dots"><span></span><span></span><span></span></span>
					{:else if side?.error}
						<p class="pane-err">{side.error}</p>
					{:else if side?.text}
						{side.text}
					{:else}
						<p class="hint">a resposta aparece aqui</p>
					{/if}
				</div>
			</div>
		{/each}
	</div>
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		display: flex;
		flex-direction: column;
	}
	.head {
		padding: 18px 24px 0;
	}
	.head h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0;
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
	.sub {
		font-size: 12px;
		font-weight: 400;
		color: var(--fg-muted);
	}

	.controls {
		padding: 16px 24px;
		border-bottom: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.selects {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	select {
		flex: 1;
		max-width: 280px;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 13px;
		padding: 8px 10px;
		border-radius: 9px;
		outline: none;
	}
	select:focus {
		border-color: var(--accent);
	}
	.vs {
		color: var(--fg-muted);
		font-size: 12px;
	}
	.prompt-row {
		display: flex;
		gap: 10px;
		align-items: stretch;
	}
	textarea {
		flex: 1;
		min-height: 54px;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14px;
		line-height: 1.45;
		padding: 10px 12px;
		border-radius: 11px;
		resize: vertical;
		outline: none;
	}
	textarea:focus {
		border-color: var(--accent);
	}
	.run {
		flex: none;
		align-self: stretch;
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		padding: 0 18px;
		border-radius: 11px;
		cursor: pointer;
	}
	.run:disabled {
		opacity: 0.4;
		cursor: default;
	}
	.err {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}

	.panes {
		flex: 1;
		display: grid;
		grid-template-columns: 1fr 1fr;
		min-height: 0;
	}
	.pane {
		display: flex;
		flex-direction: column;
		min-width: 0;
		border-right: 1px solid var(--border);
	}
	.pane:last-child {
		border-right: none;
	}
	.pane-head {
		padding: 10px 18px;
		font-size: 12px;
		font-weight: 600;
		color: var(--accent);
		border-bottom: 1px solid var(--border);
		background: var(--panel-2);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.pane-body {
		flex: 1;
		overflow-y: auto;
		padding: 18px;
		font-family: var(--font-body);
		font-size: 14px;
		line-height: 1.6;
		color: var(--fg-strong);
		white-space: pre-wrap;
	}
	.hint {
		color: var(--fg-muted);
		font-size: 13px;
	}
	.pane-err {
		color: var(--red);
		font-size: 13px;
	}

	.dots {
		display: inline-flex;
		gap: 4px;
	}
	.dots span {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		animation: blink 1.4s infinite both;
	}
	.dots span:nth-child(2) {
		animation-delay: 0.2s;
	}
	.dots span:nth-child(3) {
		animation-delay: 0.4s;
	}
	@keyframes blink {
		0%,
		80%,
		100% {
			opacity: 0.25;
		}
		40% {
			opacity: 1;
		}
	}
</style>
