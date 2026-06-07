<script lang="ts">
	import { putSettings, listModels } from '$lib/api';

	let { onDone }: { onDone: (name: string) => void } = $props();

	let step = $state(0);
	let name = $state('');
	let checking = $state(false);
	let checkResult = $state<{ qwen: boolean; embed: boolean; ok: boolean } | null>(null);

	const CMDS = ['ollama pull qwen3-vl:8b', 'ollama pull embeddinggemma'];

	async function finish() {
		try {
			await putSettings({ onboarded: true, user_name: name.trim() });
		} catch (e) {
			console.error('falha a gravar onboarding', e);
		}
		onDone(name.trim());
	}

	async function skip() {
		await finish();
	}

	async function checkConnection() {
		checking = true;
		checkResult = null;
		try {
			const models = await listModels();
			const qwen = models.some((m) => m.includes('qwen3-vl'));
			const embed = models.some((m) => m.includes('embeddinggemma'));
			checkResult = { qwen, embed, ok: qwen && embed };
		} catch (e) {
			checkResult = { qwen: false, embed: false, ok: false };
		} finally {
			checking = false;
		}
	}

	function copy(cmd: string) {
		navigator.clipboard?.writeText(cmd).catch(() => {});
	}
</script>

<div class="overlay">
	<div class="card">
		<button class="skip" onclick={skip}>ignorar</button>

		{#if step === 0}
			<div class="logo"><span class="dot"></span></div>
			<h1>Bem-vindo ao Penelope</h1>
			<p class="sub">
				O teu assistente de IA <strong>local-first</strong>: corre offline, com os teus dados na tua
				máquina. Vamos configurar em 2 passos rápidos.
			</p>
			<button class="primary" onclick={() => (step = 1)}>começar →</button>
		{:else if step === 1}
			<h1>Como te chamas?</h1>
			<p class="sub">Opcional — só para personalizar. Fica guardado localmente.</p>
			<input class="name-in" placeholder="o teu nome" bind:value={name} />
			<div class="row">
				<button class="ghost" onclick={() => (step = 2)}>saltar</button>
				<button class="primary" onclick={() => (step = 2)}>continuar →</button>
			</div>
		{:else if step === 2}
			<h1>Configurar o Ollama</h1>
			<p class="sub">
				O Penelope usa o <strong>Ollama</strong> a correr na tua máquina. Garante que está instalado e
				a correr, e descarrega o modelo base:
			</p>
			<div class="cmds">
				{#each CMDS as cmd}
					<div class="cmd">
						<code>{cmd}</code>
						<button class="copy" onclick={() => copy(cmd)} title="Copiar">⧉</button>
					</div>
				{/each}
			</div>

			<button class="check" onclick={checkConnection} disabled={checking}>
				{checking ? 'a verificar…' : 'verificar ligação'}
			</button>
			{#if checkResult}
				<div class="result">
					<div class="r-line {checkResult.qwen ? 'ok' : 'no'}">
						{checkResult.qwen ? '✓' : '✕'} qwen3-vl:8b {checkResult.qwen ? 'pronto' : 'em falta'}
					</div>
					<div class="r-line {checkResult.embed ? 'ok' : 'no'}">
						{checkResult.embed ? '✓' : '✕'} embeddinggemma {checkResult.embed ? 'pronto' : 'em falta'}
					</div>
					{#if !checkResult.ok}
						<p class="r-note">corre os comandos acima (e confirma que o Ollama está ligado), depois verifica de novo.</p>
					{/if}
				</div>
			{/if}

			<div class="row">
				<button class="ghost" onclick={() => (step = 1)}>← voltar</button>
				<button class="primary" onclick={finish}>concluir</button>
			</div>
		{/if}

		<div class="dots-nav">
			{#each [0, 1, 2] as i}
				<span class="nd" class:on={i === step}></span>
			{/each}
		</div>
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: var(--bg);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
		padding: 20px;
	}
	.card {
		position: relative;
		width: 100%;
		max-width: 460px;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 20px;
		padding: 36px 32px 24px;
		text-align: center;
		box-shadow: var(--shadow-panel);
		animation: pen-pop 0.3s cubic-bezier(0.22, 0.61, 0.36, 1);
	}
	.skip {
		position: absolute;
		top: 14px;
		right: 16px;
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 12px;
		cursor: pointer;
	}
	.skip:hover {
		color: var(--fg);
	}
	.logo {
		width: 56px;
		height: 56px;
		margin: 0 auto 20px;
		border-radius: 16px;
		display: grid;
		place-items: center;
		background: radial-gradient(circle at 50% 40%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 72%);
		border: 1px solid var(--border);
	}
	.logo .dot {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 16px var(--accent);
	}
	h1 {
		font-size: 21px;
		font-weight: 600;
		color: var(--fg-strong);
		margin: 0 0 10px;
	}
	.sub {
		font-size: 13.5px;
		color: var(--fg-muted);
		line-height: 1.5;
		margin: 0 0 22px;
		font-family: var(--font-body);
	}
	.name-in {
		width: 100%;
		background: var(--bg);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 15px;
		padding: 11px 14px;
		border-radius: 11px;
		outline: none;
		margin-bottom: 20px;
	}
	.name-in:focus {
		border-color: var(--accent);
	}
	.cmds {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-bottom: 18px;
		text-align: left;
	}
	.cmd {
		display: flex;
		align-items: center;
		gap: 8px;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 9px 12px;
	}
	.cmd code {
		flex: 1;
		font-family: var(--font-ui);
		font-size: 12.5px;
		color: var(--fg);
		overflow-x: auto;
		white-space: nowrap;
	}
	.copy {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 14px;
	}
	.copy:hover {
		color: var(--accent);
	}
	.check {
		width: 100%;
		background: transparent;
		border: 1px solid var(--accent);
		color: var(--accent);
		font-family: var(--font-ui);
		font-size: 13px;
		padding: 9px;
		border-radius: 10px;
		cursor: pointer;
		margin-bottom: 14px;
	}
	.check:disabled {
		opacity: 0.5;
	}
	.result {
		text-align: left;
		font-family: var(--font-ui);
		font-size: 12.5px;
		margin-bottom: 18px;
	}
	.r-line.ok {
		color: var(--green);
	}
	.r-line.no {
		color: var(--red);
	}
	.r-note {
		color: var(--fg-muted);
		font-size: 11.5px;
		margin: 6px 0 0;
	}
	.row {
		display: flex;
		gap: 10px;
		justify-content: center;
	}
	.primary {
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font-family: var(--font-ui);
		font-size: 13.5px;
		font-weight: 600;
		padding: 10px 22px;
		border-radius: 11px;
		cursor: pointer;
	}
	.primary:hover {
		background: var(--accent-hover);
	}
	.ghost {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 13px;
		padding: 10px 18px;
		border-radius: 11px;
		cursor: pointer;
	}
	.ghost:hover {
		color: var(--fg);
		border-color: var(--accent);
	}
	.dots-nav {
		display: flex;
		gap: 6px;
		justify-content: center;
		margin-top: 22px;
	}
	.nd {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--border);
	}
	.nd.on {
		background: var(--accent);
		width: 18px;
		border-radius: 3px;
	}
</style>
