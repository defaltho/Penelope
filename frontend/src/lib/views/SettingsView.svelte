<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getSettings,
		putSettings,
		listModels,
		exportData,
		importData,
		wipeData,
		listAgentTools,
		type AppSettings,
		type AgentTool
	} from '$lib/api';
	import { downloadJson, pickJsonFile } from '$lib/io';
	import { THEMES, setTheme, loadTheme, applyAnimation } from '$lib/theme';
	import Icon from '$lib/components/Icon.svelte';

	let { onClose }: { onClose?: () => void } = $props();

	let settings = $state<AppSettings | null>(null);
	let models = $state<string[]>([]);
	let saved = $state(false);
	let error = $state<string | null>(null);
	let section = $state('ia');

	const NAV = [
		{ id: 'account', icon: 'user', label: 'Conta' },
		{ id: 'ia', icon: 'brain', label: 'IA' },
		{ id: 'tools', icon: 'zap', label: 'Agent Tools' },
		{ id: 'game', icon: 'bot', label: 'AI Dungeon' },
		{ id: 'appearance', icon: 'palette', label: 'Aparência' },
		{ id: 'privacy', icon: 'eye', label: 'Privacidade' },
		{ id: 'data', icon: 'database', label: 'Dados' }
	];

	let tools = $state<AgentTool[]>([]);

	let curTheme = $state(loadTheme());
	const themeEntries = Object.entries(THEMES);

	const WIPES = [
		{ id: 'chats', label: 'Apagar conversas', desc: 'todas as sessões e mensagens.' },
		{ id: 'memory', label: 'Apagar memória', desc: 'todos os factos aprendidos.' },
		{ id: 'skills', label: 'Apagar skills', desc: 'todas as instruções guardadas.' },
		{ id: 'notes', label: 'Apagar notas', desc: 'todas as notas.' },
		{ id: 'tasks', label: 'Apagar tarefas', desc: 'todas as tarefas.' },
		{ id: 'gallery', label: 'Apagar galeria', desc: 'todas as imagens (ficheiros em disco).' }
	];
	let wipeMsg = $state('');

	onMount(async () => {
		try {
			[settings, models, tools] = await Promise.all([
				getSettings(),
				listModels().then((m) => m.filter((x) => !x.includes('embed'))),
				listAgentTools().catch(() => [])
			]);
		} catch (e) {
			error = 'falha a carregar definições';
		}
	});

	async function toggleTool(name: string) {
		const t = tools.find((x) => x.name === name);
		if (!t) return;
		t.enabled = !t.enabled;
		const disabled = tools.filter((x) => !x.enabled).map((x) => x.name);
		try {
			settings = await putSettings({ tools_disabled: JSON.stringify(disabled) } as Partial<AppSettings>);
			saved = true;
			setTimeout(() => (saved = false), 1600);
		} catch (e) {
			error = 'falha a guardar';
		}
	}

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

	function adventuresCount(): number {
		try {
			return JSON.parse(settings?.adventures || '[]').length;
		} catch {
			return 0;
		}
	}

	function toggle(key: keyof AppSettings) {
		if (!settings) return;
		(settings as any)[key] = !(settings as any)[key];
		persist();
	}

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
</script>

