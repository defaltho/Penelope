<script lang="ts">
	import { onMount } from 'svelte';
	import { getSettings, putSettings, listModels, type AppSettings } from '$lib/api';

	let settings = $state<AppSettings | null>(null);
	let models = $state<string[]>([]);
	let saved = $state(false);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			[settings, models] = await Promise.all([
				getSettings(),
				listModels().then((m) => m.filter((x) => !x.includes('embed')))
			]);
		} catch (e) {
			error = 'falha a carregar definições';
		}
	});

	let saveTimer: ReturnType<typeof setTimeout> | undefined;
	function persist() {
		if (!settings) return;
		clearTimeout(saveTimer);
		saveTimer = setTimeout(async () => {
			try {
				settings = await putSettings($state.snapshot(settings!));
				saved = true;
				setTimeout(() => (saved = false), 1600);
			} catch (e) {
				error = 'falha a guardar';
			}
		}, 300);
	}
</script>

<div class="view settings">
	<div class="inner">
		<header class="head">
			<h2><span class="dot"></span>Definições</h2>
			{#if saved}<span class="saved">✓ guardado</span>{/if}
		</header>

		{#if error}
			<p class="err">{error}</p>
		{/if}

		{#if settings}
			<section class="field">
				<label for="model">Modelo de chat</label>
				<p class="hint">o modelo Ollama usado por defeito nas conversas.</p>
				<select id="model" bind:value={settings.chat_model} onchange={persist}>
					{#each models as m}<option value={m}>{m}</option>{/each}
					{#if !models.includes(settings.chat_model)}
						<option value={settings.chat_model}>{settings.chat_model}</option>
					{/if}
				</select>
			</section>

			<section class="field">
				<label for="dispatch">Endpoint de dispatch (Pipeline)</label>
				<p class="hint">webhook para onde as transações são enviadas. vazio = só guarda localmente.</p>
				<input
					id="dispatch"
					placeholder="https://…"
					bind:value={settings.dispatch_url}
					oninput={persist}
				/>
			</section>

			<section class="field toggle-field">
				<div>
					<label for="mem">Memória</label>
					<p class="hint">aprende factos sobre ti e injeta-os no contexto.</p>
				</div>
				<button
					id="mem"
					class="toggle"
					class:on={settings.memory_enabled}
					onclick={() => {
						settings!.memory_enabled = !settings!.memory_enabled;
						persist();
					}}
					aria-label="Ligar/desligar memória"><span class="knob"></span></button
				>
			</section>

			<section class="field toggle-field">
				<div>
					<label for="sk">Skills</label>
					<p class="hint">aplica as instruções ativas em cada conversa.</p>
				</div>
				<button
					id="sk"
					class="toggle"
					class:on={settings.skills_enabled}
					onclick={() => {
						settings!.skills_enabled = !settings!.skills_enabled;
						persist();
					}}
					aria-label="Ligar/desligar skills"><span class="knob"></span></button
				>
			</section>
		{:else if !error}
			<p class="hint">a carregar…</p>
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
		max-width: 620px;
		margin: 0 auto;
		padding: 28px 24px 60px;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 24px;
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
	.saved {
		font-size: 12px;
		color: var(--green);
	}
	.err {
		color: var(--red);
		font-size: 13px;
	}

	.field {
		padding: 18px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
	}
	label {
		font-size: 14px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.hint {
		font-size: 12px;
		color: var(--fg-muted);
		margin: 4px 0 10px;
	}
	select,
	input {
		width: 100%;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 13px;
		padding: 9px 12px;
		border-radius: 10px;
		outline: none;
	}
	select:focus,
	input:focus {
		border-color: var(--accent);
	}

	.toggle-field {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}
	.toggle-field .hint {
		margin-bottom: 0;
	}
	.toggle {
		flex: none;
		width: 42px;
		height: 24px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: var(--bg);
		position: relative;
		cursor: pointer;
		padding: 0;
		transition: background 0.15s, border-color 0.15s;
	}
	.toggle.on {
		background: color-mix(in srgb, var(--accent) 35%, transparent);
		border-color: var(--accent);
	}
	.knob {
		position: absolute;
		top: 1px;
		left: 1px;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: var(--fg-muted);
		transition: transform 0.15s, background 0.15s;
	}
	.toggle.on .knob {
		transform: translateX(18px);
		background: var(--accent);
	}
</style>
