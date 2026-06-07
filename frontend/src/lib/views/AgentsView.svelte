<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { agentRun, type AgentStep } from '$lib/api';

	let task = $state('');
	let busy = $state(false);
	let steps = $state<AgentStep[]>([]);
	let final = $state<string | null>(null);
	let error = $state<string | null>(null);

	const EXAMPLES = [
		'Que horas são?',
		'Cria uma nota com a minha lista de compras: leite, ovos, café.',
		'Adiciona uma tarefa: ligar ao dentista.',
		'O que sabes sobre mim?'
	];

	async function run(t?: string) {
		const text = (t ?? task).trim();
		if (!text || busy) return;
		task = text;
		busy = true;
		error = null;
		steps = [];
		final = null;
		try {
			const r = await agentRun(text);
			steps = r.steps;
			final = r.final;
		} catch (e) {
			error = 'o agente falhou (modelo a carregar? tenta de novo)';
		} finally {
			busy = false;
		}
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run();
	}
</script>

<div class="view agents">
	<div class="inner">
		<header class="head">
			<h2><Icon name="bot" size={18} /> Agents <span class="sub">dá uma tarefa, ele usa ferramentas</span></h2>
		</header>

		<div class="prompt-row">
			<textarea
				placeholder="descreve uma tarefa (Cmd/Ctrl+Enter para correr)…"
				bind:value={task}
				onkeydown={onKey}
			></textarea>
			<button class="run" onclick={() => run()} disabled={busy || !task.trim()}>
				{busy ? 'a correr…' : 'executar →'}
			</button>
		</div>

		{#if !steps.length && !busy && !final}
			<div class="examples">
				{#each EXAMPLES as ex}
					<button class="ex" onclick={() => run(ex)}>{ex}</button>
				{/each}
			</div>
		{/if}

		{#if error}<p class="err">{error}</p>{/if}

		{#if busy}
			<div class="thinking"><span class="dots"><span></span><span></span><span></span></span> o agente está a pensar…</div>
		{/if}

		{#if steps.length}
			<div class="timeline">
				{#each steps as s, i (i)}
					{#if s.tool}
						<div class="step">
							<div class="s-head">
								<span class="s-num">{i + 1}</span>
								<span class="s-tool"><Icon name="zap" size={12} /> {s.tool}</span>
							</div>
							{#if s.thought}<p class="s-thought">{s.thought}</p>{/if}
							{#if Object.keys(s.args).length}<code class="s-args">{JSON.stringify(s.args)}</code>{/if}
							{#if s.observation}<div class="s-obs">{s.observation}</div>{/if}
						</div>
					{/if}
				{/each}
			</div>
		{/if}

		{#if final}
			<div class="final">
				<div class="f-head"><Icon name="bot" size={14} /> resposta</div>
				<div class="f-body">{final}</div>
			</div>
		{/if}
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
		max-width: 760px;
		margin: 0 auto;
		padding: 26px 24px 60px;
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
	.sub {
		font-size: 12px;
		font-weight: 400;
		color: var(--fg-muted);
	}

	.prompt-row {
		display: flex;
		gap: 10px;
		align-items: stretch;
	}
	textarea {
		flex: 1;
		min-height: 58px;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14px;
		line-height: 1.45;
		padding: 11px 13px;
		border-radius: 12px;
		resize: vertical;
		outline: none;
	}
	textarea:focus {
		border-color: var(--accent);
	}
	.run {
		flex: none;
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		padding: 0 18px;
		border-radius: 12px;
		cursor: pointer;
	}
	.run:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.examples {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-top: 14px;
	}
	.ex {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-body);
		font-size: 12.5px;
		padding: 7px 12px;
		border-radius: 999px;
		cursor: pointer;
	}
	.ex:hover {
		color: var(--accent);
		border-color: var(--accent);
	}

	.err {
		color: var(--red);
		font-size: 13px;
	}
	.thinking {
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--fg-muted);
		font-size: 13px;
		margin-top: 18px;
	}

	.timeline {
		margin-top: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.step {
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 12px 14px;
		background: color-mix(in srgb, var(--panel) 50%, transparent);
	}
	.s-head {
		display: flex;
		align-items: center;
		gap: 9px;
		margin-bottom: 6px;
	}
	.s-num {
		width: 20px;
		height: 20px;
		border-radius: 50%;
		display: grid;
		place-items: center;
		background: color-mix(in srgb, var(--accent) 18%, transparent);
		color: var(--accent);
		font-size: 11px;
		font-weight: 700;
	}
	.s-tool {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-family: var(--font-ui);
		font-size: 12.5px;
		font-weight: 600;
		color: var(--accent);
	}
	.s-thought {
		margin: 4px 0;
		font-family: var(--font-body);
		font-size: 13px;
		color: var(--fg);
	}
	.s-args {
		display: block;
		font-family: var(--font-ui);
		font-size: 11.5px;
		color: var(--fg-muted);
		margin: 4px 0;
		word-break: break-all;
	}
	.s-obs {
		margin-top: 6px;
		padding: 8px 10px;
		border-left: 2px solid var(--border);
		font-family: var(--font-body);
		font-size: 12.5px;
		color: var(--fg-muted);
		background: var(--bg);
		border-radius: 0 8px 8px 0;
		white-space: pre-wrap;
	}

	.final {
		margin-top: 18px;
		border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border));
		border-radius: 14px;
		overflow: hidden;
	}
	.f-head {
		display: flex;
		align-items: center;
		gap: 7px;
		padding: 8px 14px;
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.f-body {
		padding: 14px;
		font-family: var(--font-body);
		font-size: 14.5px;
		line-height: 1.5;
		color: var(--fg-strong);
		white-space: pre-wrap;
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