<div class="view settings">
	<header class="head">
		<div class="head-top">
			<h2><Icon name="settings" size={18} /> Definições {#if saved}<span class="saved">✓ guardado</span>{/if}</h2>
			{#if onClose}
				<button class="close-btn" onclick={onClose} title="Fechar" aria-label="Fechar">
					<Icon name="x" size={18} />
				</button>
			{/if}
		</div>
		<p class="sub">configura o Penelope: modelo, aparência, privacidade e dados.</p>
	</header>

	{#if error}
		<p class="err">{error}</p>
	{/if}

	<div class="body">
		<nav class="subnav">
			{#each NAV as n (n.id)}
				<button class="nav-item" class:active={section === n.id} onclick={() => (section = n.id)}>
					<Icon name={n.icon} size={16} /><span>{n.label}</span>
				</button>
			{/each}
		</nav>

		<div class="content">
			{#if !settings}
				{#if !error}<p class="hint">a carregar…</p>{/if}

			{:else if section === 'account'}
				<div class="card">
					<h3 class="card-title"><Icon name="user" size={15} /> Perfil</h3>
					<div class="field">
						<label for="uname">Nome</label>
						<p class="hint">opcional, só para personalizar (guardado localmente).</p>
						<input id="uname" placeholder="o teu nome" bind:value={settings.user_name} oninput={persist} />
					</div>
				</div>

			{:else if section === 'ia'}
				<div class="card">
					<h3 class="card-title"><Icon name="brain" size={15} /> Modelo & geração</h3>
					<div class="field">
						<label for="model">Modelo de chat</label>
						<p class="hint">o modelo Ollama usado por defeito nas conversas.</p>
						<select id="model" bind:value={settings.chat_model} onchange={persist}>
							{#each models as m}<option value={m}>{m}</option>{/each}
							{#if !models.includes(settings.chat_model)}
								<option value={settings.chat_model}>{settings.chat_model}</option>
							{/if}
						</select>
					</div>
					<div class="field">
						<label for="temp">Temperatura <span class="val">{settings.temperature.toFixed(2)}</span></label>
						<p class="hint">criatividade: 0 = preciso, 2 = muito criativo.</p>
						<input id="temp" type="range" min="0" max="2" step="0.05" bind:value={settings.temperature} onchange={persist} />
					</div>
					<div class="field">
						<label for="ctx">Janela de contexto (num_ctx)</label>
						<p class="hint">tokens de história considerados (mais = mais RAM).</p>
						<input id="ctx" type="number" min="512" max="32768" step="512" bind:value={settings.num_ctx} onchange={persist} />
					</div>
					<div class="field">
						<label for="maxtok">Máximo de tokens na resposta</label>
						<p class="hint">0 = sem limite (default do modelo).</p>
						<input id="maxtok" type="number" min="0" max="8192" step="64" bind:value={settings.max_tokens} onchange={persist} />
					</div>
					<div class="field">
						<label for="sysx">Instrução de sistema (persona)</label>
						<p class="hint">texto adicionado ao início de cada conversa.</p>
						<textarea id="sysx" rows="3" bind:value={settings.system_extra} oninput={persist}></textarea>
					</div>
				</div>

				<div class="card">
					<h3 class="card-title"><Icon name="lightbulb" size={15} /> Memória & skills</h3>
					<div class="field toggle-field">
						<div><label for="mem">Memória</label><p class="hint">aprende factos sobre ti.</p></div>
						<button id="mem" class="toggle" class:on={settings.memory_enabled} onclick={() => toggle('memory_enabled')} aria-label="Memória"><span class="knob"></span></button>
					</div>
					<div class="field toggle-field">
						<div><label for="memrev">Rever memórias antes de gravar</label><p class="hint">aprovas os factos na aba Memória.</p></div>
						<button id="memrev" class="toggle" class:on={settings.memory_review} onclick={() => toggle('memory_review')} aria-label="Rever memórias"><span class="knob"></span></button>
					</div>
					<div class="field toggle-field">
						<div><label for="sk">Skills</label><p class="hint">aplica as instruções ativas.</p></div>
						<button id="sk" class="toggle" class:on={settings.skills_enabled} onclick={() => toggle('skills_enabled')} aria-label="Skills"><span class="knob"></span></button>
					</div>
					<div class="field toggle-field">
						<div><label for="skauto">Auto-aprender skills</label><p class="hint">propõe skills das conversas para aprovares.</p></div>
						<button id="skauto" class="toggle" class:on={settings.skills_auto} onclick={() => toggle('skills_auto')} aria-label="Auto-skills"><span class="knob"></span></button>
					</div>
				</div>

			{:else if section === 'tools'}
				<div class="card">
					<h3 class="card-title"><Icon name="zap" size={15} /> Built-in Tools</h3>
					<p class="hint">liga ou desliga as ferramentas que o agente pode usar (vista Agents). As perigosas estão <strong>desligadas por defeito</strong>.</p>
					{#if tools.length === 0}
						<p class="hint">a carregar ferramentas…</p>
					{/if}
					{#each tools as t (t.name)}
						<div class="field toggle-field" class:danger-field={t.dangerous}>
							<div>
								<label for={'tool-' + t.name}>
									<code>{t.name}</code>
									{#if t.dangerous}<span class="tag tag-danger">acesso total</span>{/if}
									{#if t.requires_internet}<span class="tag">internet</span>{/if}
								</label>
								<p class="hint">
									{t.desc}
									{#if t.dangerous}<br /><strong>Aviso:</strong> executa com acesso total à tua máquina. Liga só se confiares no que pedes ao agente.{/if}
								</p>
							</div>
							<button
								id={'tool-' + t.name}
								class="toggle"
								class:on={t.enabled}
								onclick={() => toggleTool(t.name)}
								aria-label={t.name}><span class="knob"></span></button>
						</div>
					{/each}
				</div>

			{:else if section === 'game'}
				<div class="card">
					<h3 class="card-title"><Icon name="dice" size={15} /> AI Dungeon (/aidungeon)</h3>
					<p class="hint">no chat, escreve <code>/aidungeon</code> para entrar no modo aventura (estilo AI Dungeon: modos Fazer/Dizer/História, Continuar, Repetir, Retroceder). As histórias ficam guardadas na aba <strong>Aventuras</strong>.</p>
					<div class="field">
						<label for="advmodel">Modelo de aventura</label>
						<p class="hint">
							modelo Ollama usado no jogo. Recomendado: <strong>Harbinger-24B</strong> (Latitude Games, base Mistral Small 3.1, ~14GB). Puxa-o com:<br />
							<code>ollama pull {settings.adventure_model || 'hf.co/LatitudeGames/Harbinger-24B-GGUF:Q4_K_M'}</code><br />
							vazio = usa o modelo de reserva abaixo (já instalado).
						</p>
						<input id="advmodel" placeholder="hf.co/LatitudeGames/Harbinger-24B-GGUF:Q4_K_M" bind:value={settings.adventure_model} oninput={persist} />
					</div>
					<div class="field">
						<label for="advfb">Modelo de reserva</label>
						<p class="hint">usado se o de aventura não estiver instalado (corre folgado no teu hardware).</p>
						<select id="advfb" bind:value={settings.adventure_model_fallback} onchange={persist}>
							{#each models as m}<option value={m}>{m}</option>{/each}
							{#if settings.adventure_model_fallback && !models.includes(settings.adventure_model_fallback)}
								<option value={settings.adventure_model_fallback}>{settings.adventure_model_fallback}</option>
							{/if}
						</select>
					</div>
					<p class="hint">nota: o Harbinger-24B compete com o qwen3-vl pela memória; o Ollama troca-os sob demanda, por isso o primeiro token pode demorar.</p>
				</div>

				<div class="card">
					<h3 class="card-title"><Icon name="zap" size={15} /> Sampler do Harbinger</h3>
					<p class="hint">valores oficiais da Latitude Games para este modelo. ChatML e a system message do storyteller são aplicados automaticamente.</p>
					<div class="field">
						<label for="advtemp">Temperatura ({settings.adventure_temperature})</label>
						<input id="advtemp" type="range" min="0" max="2" step="0.05" bind:value={settings.adventure_temperature} oninput={persist} />
					</div>
					<div class="field">
						<label for="advrep">Repetition Penalty ({settings.adventure_repeat_penalty})</label>
						<input id="advrep" type="range" min="1" max="1.5" step="0.01" bind:value={settings.adventure_repeat_penalty} oninput={persist} />
					</div>
					<div class="field">
						<label for="advminp">Min-P ({settings.adventure_min_p})</label>
						<input id="advminp" type="range" min="0" max="0.2" step="0.005" bind:value={settings.adventure_min_p} oninput={persist} />
					</div>
				</div>

				<div class="card">
					<h3 class="card-title"><Icon name="database" size={15} /> Sessões guardadas</h3>
					<p class="hint">
						{adventuresCount()} aventura(s) arquivada(s). Os metadados ficam nas definições; cada história
						num ficheiro próprio em <code>data/adventures/</code>. Vê e retoma na aba <strong>Aventuras</strong>.
					</p>
				</div>

			{:else if section === 'appearance'}
				<div class="card">
					<h3 class="card-title"><Icon name="palette" size={15} /> Tema</h3>
					<div class="field toggle-field">
						<div><label for="anim">Animações de fundo</label><p class="hint">efeitos subtis (respeita reduzir-movimento).</p></div>
						<button id="anim" class="toggle" class:on={settings.ui_anim} onclick={toggleAnim} aria-label="Animações"><span class="knob"></span></button>
					</div>
					<div class="field">
						<span class="field-label">Paleta</span>
						<div class="theme-grid">
							{#each themeEntries as [name, t] (name)}
								<button class="swatch" class:active={name === curTheme} onclick={() => pickTheme(name)}
									style="--s-bg:{t.bg}; --s-fg:{t.fg}; --s-panel:{t.panel}; --s-accent:{t.accent}; --s-border:{t.border}" title={name}>
									<div class="preview"><span class="p-panel"></span><span class="p-accent"></span><span class="p-fg"></span></div>
									<span class="s-name">{name}</span>
								</button>
							{/each}
						</div>
					</div>
				</div>

				<div class="card">
					<h3 class="card-title"><Icon name="message-square" size={15} /> Chat</h3>
					<div class="field toggle-field">
						<div><label for="uiw">Ecrã de boas-vindas</label><p class="hint">logo e dica no chat vazio.</p></div>
						<button id="uiw" class="toggle" class:on={settings.ui_welcome} onclick={() => toggle('ui_welcome')} aria-label="Boas-vindas"><span class="knob"></span></button>
					</div>
					<div class="field toggle-field">
						<div><label for="uit">Mostrar raciocínio</label><p class="hint">mostra os blocos &lt;think&gt; em vez de os ocultar.</p></div>
						<button id="uit" class="toggle" class:on={settings.ui_thinking} onclick={() => toggle('ui_thinking')} aria-label="Raciocínio"><span class="knob"></span></button>
					</div>
					<div class="field toggle-field">
						<div><label for="uie">Sem emojis</label><p class="hint">remove emojis das respostas.</p></div>
						<button id="uie" class="toggle" class:on={settings.ui_text_emojis} onclick={() => toggle('ui_text_emojis')} aria-label="Sem emojis"><span class="knob"></span></button>
					</div>
				</div>

			{:else if section === 'privacy'}
				<div class="card">
					<h3 class="card-title"><Icon name="eye" size={15} /> Acesso à internet</h3>
					<div class="field toggle-field danger-field">
						<div>
							<label for="net">Acesso à internet</label>
							<p class="hint"><strong>desligado por defeito.</strong> Permite saídas (ex.: dispatch, web do agente). O modelo (Ollama) corre sempre offline.</p>
						</div>
						<button id="net" class="toggle" class:on={settings.internet_enabled} onclick={() => toggle('internet_enabled')} aria-label="Internet"><span class="knob"></span></button>
					</div>
				</div>

				<div class="card">
					<h3 class="card-title"><Icon name="search" size={15} /> Pesquisa web</h3>
					<p class="hint">usada pelo agente (ferramenta <code>pesquisar_web</code>). só funciona com a internet ligada.</p>
					<div class="field">
						<label for="sprov">Provedor</label>
						<select id="sprov" bind:value={settings.search_provider} onchange={persist}>
							<option value="duckduckgo">DuckDuckGo (sem chave)</option>
							<option value="searxng">SearXNG (self-hosted)</option>
						</select>
					</div>
					<div class="field">
						<label for="sres">Nº de resultados</label>
						<input id="sres" type="number" min="1" max="10" bind:value={settings.search_results} onchange={persist} />
					</div>
					{#if settings.search_provider === 'searxng'}
						<div class="field">
							<label for="surl">URL da instância SearXNG</label>
							<p class="hint">ex.: http://localhost:8080 (vazio = usa DuckDuckGo).</p>
							<input id="surl" placeholder="http://localhost:8080" bind:value={settings.search_url} oninput={persist} />
						</div>
					{/if}
				</div>

			{:else if section === 'data'}
				<div class="card">
					<h3 class="card-title"><Icon name="download" size={15} /> Cópia de segurança</h3>
					<p class="hint">exporta/importa memória, skills, notas e tarefas como JSON.</p>
					<div class="data-row">
						<button class="data-btn" onclick={doExport}><Icon name="download" size={13} /> exportar</button>
						<button class="data-btn" onclick={doImport}><Icon name="upload" size={13} /> importar</button>
					</div>
				</div>
				<div class="card danger-card">
					<h3 class="card-title danger"><Icon name="x" size={15} /> Zona de perigo</h3>
					<p class="hint">irreversível. cada ação apaga só a sua categoria.</p>
					{#if wipeMsg}<p class="wipe-msg">{wipeMsg}</p>{/if}
					{#each WIPES as w (w.id)}
						<div class="wipe-row">
							<div><strong>{w.label}</strong><span class="wipe-desc">{w.desc}</span></div>
							<button class="wipe-btn" onclick={() => doWipe(w.id, w.label)}>apagar</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.view {
		flex: 1;
		min-width: 0;
		height: 100dvh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.head {
		padding: 22px 28px 14px;
		border-bottom: 1px solid var(--border);
	}
	.head-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.close-btn {
		display: grid;
		place-items: center;
		width: 34px;
		height: 34px;
		border-radius: 9px;
		border: 1px solid var(--border);
		background: transparent;
		color: var(--fg-muted);
		cursor: pointer;
	}
	.close-btn:hover {
		color: var(--fg-strong);
		border-color: var(--accent);
	}
	.head h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0;
		font-size: 19px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.saved {
		font-size: 12px;
		font-weight: 400;
		color: var(--green);
		margin-left: 6px;
	}
	.sub {
		margin: 6px 0 0;
		font-size: 12.5px;
		color: var(--fg-muted);
	}
	.err {
		color: var(--red);
		font-size: 13px;
		padding: 10px 28px 0;
	}

	.body {
		flex: 1;
		display: flex;
		min-height: 0;
	}
	.subnav {
		width: 210px;
		flex: none;
		border-right: 1px solid var(--border);
		padding: 16px 10px;
		display: flex;
		flex-direction: column;
		gap: 3px;
		overflow-y: auto;
	}
	.nav-item {
		display: flex;
		align-items: center;
		gap: 11px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 13.5px;
		padding: 9px 12px;
		border-radius: 9px;
		cursor: pointer;
		transition: background 0.13s, color 0.13s;
	}
	.nav-item :global(svg) {
		color: var(--fg-muted);
	}
	.nav-item:hover {
		background: color-mix(in srgb, var(--fg) 6%, transparent);
		color: var(--fg);
	}
	.nav-item.active {
		background: color-mix(in srgb, var(--accent) 16%, transparent);
		color: var(--accent);
	}
	.nav-item.active :global(svg) {
		color: var(--accent);
	}

	.content {
		flex: 1;
		min-width: 0;
		overflow-y: auto;
		padding: 22px 28px 60px;
		display: flex;
		flex-direction: column;
		gap: 18px;
		max-width: 760px;
	}

	.card {
		border: 1px solid var(--border);
		border-radius: 14px;
		padding: 6px 18px 16px;
		background: color-mix(in srgb, var(--panel) 45%, transparent);
	}
	.card-title {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0;
		padding: 14px 0 6px;
		font-size: 14px;
		font-weight: 600;
		color: var(--fg-strong);
		border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
	}
	.card-title.danger {
		color: var(--red);
	}
	.danger-card {
		border-color: color-mix(in srgb, var(--red) 35%, var(--border));
		background: color-mix(in srgb, var(--red) 5%, transparent);
	}

	.field {
		padding: 14px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--border) 45%, transparent);
	}
	.field:last-child {
		border-bottom: none;
	}
	label,
	.field-label {
		display: block;
		font-size: 14px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.val {
		color: var(--fg-muted);
		font-weight: 400;
		font-size: 12px;
	}
	.hint {
		font-size: 12px;
		color: var(--fg-muted);
		margin: 4px 0 10px;
	}
	select,
	input,
	textarea {
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
	textarea {
		font-family: var(--font-body);
		resize: vertical;
	}
	select:focus,
	input:focus,
	textarea:focus {
		border-color: var(--accent);
	}
	input[type='range'] {
		accent-color: var(--accent);
		padding: 0;
	}

	.tag {
		display: inline-block;
		margin-left: 6px;
		padding: 1px 7px;
		border-radius: 999px;
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.2px;
		vertical-align: middle;
		color: var(--fg-muted);
		background: color-mix(in srgb, var(--fg) 10%, transparent);
		border: 1px solid var(--border);
	}
	.tag-danger {
		color: var(--red);
		background: color-mix(in srgb, var(--red) 14%, transparent);
		border-color: color-mix(in srgb, var(--red) 40%, transparent);
	}
	code {
		font-family: var(--font-body);
		font-size: 12.5px;
		background: color-mix(in srgb, var(--fg) 8%, transparent);
		padding: 1px 5px;
		border-radius: 5px;
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
	.danger-field {
		border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
		border-radius: 12px;
		padding: 12px;
		background: color-mix(in srgb, var(--accent) 5%, transparent);
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

	.theme-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
		gap: 10px;
		margin-top: 6px;
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
		height: 28px;
		padding: 0 4px;
		border-radius: 7px;
		background: var(--s-panel);
		border: 1px solid var(--s-border);
	}
	.p-panel {
		width: 20px;
		height: 13px;
		border-radius: 4px;
		background: var(--s-bg);
		border: 1px solid var(--s-border);
	}
	.p-accent {
		width: 13px;
		height: 13px;
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
		font-size: 10px;
		color: var(--s-fg);
		text-align: center;
		text-transform: lowercase;
	}

	.data-row {
		display: flex;
		gap: 10px;
	}
	.data-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		background: var(--panel);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font: inherit;
		font-size: 13px;
		padding: 8px 16px;
		border-radius: 10px;
		cursor: pointer;
		width: auto;
	}
	.data-btn:hover {
		border-color: var(--accent);
		color: var(--accent);
	}
	.wipe-msg {
		color: var(--green);
		font-size: 12px;
		margin: 8px 0;
	}
	.wipe-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 0;
		border-bottom: 1px solid color-mix(in srgb, var(--border) 45%, transparent);
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
		width: auto;
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

	@media (max-width: 640px) {
		.body {
			flex-direction: column;
		}
		.subnav {
			width: 100%;
			flex-direction: row;
			overflow-x: auto;
			border-right: none;
			border-bottom: 1px solid var(--border);
			padding: 10px;
		}
		.nav-item {
			width: auto;
			white-space: nowrap;
		}
	}
</style>
