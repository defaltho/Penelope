<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getSettings,
		putSettings,
		listModels,
		exportData,
		importData,
		wipeData,
		type AppSettings
	} from '$lib/api';
	import { downloadJson, pickJsonFile } from '$lib/io';
	import { THEMES, setTheme, loadTheme, applyAnimation } from '$lib/theme';

	const WIPES = [
		{ id: 'chats', label: 'Apagar conversas', desc: 'todas as sessões e mensagens.' },
		{ id: 'memory', label: 'Apagar memória', desc: 'todos os factos aprendidos.' },
		{ id: 'skills', label: 'Apagar skills', desc: 'todas as instruções guardadas.' },
		{ id: 'notes', label: 'Apagar notas', desc: 'todas as notas.' },
		{ id: 'tasks', label: 'Apagar tarefas', desc: 'todas as tarefas.' },
		{ id: 'gallery', label: 'Apagar galeria', desc: 'todas as imagens (ficheiros em disco).' }
	];
	let wipeMsg = $state('');

	async function doExport() {
		try {
			downloadJson('penelope-backup.json', await exportData());
		} catch (e) {
			console.error('export falhou', e);
		}
	}
	async function doImport() {
		try {
			const data = await pickJsonFile();
			const r = await importData(data);
			alert(
				`Importado: ${r.added.facts} factos, ${r.added.skills} skills, ${r.added.notes} notas, ${r.added.tasks} tarefas.`
			);
		} catch (e) {
			alert('importação falhou: ficheiro inválido?');
		}
	}
	async function doWipe(target: string, label: string) {
		if (!confirm(`${label}? Isto é IRREVERSÍVEL.`)) return;
		if (!confirm('Tens a certeza? Confirma novamente.')) return;
		try {
			await wipeData(target);
			wipeMsg = `✓ ${label.toLowerCase()} concluído`;
			setTimeout(() => (wipeMsg = ''), 2500);
		} catch (e) {
			wipeMsg = 'falhou';
		}
	}

	let curTheme = $state(loadTheme());
	const themeEntries = Object.entries(THEMES);

	function pickTheme(name: string) {
		curTheme = name;
		setTheme(name);
		applyAnimation(name, settings?.ui_anim ?? true);
	}
	function toggleAnim() {
		if (!settings) return;
		settings.ui_anim = !settings.ui_anim;
		applyAnimation(curTheme, settings.ui_anim);
		persist();
	}

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

			<section class="field toggle-field">
				<div>
					<label for="memrev">Rever memórias antes de gravar</label>
					<p class="hint">
						os factos extraídos ficam pendentes para tu aprovares na aba Memória (em vez de gravar
						automaticamente).
					</p>
				</div>
				<button
					id="memrev"
					class="toggle"
					class:on={settings.memory_review}
					onclick={() => {
						settings!.memory_review = !settings!.memory_review;
						persist();
					}}
					aria-label="Rever memórias"><span class="knob"></span></button
				>
			</section>

			<section class="field toggle-field">
				<div>
					<label for="skauto">Auto-aprender skills</label>
					<p class="hint">
						o modelo deteta procedimentos repetidos e propõe-nos como skills para aprovares.
					</p>
				</div>
				<button
					id="skauto"
					class="toggle"
					class:on={settings.skills_auto}
					onclick={() => {
						settings!.skills_auto = !settings!.skills_auto;
						persist();
					}}
					aria-label="Auto-aprender skills"><span class="knob"></span></button
				>
			</section>

			<h3 class="section-title">Geração</h3>

			<section class="field">
				<label for="temp">Temperatura <span class="val">{settings.temperature.toFixed(2)}</span></label>
				<p class="hint">criatividade: 0 = preciso/determinístico, 2 = muito criativo.</p>
				<input
					id="temp"
					type="range"
					min="0"
					max="2"
					step="0.05"
					bind:value={settings.temperature}
					onchange={persist}
				/>
			</section>

			<section class="field">
				<label for="ctx">Janela de contexto (num_ctx)</label>
				<p class="hint">quantos tokens de história o modelo considera (mais = mais memória, mais RAM).</p>
				<input id="ctx" type="number" min="512" max="32768" step="512" bind:value={settings.num_ctx} onchange={persist} />
			</section>

			<section class="field">
				<label for="maxtok">Máximo de tokens na resposta</label>
				<p class="hint">limite de comprimento da resposta. 0 = sem limite (default do modelo).</p>
				<input id="maxtok" type="number" min="0" max="8192" step="64" bind:value={settings.max_tokens} onchange={persist} />
			</section>

			<section class="field">
				<label for="sysx">Instrução de sistema (persona)</label>
				<p class="hint">texto adicionado ao início de cada conversa (ex.: "Sê sempre formal e conciso").</p>
				<textarea id="sysx" rows="3" bind:value={settings.system_extra} oninput={persist}></textarea>
			</section>

			<h3 class="section-title">Privacidade e rede</h3>

			<section class="field toggle-field danger-field">
				<div>
					<label for="net">Acesso à internet</label>
					<p class="hint">
						<strong>desligado por defeito.</strong> Quando ligado, permite que ações como o dispatch
						façam pedidos de saída. O Penelope é local-first: o modelo (Ollama) corre sempre offline.
					</p>
				</div>
				<button
					id="net"
					class="toggle"
					class:on={settings.internet_enabled}
					onclick={() => {
						settings!.internet_enabled = !settings!.internet_enabled;
						persist();
					}}
					aria-label="Ligar/desligar acesso à internet"><span class="knob"></span></button
				>
			</section>

			<h3 class="section-title">Aparência</h3>

			<section class="field toggle-field">
				<div>
					<label for="anim">Animações de fundo</label>
					<p class="hint">efeitos subtis no fundo de alguns temas (respeita reduzir-movimento).</p>
				</div>
				<button
					id="anim"
					class="toggle"
					class:on={settings.ui_anim}
					onclick={toggleAnim}
					aria-label="Animações de fundo"><span class="knob"></span></button
				>
			</section>

			<section class="field">
				<span class="field-label">Tema</span>
				<p class="hint">escolhe a paleta. aplica-se de imediato e fica guardada.</p>
				<div class="theme-grid">
					{#each themeEntries as [name, t] (name)}
						<button
							class="swatch"
							class:active={name === curTheme}
							onclick={() => pickTheme(name)}
							style="--s-bg:{t.bg}; --s-fg:{t.fg}; --s-panel:{t.panel}; --s-accent:{t.accent}; --s-border:{t.border}"
							title={name}
						>
							<div class="preview">
								<span class="p-panel"></span>
								<span class="p-accent"></span>
								<span class="p-fg"></span>
							</div>
							<span class="s-name">{name}</span>
						</button>
					{/each}
				</div>
			</section>

			<section class="field toggle-field">
				<div>
					<label for="uiw">Ecrã de boas-vindas</label>
					<p class="hint">mostra o logo e a dica no chat vazio.</p>
				</div>
				<button id="uiw" class="toggle" class:on={settings.ui_welcome} onclick={() => { settings!.ui_welcome = !settings!.ui_welcome; persist(); }} aria-label="Boas-vindas"><span class="knob"></span></button>
			</section>
			<section class="field toggle-field">
				<div>
					<label for="uit">Mostrar raciocínio</label>
					<p class="hint">mostra os blocos &lt;think&gt; do modelo em vez de os ocultar.</p>
				</div>
				<button id="uit" class="toggle" class:on={settings.ui_thinking} onclick={() => { settings!.ui_thinking = !settings!.ui_thinking; persist(); }} aria-label="Raciocínio"><span class="knob"></span></button>
			</section>
			<section class="field toggle-field">
				<div>
					<label for="uie">Sem emojis</label>
					<p class="hint">remove emojis das respostas da IA.</p>
				</div>
				<button id="uie" class="toggle" class:on={settings.ui_text_emojis} onclick={() => { settings!.ui_text_emojis = !settings!.ui_text_emojis; persist(); }} aria-label="Sem emojis"><span class="knob"></span></button>
			</section>

			<h3 class="section-title">Dados</h3>

			<section class="field">
				<span class="field-label">Cópia de segurança</span>
				<p class="hint">exporta/importa memória, skills, notas e tarefas como JSON.</p>
				<div class="data-row">
					<button class="data-btn" onclick={doExport}>exportar</button>
					<button class="data-btn" onclick={doImport}>importar</button>
				</div>
			</section>

			<section class="field danger-zone">
				<span class="field-label danger">Zona de perigo</span>
				<p class="hint">irreversível. cada ação apaga só a sua categoria.</p>
				{#if wipeMsg}<p class="wipe-msg">{wipeMsg}</p>{/if}
				{#each WIPES as w}
					<div class="wipe-row">
						<div>
							<strong>{w.label}</strong>
							<span class="wipe-desc">{w.desc}</span>
						</div>
						<button class="wipe-btn" onclick={() => doWipe(w.id, w.label)}>apagar</button>
					</div>
				{/each}
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
	.section-title {
		margin: 28px 0 4px;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.6px;
		color: var(--accent);
	}
	.val {
		color: var(--fg-muted);
		font-weight: 400;
		font-size: 12px;
	}
	textarea {
		width: 100%;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 13px;
		padding: 9px 12px;
		border-radius: 10px;
		outline: none;
		resize: vertical;
	}
	textarea:focus {
		border-color: var(--accent);
	}
	input[type='range'] {
		width: 100%;
		accent-color: var(--accent);
		padding: 0;
	}
	.danger-field {
		border-bottom: none;
		border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
		border-radius: 12px;
		padding: 14px;
		background: color-mix(in srgb, var(--accent) 5%, transparent);
	}

	.field-label {
		display: block;
		font-size: 14px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.field-label.danger {
		color: var(--red);
	}
	.data-row {
		display: flex;
		gap: 10px;
		margin-top: 4px;
	}
	.data-btn {
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font: inherit;
		font-size: 13px;
		padding: 8px 18px;
		border-radius: 10px;
		cursor: pointer;
	}
	.data-btn:hover {
		border-color: var(--accent);
		color: var(--accent);
	}
	.danger-zone {
		border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
		border-radius: 12px;
		padding: 14px;
		background: color-mix(in srgb, var(--red) 5%, transparent);
	}
	.wipe-msg {
		color: var(--green);
		font-size: 12px;
		margin: 4px 0;
	}
	.wipe-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 9px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
	}
	.wipe-row:last-child {
		border-bottom: none;
	}
	.wipe-row strong {
		font-size: 13px;
		color: var(--fg-strong);
		font-weight: 600;
	}
	.wipe-desc {
		display: block;
		font-size: 11.5px;
		color: var(--fg-muted);
	}
	.wipe-btn {
		flex: none;
		background: transparent;
		border: 1px solid color-mix(in srgb, var(--red) 50%, transparent);
		color: var(--red);
		font: inherit;
		font-size: 12.5px;
		padding: 6px 14px;
		border-radius: 9px;
		cursor: pointer;
	}
	.wipe-btn:hover {
		background: color-mix(in srgb, var(--red) 18%, transparent);
	}
	.theme-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
		gap: 10px;
		margin-top: 4px;
	}
	.swatch {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 7px;
		border-radius: 11px;
		border: 1px solid var(--border);
		background: var(--s-bg);
		cursor: pointer;
		transition: transform 0.12s;
	}
	.swatch:hover {
		transform: translateY(-2px);
	}
	.swatch.active {
		border-color: var(--s-accent);
		box-shadow: 0 0 0 2px var(--s-accent);
	}
	.preview {
		display: flex;
		gap: 4px;
		align-items: center;
		height: 30px;
		padding: 0 4px;
		border-radius: 7px;
		background: var(--s-panel);
		border: 1px solid var(--s-border);
	}
	.p-panel {
		width: 22px;
		height: 14px;
		border-radius: 4px;
		background: var(--s-bg);
		border: 1px solid var(--s-border);
	}
	.p-accent {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--s-accent);
	}
	.p-fg {
		flex: 1;
		height: 4px;
		border-radius: 2px;
		background: var(--s-fg);
	}
	.s-name {
		font-family: var(--font-ui);
		font-size: 10.5px;
		color: var(--s-fg);
		text-align: center;
		text-transform: lowercase;
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
