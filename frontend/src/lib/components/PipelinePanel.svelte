<script lang="ts">
	import { pipelineExtract, pipelineDispatch, type Transaction } from '$lib/api';

	let { onClose, inline = false }: { onClose?: () => void; inline?: boolean } = $props();

	let text = $state('');
	let imageData = $state<string | null>(null);
	let tx = $state<Transaction | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let result = $state<string | null>(null);
	let fileInput: HTMLInputElement;

	const FIELDS: { key: keyof Transaction; label: string }[] = [
		{ key: 'date', label: 'data' },
		{ key: 'amount', label: 'valor' },
		{ key: 'currency', label: 'moeda' },
		{ key: 'merchant', label: 'comerciante' },
		{ key: 'category', label: 'categoria' },
		{ key: 'account', label: 'conta' },
		{ key: 'notes', label: 'notas' }
	];

	function onPickFile(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => (imageData = reader.result as string);
		reader.readAsDataURL(file);
		fileInput.value = '';
	}

	async function extract() {
		if (!text.trim() && !imageData) return;
		busy = true;
		error = null;
		result = null;
		try {
			tx = await pipelineExtract(text.trim(), imageData);
		} catch (e) {
			error = 'extração falhou (modelo a carregar? tenta de novo)';
		} finally {
			busy = false;
		}
	}

	function isLow(key: string): boolean {
		return !!tx && tx.low_confidence_fields.includes(key);
	}

	async function dispatch() {
		if (!tx) return;
		busy = true;
		error = null;
		try {
			const r = await pipelineDispatch(tx);
			result = r.detail;
		} catch (e) {
			error = 'dispatch falhou';
		} finally {
			busy = false;
		}
	}

	function reset() {
		tx = null;
		text = '';
		imageData = null;
		result = null;
		error = null;
	}
</script>

<div
	class="overlay"
	class:inline
	role="presentation"
	onclick={(e) => {
		if (!inline && e.target === e.currentTarget) onClose?.();
	}}
>
	<div class="panel" class:inline role="dialog" aria-label="Pipeline">
		<header class="panel-head">
			<h2><span class="dot"></span>Pipeline <span class="sub">estruturar transação</span></h2>
			{#if !inline}
				<button class="close" onclick={() => onClose?.()} aria-label="Fechar">×</button>
			{/if}
		</header>

		<div class="body">
			{#if !tx}
				<textarea
					class="in ta"
					placeholder="cola aqui o texto de um recibo/extrato, ou anexa uma imagem…"
					bind:value={text}
				></textarea>
				<div class="row">
					<input bind:this={fileInput} type="file" accept="image/*" onchange={onPickFile} hidden />
					<button class="ghost" onclick={() => fileInput.click()}>
						{imageData ? '✓ imagem anexada' : '+ anexar imagem'}
					</button>
					{#if imageData}
						<button class="ghost" onclick={() => (imageData = null)}>remover</button>
					{/if}
					<button
						class="primary"
						onclick={extract}
						disabled={busy || (!text.trim() && !imageData)}
					>
						{busy ? 'a extrair…' : 'extrair →'}
					</button>
				</div>
			{:else}
				<div class="conf">
					confiança: {Math.round(tx.confidence * 100)}%
					{#if tx.low_confidence_fields.length}
						<span class="warn">· confirma os campos marcados</span>
					{/if}
				</div>
				<div class="form">
					{#each FIELDS as f}
						<label class="field" class:low={isLow(f.key as string)}>
							<span class="flabel">{f.label}{isLow(f.key as string) ? ' ⚠' : ''}</span>
							<input
								class="in"
								value={(tx[f.key] ?? '') as string}
								oninput={(e) => {
									const v = (e.target as HTMLInputElement).value;
									(tx as any)[f.key] =
										f.key === 'amount' ? (v === '' ? null : parseFloat(v)) : v || null;
								}}
							/>
						</label>
					{/each}
				</div>

				{#if result}
					<p class="ok">✓ {result}</p>
				{/if}

				<div class="row end">
					<button class="ghost" onclick={reset}>recomeçar</button>
					<button class="primary" onclick={dispatch} disabled={busy}>
						{busy ? '…' : 'despachar'}
					</button>
				</div>
			{/if}

			{#if error}
				<p class="err">{error}</p>
			{/if}
		</div>
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, #000 55%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 50;
		padding: 20px;
	}
	.panel {
		width: 100%;
		max-width: 540px;
		max-height: 84dvh;
		display: flex;
		flex-direction: column;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
	}

	.overlay.inline {
		position: static;
		inset: auto;
		flex: 1;
		min-width: 0;
		padding: 0;
		background: transparent;
		backdrop-filter: none;
		-webkit-backdrop-filter: none;
		animation: none;
	}
	.panel.inline {
		flex: 1;
		max-width: none;
		max-height: none;
		height: 100dvh;
		border: none;
		border-radius: 0;
		box-shadow: none;
		animation: none;
	}

	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 18px;
		border-bottom: 1px solid var(--border);
	}
	.panel-head h2 {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.panel-head .dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent);
	}
	.sub {
		color: var(--fg-muted);
		font-size: 11px;
		font-weight: 400;
	}
	.close {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
	}
	.close:hover {
		color: var(--fg-strong);
	}

	.body {
		flex: 1;
		overflow-y: auto;
		padding: 16px 18px;
	}

	.in {
		width: 100%;
		background: var(--bg);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 13.5px;
		padding: 8px 11px;
		border-radius: 9px;
		outline: none;
	}
	.in:focus {
		border-color: var(--accent);
	}
	.ta {
		resize: vertical;
		min-height: 120px;
		line-height: 1.45;
		margin-bottom: 12px;
	}

	.row {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}
	.row.end {
		justify-content: flex-end;
		margin-top: 16px;
	}
	.ghost {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font: inherit;
		font-size: 12.5px;
		padding: 7px 12px;
		border-radius: 9px;
		cursor: pointer;
	}
	.ghost:hover {
		color: var(--fg);
		border-color: var(--accent);
	}
	.primary {
		margin-left: auto;
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		padding: 8px 16px;
		border-radius: 9px;
		cursor: pointer;
	}
	.row.end .primary {
		margin-left: 0;
	}
	.primary:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.conf {
		font-size: 12px;
		color: var(--fg-muted);
		margin-bottom: 12px;
	}
	.warn {
		color: var(--warn, #f0ad4e);
	}
	.form {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.flabel {
		font-size: 11px;
		text-transform: lowercase;
		color: var(--fg-muted);
	}
	.field.low .flabel {
		color: var(--warn, #f0ad4e);
	}
	.field.low .in {
		border-color: var(--warn, #f0ad4e);
	}

	.ok {
		color: var(--green);
		font-size: 13px;
		margin: 14px 0 0;
	}
	.err {
		color: var(--red);
		font-size: 13px;
		margin: 12px 0 0;
	}
</style>
