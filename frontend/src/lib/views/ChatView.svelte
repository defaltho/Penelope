<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { streamChat } from '$lib/chat';
	import { StreamBuffer } from '$lib/stream-buffer';
	import Icon from '$lib/components/Icon.svelte';
	import ModelBadge from '$lib/components/ModelBadge.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import ActivityLane from '$lib/components/ActivityLane.svelte';
	import ThinkingPanel from '$lib/components/ThinkingPanel.svelte';
	import Markdown from '$lib/components/Markdown.svelte';
	import { sanitizePartial } from '$lib/markdown';
	import { notify, requestPermission } from '$lib/notifications';
	import {
		getMessages,
		listModels,
		getSettings,
		imageUrl,
		compactChat,
	} from '$lib/api';
	import {
		matchCommands,
		parseCommand,
		helpText,
		type SlashCommand
	} from '$lib/commands';

	let {
		openConvoId = null,
		conversationId = $bindable(null),
		newSignal = 0,
		onConversationsChanged = () => {},
	}: {
		openConvoId?: number | null;
		conversationId?: number | null;
		newSignal?: number;
		onConversationsChanged?: () => void;
	} = $props();

	interface Msg {
		role: 'user' | 'assistant';
		content: string;
		image?: string;
		file?: { name: string };
		model?: string;
		tokPerSec?: number;
	}

	let messages = $state<Msg[]>([]);
	let input = $state('');
	let streaming = $state(false);
	let errorMsg = $state<string | null>(null);
	let pendingImage = $state<string | null>(null);
	// Ficheiro de texto/código anexado (lido como texto, juntado ao contexto).
	let pendingFile = $state<{ name: string; content: string } | null>(null);
	const MAX_FILE_CHARS = 200_000; // ~200KB de texto, para não estourar o contexto
	// Extensões de texto/código aceites (além de qualquer image/*).
	const TEXT_EXTS = [
		'txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'jsonl', 'xml', 'yaml', 'yml',
		'toml', 'ini', 'env', 'log', 'html', 'css', 'scss', 'js', 'ts', 'jsx', 'tsx',
		'svelte', 'vue', 'py', 'rb', 'go', 'rs', 'java', 'c', 'h', 'cpp', 'cs', 'php',
		'sh', 'bash', 'zsh', 'sql', 'r', 'lua', 'kt', 'swift', 'dart', 'gitignore'
	];
	const FILE_ACCEPT = 'image/*,' + TEXT_EXTS.map((e) => '.' + e).join(',') + ',text/*';
	// Fase atual do turno em streaming (B2: activity lane).
	let activity = $state<{ kind: string; text: string } | null>(null);
	// Composer (B6): fila de mensagens enquanto ocupado + histórico de envios.
	let msgQueue = $state<string[]>([]);
	let inputHistory = $state<string[]>([]);
	let histIdx = $state(-1); // -1 = a escrever (não a navegar o histórico)

	let models = $state<string[]>([]);
	let selectedModel = $state('');
	let modelMenuOpen = $state(false);
	let openMenu = $state<number | null>(null);
	let incognito = $state(false);
	let webSearch = $state(false);
	let internetOn = $state(false);
	let plusMenuOpen = $state(false);
	let uiWelcome = $state(true);
	let uiThinking = $state(false);
	let uiTextEmojis = $state(false);
	let dragging = $state(false);

	let slashIndex = $state(0);
	let slashHidden = $state(false);
	const slashMatches = $derived(matchCommands(input));
	const slashMenuOpen = $derived(!slashHidden && slashMatches.length > 0);
	const groupedSlash = $derived.by(() => {
		const groups: { cat: string; cmds: typeof slashMatches }[] = [];
		const seen = new Set<string>();
		for (const c of slashMatches) {
			const cat = c.category || '';
			if (!seen.has(cat)) { seen.add(cat); groups.push({ cat, cmds: [] }); }
			groups.find(g => g.cat === cat)!.cmds.push(c);
		}
		return groups;
	});
	$effect(() => {
		// Reset do índice destacado sempre que a lista de sugestões muda.
		slashMatches.length;
		slashIndex = 0;
	});

	const EMOJI_RE =
		/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{FE0F}\u{200D}]/gu;

	// Separa o raciocínio (<think>…</think>, possivelmente ainda aberto durante o
	// streaming) da resposta visível. `thinking` = bloco <think> ainda sem fecho.
	function parseAssistant(c: string): { think: string; answer: string; thinking: boolean } {
		const open = c.indexOf('<think>');
		if (open === -1) return { think: '', answer: c, thinking: false };
		const close = c.indexOf('</think>');
		if (close === -1) {
			// Em streaming: o <think> abriu mas ainda não fechou -> tudo é raciocínio.
			return { think: c.slice(open + 7), answer: '', thinking: true };
		}
		const think = c.slice(open + 7, close);
		const answer = c.slice(0, open) + c.slice(close + 8);
		return { think, answer, thinking: false };
	}

	function displayAnswer(c: string): string {
		let out = c.trimStart();
		if (uiTextEmojis) out = out.replace(EMOJI_RE, '').replace(/\s{2,}/g, ' ');
		return out;
	}

	let scroller: HTMLDivElement;
	let textarea: HTMLTextAreaElement;
	let fileInput: HTMLInputElement;

	const hasMessages = $derived(messages.length > 0);

	const NUM_CTX = 8192;
	const contextPct = $derived(
		Math.min(
			100,
			Math.round((messages.reduce((n, m) => n + (m.content?.length || 0), 0) / 4 / NUM_CTX) * 100)
		)
	);
	// Status bar (B5): velocidade do último turno + saúde do Ollama (modelos carregados).
	const lastTps = $derived.by(() => {
		for (let i = messages.length - 1; i >= 0; i--) {
			if (messages[i].role === 'assistant' && messages[i].tokPerSec) return messages[i].tokPerSec!;
		}
		return null;
	});
	const ollamaOnline = $derived(models.length > 0);

	let lastOpened = $state<number | null>(null);
	$effect(() => {
		if (openConvoId != null && openConvoId !== lastOpened) {
			lastOpened = openConvoId;
			loadConversation(openConvoId);
		}
	});

	let lastNew = $state(0);
	$effect(() => {
		if (newSignal !== lastNew) {
			lastNew = newSignal;
			newConversation();
		}
	});

	onMount(async () => {
		try {
			const [mdls, settings] = await Promise.all([
				listModels().then((m) => m.filter((x) => !x.includes('embed'))),
				getSettings()
			]);
			models = mdls;
			selectedModel = settings.chat_model || mdls[0] || '';
			uiWelcome = settings.ui_welcome;
			uiThinking = settings.ui_thinking;
			uiTextEmojis = settings.ui_text_emojis;
			internetOn = settings.internet_enabled;
			if (!internetOn) webSearch = false;
		} catch (e) {
			console.error('falha a obter modelos', e);
		}
		requestPermission();
	});

	async function loadConversation(id: number) {
		if (streaming) return;
		try {
			const msgs = await getMessages(id);
			messages = msgs
				.filter((m) => m.role === 'user' || m.role === 'assistant')
				.map((m) => ({
					role: m.role as 'user' | 'assistant',
					content: m.content,
					image: m.image_path ? imageUrl(m.image_path) : undefined,
					model: m.model ?? undefined,
					tokPerSec: m.tok_per_sec ?? undefined
				}));
			conversationId = id;
			errorMsg = null;
			await scrollToBottom();
		} catch (e) {
			errorMsg = 'falha a carregar a conversa';
		}
	}

	async function scrollToBottom() {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
	}

	function autoGrow() {
		if (!textarea) return;
		textarea.style.height = 'auto';
		textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
	}

	function processFile(file: File) {
		errorMsg = null;
		const ext = (file.name.split('.').pop() || '').toLowerCase();
		const isText = file.type.startsWith('text/') || TEXT_EXTS.includes(ext);
		if (file.type.startsWith('image/')) {
			const reader = new FileReader();
			reader.onload = () => {
				pendingImage = reader.result as string;
				pendingFile = null;
			};
			reader.readAsDataURL(file);
		} else if (isText) {
			const reader = new FileReader();
			reader.onload = () => {
				let content = (reader.result as string) || '';
				if (content.length > MAX_FILE_CHARS) {
					content = content.slice(0, MAX_FILE_CHARS) + '\n…(ficheiro truncado)';
				}
				pendingFile = { name: file.name, content };
				pendingImage = null;
			};
			reader.readAsText(file);
		} else {
			errorMsg = `formato não suportado: "${file.name}". Usa uma imagem ou um ficheiro de texto/código.`;
		}
	}

	function onPickFile(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0];
		if (!file) return;
		fileInput.value = '';
		processFile(file);
	}

	async function send(textOverride?: string, forceWeb = false) {
		const text = (textOverride ?? input).trim();
		const image = textOverride ? null : pendingImage;
		const file = textOverride ? null : pendingFile;
		if ((!text && !image && !file) || streaming) return;

		const useWeb = (forceWeb || webSearch) && internetOn;

		// O modelo recebe o conteúdo do ficheiro junto ao texto; a UI mostra só um chip.
		const ext = file ? (file.name.split('.').pop() || '').toLowerCase() : '';
		const modelText = file
			? `Ficheiro anexado "${file.name}":\n\`\`\`${ext}\n${file.content}\n\`\`\`\n\n${text}`.trim()
			: text;

		errorMsg = null;
		messages.push({
			role: 'user',
			content: text,
			image: image ?? undefined,
			file: file ? { name: file.name } : undefined
		});
		if (!textOverride) input = '';
		pendingImage = null;
		pendingFile = null;
		autoGrow();

		const idx = messages.push({ role: 'assistant', content: '', model: selectedModel }) - 1;
		streaming = true;
		let tokens = 0;
		let startedAt = 0;
		// Buffer de fluidez (B1): aplica os tokens ao render de forma suave via RAF.
		const buf = new StreamBuffer((chunk) => {
			messages[idx].content += chunk;
			scrollToBottom();
		});
		activity = { kind: 'thinking', text: '' };
		await scrollToBottom();

		await streamChat(
			modelText,
			conversationId,
			{
				onStatus: (kind, statusText) => {
					activity = { kind, text: statusText };
					scrollToBottom();
				},
				onToken: (t) => {
					if (startedAt === 0) startedAt = performance.now();
					activity = null; // o primeiro token termina a fase de preparação
					tokens += 1;
					buf.push(t);
				},
				onDone: (id) => {
					buf.flush();
					activity = null;
					streaming = false;
					const secs = startedAt ? (performance.now() - startedAt) / 1000 : 0;
					if (secs > 0 && tokens > 1) messages[idx].tokPerSec = tokens / secs;
					// Anónimo: id vem null; não fixa conversa nem refresca a sidebar.
					if (id != null) {
						conversationId = id;
						onConversationsChanged();
					}
					notify('Penelope', 'Resposta pronta.');
					// Drenar a fila do composer (B6): envia a próxima mensagem em espera.
					const next = msgQueue.shift();
					if (next) send(next);
				},
				onError: (msg) => {
					buf.stop();
					activity = null;
					errorMsg = msg;
					streaming = false;
					if (messages[idx]?.content === '') messages.splice(idx, 1);
				}
			},
			image,
			selectedModel,
			incognito,
			useWeb,
			null
		);
	}

	function newConversation() {
		if (streaming) return;
		messages = [];
		conversationId = null;
		errorMsg = null;
		input = '';
		pendingImage = null;
		autoGrow();
		textarea?.focus();
	}

	function onComposerInput() {
		autoGrow();
		slashHidden = false;
	}

	function onKeydown(e: KeyboardEvent) {
		// Navegação no menu de slash-commands.
		if (slashMenuOpen) {
			if (e.key === 'ArrowDown') {
				e.preventDefault();
				slashIndex = (slashIndex + 1) % slashMatches.length;
				return;
			}
			if (e.key === 'ArrowUp') {
				e.preventDefault();
				slashIndex = (slashIndex - 1 + slashMatches.length) % slashMatches.length;
				return;
			}
			if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
				e.preventDefault();
				pickSlash(slashMatches[slashIndex]);
				return;
			}
			if (e.key === 'Escape') {
				e.preventDefault();
				slashHidden = true;
				return;
			}
		}
		// Histórico de envios (B6): Up/Down quando não se está a navegar o slash menu
		// e o composer está vazio (ou já em navegação). Não interfere com multiline.
		if (!slashMenuOpen && inputHistory.length && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
			const navigating = histIdx >= 0;
			if (e.key === 'ArrowUp' && (input === '' || navigating)) {
				e.preventDefault();
				histIdx = Math.min(histIdx + 1, inputHistory.length - 1);
				input = inputHistory[inputHistory.length - 1 - histIdx];
				return;
			}
			if (e.key === 'ArrowDown' && navigating) {
				e.preventDefault();
				histIdx -= 1;
				input = histIdx < 0 ? '' : inputHistory[inputHistory.length - 1 - histIdx];
				return;
			}
		}
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	// ---- Slash-commands ----
	function submit() {
		const cmd = parseCommand(input);
		if (cmd) {
			runCommand(cmd.name, cmd.rest);
			return;
		}
		const text = input.trim();
		// Regista no histórico; se ocupado, enfileira em vez de descartar.
		if (text) {
			inputHistory.push(text);
			histIdx = -1;
			if (streaming) {
				msgQueue.push(text);
				input = '';
				autoGrow();
				return;
			}
		}
		send();
	}

	function pickSlash(c: SlashCommand) {
		if (c.takesArg) {
			input = '/' + c.name + ' ';
			slashHidden = true;
			textarea?.focus();
			autoGrow();
		} else {
			runCommand(c.name, '');
		}
	}

	function pushInfo(text: string) {
		messages.push({ role: 'assistant', content: text, model: 'sistema' });
		scrollToBottom();
	}

	function runCommand(name: string, rest: string) {
		input = '';
		slashHidden = false;
		autoGrow();
		switch (name) {
			case 'help':
				pushInfo(helpText());
				break;
			case 'new':
				newConversation();
				break;
			case 'clear':
				messages = [];
				conversationId = null;
				errorMsg = null;
				pendingImage = null;
				pendingFile = null;
				break;
			case 'compact':
				if (!conversationId) {
					errorMsg = 'Nenhuma conversa para compactar.';
					break;
				}
				streaming = true;
				activity = { kind: 'thinking', text: 'a compactar…' };
				compactChat(conversationId)
					.then((r) => {
						messages = [
							{ role: 'user', content: '[contexto compactado]' },
							{ role: 'assistant', content: r.summary, model: 'sistema' }
						];
						streaming = false;
						activity = null;
					})
					.catch((e) => {
						errorMsg = String(e);
						streaming = false;
						activity = null;
					});
				break;
			case 'model':
				if (rest) {
					selectedModel = rest;
					pushInfo(`Modelo do chat: ${rest}`);
				} else {
					modelMenuOpen = true;
				}
				break;
			case 'search':
				if (!internetOn) {
					errorMsg = 'Liga o acesso à internet nas Definições para pesquisar.';
					break;
				}
				if (rest) send(rest, true);
				else {
					input = '/search ';
					textarea?.focus();
				}
				break;
			case 'incognito':
				incognito = !incognito;
				pushInfo(incognito ? 'Modo anónimo ligado.' : 'Modo anónimo desligado.');
				break;
			case 'think':
				uiThinking = !uiThinking;
				pushInfo(uiThinking ? 'A mostrar o raciocínio do modelo.' : 'A ocultar o raciocínio do modelo.');
				break;
			case 'image':
				fileInput?.click();
				break;
			case 'retry':
				regenerate(messages.length);
				break;
			default:
				errorMsg = `Comando desconhecido: /${name}. Usa /help.`;
		}
	}

	// ---- Ações por mensagem ----
	async function copyMsg(m: Msg) {
		try {
			await navigator.clipboard.writeText(m.content);
		} catch (e) {
			console.error('copiar falhou', e);
		}
		openMenu = null;
	}
	function lastUserText(beforeIdx: number) {
		for (let i = beforeIdx - 1; i >= 0; i--) if (messages[i].role === 'user') return messages[i].content;
		return '';
	}
	function regenerate(idx: number) {
		openMenu = null;
		const t = lastUserText(idx);
		if (t) send(t);
	}
	function explainSimpler() {
		openMenu = null;
		send('Explica a tua última resposta de forma mais simples e curta.');
	}
	function deleteMsg(idx: number) {
		openMenu = null;
		messages.splice(idx, 1);
	}
</script>

<div
	class="chat-area"
	ondragover={(e) => { e.preventDefault(); dragging = true; }}
	ondragleave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) dragging = false; }}
	ondrop={(e) => { e.preventDefault(); dragging = false; const f = e.dataTransfer?.files?.[0]; if (f) processFile(f); }}
>
	{#if dragging}
		<div class="drop-overlay">Larga aqui o ficheiro</div>
	{/if}
	<div class="scroller" bind:this={scroller}>
		<div class="thread">
			{#if !hasMessages && uiWelcome}
				<div class="welcome-screen">
					<div class="wmark"><span class="dot"></span></div>
					<h1>penelope<span class="caret"></span></h1>
					<p>
						{incognito ? 'modo anónimo: nada será guardado.' : 'assistente local. lembro-me do que importa.'}
					</p>
					<button
						class="incognito-pill"
						class:on={incognito}
						onclick={() => (incognito = !incognito)}
						title={incognito ? 'Anónimo ligado' : 'Ligar modo anónimo'}
					>
						<Icon name={incognito ? 'eye-off' : 'eye'} size={14} />
						{incognito ? 'anónimo' : 'normal'}
					</button>
				</div>
			{/if}

			{#each messages as m, i (i)}
				<div class="msg {m.role === 'user' ? 'msg-user' : 'msg-ai'}">
					<div class="role">
						{#if m.role === 'assistant'}<ModelBadge name={m.model || 'penelope'} size={15} />{:else}<span
								class="role-dot"
							></span>{/if}
						{m.role === 'user' ? 'tu' : m.model || 'penelope'}
					</div>
					<div class="body">
						{#if m.image}<img class="msg-image" src={m.image} alt="imagem anexada" />{/if}
						{#if m.file}<span class="msg-file"><Icon name="file-text" size={13} /> {m.file.name}</span>{/if}
						{#if m.role === 'assistant'}
							{@const parsed = parseAssistant(m.content)}
							{#if uiThinking && parsed.think.trim()}
								<ThinkingPanel content={parsed.think} active={parsed.thinking && streaming && i === messages.length - 1} />
							{/if}
							{#if displayAnswer(parsed.answer)}
								{#if streaming && i === messages.length - 1}<div class="streaming-md"><Markdown source={sanitizePartial(displayAnswer(parsed.answer))} /><span class="caret"></span></div>
								{:else}<Markdown source={displayAnswer(parsed.answer)} />{/if}
							{:else if streaming && i === messages.length - 1}
								{#if activity}<ActivityLane kind={activity.kind} text={activity.text} />{:else}<Spinner />{/if}
							{/if}
						{:else if m.content}{m.content}{/if}
					</div>

					{#if m.role === 'assistant' && m.content && !(streaming && i === messages.length - 1)}
						<div class="msg-foot">
							{#if m.tokPerSec}<span class="stat">{m.tokPerSec.toFixed(1)} tok/s</span><span class="sep"
									>|</span
								>{/if}
							<button class="foot-btn" onclick={() => copyMsg(m)} title="Copiar" aria-label="Copiar">
								<Icon name="copy" size={13} />
							</button>
							<div class="foot-menu-wrap">
								<button
									class="foot-btn"
									onclick={() => (openMenu = openMenu === i ? null : i)}
									title="Mais ações"
									aria-label="Mais ações"
								>
									<Icon name="more" size={14} />
								</button>
								{#if openMenu === i}
									<div class="foot-menu">
										<button onclick={() => copyMsg(m)}><Icon name="copy" size={13} /> Copiar</button>
										<button onclick={() => regenerate(i)}>
											<Icon name="refresh" size={13} /> Regenerar
										</button>
										<button onclick={explainSimpler}>
											<Icon name="help" size={13} /> Explicar simples
										</button>
										<button class="danger" onclick={() => deleteMsg(i)}>
											<Icon name="x" size={13} /> Apagar
										</button>
									</div>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/each}

			{#if errorMsg}
				<div class="msg msg-ai error">
					<div class="role"><span class="role-dot"></span>erro</div>
					<div class="body">{errorMsg}</div>
				</div>
			{/if}
		</div>
	</div>

	<div class="composer-zone" class:welcome={!hasMessages}>
		<div class="composer">
			{#if pendingImage}
				<div class="image-chip">
					<img src={pendingImage} alt="pré-visualização" />
					<button class="chip-remove" onclick={() => (pendingImage = null)} aria-label="remover">×</button>
				</div>
			{/if}
			{#if pendingFile}
				<div class="file-chip">
					<Icon name="file-text" size={14} />
					<span class="file-name">{pendingFile.name}</span>
					<button class="chip-remove" onclick={() => (pendingFile = null)} aria-label="remover">×</button>
				</div>
			{/if}
			<div class="input-row">
				<input bind:this={fileInput} type="file" accept={FILE_ACCEPT} onchange={onPickFile} hidden />
					{#if slashMenuOpen}
						<div class="slash-menu" role="listbox" tabindex="-1">
							{#each groupedSlash as group}
								{#if group.cat}<div class="slash-cat">{group.cat}</div>{/if}
								{#each group.cmds as c (c.name)}
									<button
										class="slash-item"
										class:active={slashMatches.indexOf(c) === slashIndex}
										onmousedown={(e) => {
											e.preventDefault();
											pickSlash(c);
										}}
									>
										<span class="slash-name">/{c.name}{#if c.hint}<span class="slash-hint"> {c.hint}</span>{/if}</span>
										<span class="slash-desc">{c.desc}</span>
									</button>
								{/each}
							{/each}
						</div>
					{/if}
					{#if plusMenuOpen}
						<div class="plus-menu">
							<button onclick={() => { plusMenuOpen = false; fileInput.click(); }}>
								<Icon name="paperclip" size={14} /> Anexar ficheiro
							</button>
							<button onclick={() => { plusMenuOpen = false; input = (input ? input + '\n' : '') + 'Age como um especialista e '; textarea?.focus(); autoGrow(); }}>
								<Icon name="zap" size={14} /> Prompt
							</button>
							<button onclick={() => { plusMenuOpen = false; incognito = !incognito; }}>
								<Icon name={incognito ? 'eye-off' : 'eye'} size={14} /> {incognito ? 'Sair do anónimo' : 'Modo anónimo'}
							</button>
						</div>
					{/if}
				<button
					class="attach-btn"
					onclick={() => (plusMenuOpen = !plusMenuOpen)}
					disabled={streaming}
					title="anexar ficheiro"
					aria-label="anexar"
				>
					<Icon name="plus" size={18} />
				</button>
				<button
					class="web-btn"
					class:on={webSearch}
					onclick={() => {
						if (!internetOn) return;
						webSearch = !webSearch;
					}}
					disabled={streaming || !internetOn}
					title={internetOn
						? webSearch
							? 'Pesquisa web ligada'
							: 'Pesquisar na web antes de responder'
						: 'Liga o acesso à internet nas Definições para usar a pesquisa web'}
					aria-label="pesquisa web"
					aria-pressed={webSearch}
				>
					<Icon name="globe" size={17} />
				</button>
				<textarea
					bind:this={textarea}
					bind:value={input}
					oninput={onComposerInput}
					onkeydown={onKeydown}
					placeholder="pergunta alguma coisa…  (/ para comandos)"
					rows="1"
				></textarea>
				<button
					class="send-btn"
					onclick={submit}
					disabled={input.trim() === '' && !pendingImage && !pendingFile}
					aria-label="enviar"
				>
					<Icon name="arrow-up" size={17} stroke={2.4} />
				</button>
			</div>
		</div>

		<!-- Rodapé estilo ChatGPT: modelo + contexto -->
		<div class="meta-foot">
			<div class="model-picker">
				<button class="model-pill" onclick={() => (modelMenuOpen = !modelMenuOpen)}>
					<ModelBadge name={selectedModel} size={14} />
					<span class="mp-name">{selectedModel || 'modelo'}</span>
					<Icon name="chevron" size={12} />
				</button>
				{#if modelMenuOpen}
					<div class="model-menu">
						{#each models as mo}
							<button
								class="model-opt"
								class:on={mo === selectedModel}
								onclick={() => {
									selectedModel = mo;
									modelMenuOpen = false;
								}}
							>
								<ModelBadge name={mo} size={14} />{mo}
							</button>
						{/each}
					</div>
				{/if}
			</div>
			<div class="status-group">
				{#if msgQueue.length}
					<span class="st-queue" title="mensagens em fila">{msgQueue.length} em fila</span>
				{/if}
				{#if lastTps}<span class="st-tps">{lastTps.toFixed(1)} tok/s</span>{/if}
				<span
					class="st-health"
					class:bad={!ollamaOnline}
					title={ollamaOnline ? 'Ollama ligado' : 'Ollama indisponível'}
				>
					<span class="st-dot"></span>Ollama
				</span>
				<span class="ctx" title="janela de contexto estimada">
					<span class="ctx-ring" style="--p:{contextPct}"></span>{contextPct}% contexto
				</span>
			</div>
		</div>
	</div>

</div>

<style>
	.chat-area {
		position: relative;
		flex: 1;
		min-width: 0;
		height: 100dvh;
		display: flex;
		flex-direction: column;
	}

	.scroller {
		flex: 1;
		overflow-y: auto;
	}
	.thread {
		display: flex;
		flex-direction: column;
		padding: 26px 20px;
		min-height: 100%;
		max-width: 800px;
		width: 100%;
		margin: 0 auto;
	}

	.welcome-screen {
		margin: auto;
		text-align: center;
		color: var(--fg-muted);
		animation: pen-pop 0.4s cubic-bezier(0.22, 0.61, 0.36, 1) both;
	}
	.wmark {
		width: 46px;
		height: 46px;
		margin: 0 auto 18px;
		border-radius: 14px;
		border: 1px solid var(--border);
		display: grid;
		place-items: center;
		background: radial-gradient(
			circle at 50% 40%,
			color-mix(in srgb, var(--accent) 18%, transparent),
			transparent 70%
		);
	}
	.wmark .dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 14px var(--accent);
	}
	.welcome-screen h1 {
		font-size: 27px;
		font-weight: 600;
		letter-spacing: 1.5px;
		color: var(--fg-strong);
		margin: 0 0 10px;
	}
	.caret {
		display: inline-block;
		width: 0.6ch;
		height: 1.1em;
		margin-left: 2px;
		vertical-align: -0.16em;
		background: var(--accent);
		animation: caret-blink 1.1s steps(1) infinite;
	}
	@keyframes caret-blink {
		0%,
		50% {
			opacity: 1;
		}
		50.01%,
		100% {
			opacity: 0;
		}
	}
	.welcome-screen p {
		margin: 0;
		font-size: 13px;
		letter-spacing: 0.3px;
	}

	.msg {
		position: relative;
		display: flex;
		flex-direction: column;
		width: fit-content;
		max-width: 88%;
		min-width: 80px;
		margin: 10px 0;
		padding: 10px 14px;
		line-height: 1.45;
		word-wrap: break-word;
		overflow-wrap: break-word;
		border: 1px solid var(--border);
		animation: msg-enter 0.26s ease-out both;
	}
	.msg-user {
		align-self: flex-end;
		margin-left: auto;
		background: var(--user-bubble-bg);
		border-radius: 16px 16px 4px 16px;
	}
	.msg-ai {
		align-self: stretch;
		width: 100%;
		max-width: 100%;
		background: color-mix(in srgb, var(--panel) 45%, transparent);
		border-radius: 14px;
		border-color: color-mix(in srgb, var(--border) 65%, transparent);
		box-shadow: inset 2px 0 0 -0.5px color-mix(in srgb, var(--accent) 40%, transparent);
	}
	.msg.error {
		border-color: var(--red);
		background: color-mix(in srgb, var(--red) 16%, var(--panel));
	}

	.role {
		display: flex;
		align-items: center;
		gap: 7px;
		margin-bottom: 6px;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.3px;
		color: var(--fg-muted);
	}
	.msg-ai .role {
		color: var(--accent);
	}
	.role-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
		background: color-mix(in srgb, var(--fg) 35%, transparent);
	}
	.msg.error .role-dot {
		background: var(--red);
	}

	.body {
		color: var(--fg-strong);
		font-family: var(--font-ui);
		font-size: 14.5px;
		white-space: pre-wrap;
	}
	/* Serif (--font-body) reservado ao OUTPUT da LLM, para leitura.
	   As mensagens do utilizador ficam em sans (--font-ui), como o resto da UI. */
	.msg-ai .body {
		font-family: var(--font-body);
	}
	.msg.error .body {
		color: #ffd9d4;
	}

	.msg-foot {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 10px;
		font-size: 11px;
		color: var(--fg-muted);
	}
	.stat {
		font-variant-numeric: tabular-nums;
	}
	.sep {
		opacity: 0.4;
	}
	.foot-btn {
		display: inline-grid;
		place-items: center;
		width: 24px;
		height: 24px;
		background: transparent;
		border: none;
		border-radius: 7px;
		color: var(--fg-muted);
		cursor: pointer;
		transition: color 0.13s, background 0.13s;
	}
	.foot-btn:hover {
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
	}
	.foot-menu-wrap {
		position: relative;
	}
	.foot-menu {
		position: absolute;
		bottom: calc(100% + 6px);
		left: 0;
		z-index: 20;
		min-width: 178px;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 11px;
		box-shadow: var(--shadow-panel);
		padding: 5px;
	}
	.foot-menu button {
		display: flex;
		align-items: center;
		gap: 9px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-ui);
		font-size: 12.5px;
		padding: 8px 10px;
		border-radius: 8px;
		cursor: pointer;
	}
	.foot-menu button:hover {
		background: color-mix(in srgb, var(--fg) 7%, transparent);
	}
	.foot-menu button.danger:hover {
		background: color-mix(in srgb, var(--red) 18%, transparent);
		color: #ffd9d4;
	}

	@keyframes msg-enter {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* ---- Composer ---- */
	.composer-zone {
		max-width: 800px;
		width: 100%;
		margin: 0 auto;
		padding: 8px 20px calc(10px + env(safe-area-inset-bottom));
		transition: margin-bottom 0.35s cubic-bezier(0.22, 0.61, 0.36, 1);
	}
	.composer-zone.welcome {
		margin-bottom: 26vh;
	}
	.composer {
		display: flex;
		flex-direction: column;
		gap: 8px;
		background: color-mix(in srgb, var(--panel) 92%, var(--bg));
		border: 1px solid var(--border);
		border-radius: 22px;
		padding: 6px 6px 6px 8px;
		transition: border-color 0.18s;
	}
	.composer:focus-within {
		border-color: color-mix(in srgb, var(--accent) 60%, var(--border));
	}
	.input-row {
		display: flex;
		align-items: flex-end;
		gap: 6px;
		position: relative;
	}
	.plus-menu {
		position: absolute;
		bottom: calc(100% + 8px);
		left: 0;
		z-index: 30;
		min-width: 184px;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 12px;
		box-shadow: var(--shadow-panel);
		padding: 5px;
	}
	.plus-menu button {
		display: flex;
		align-items: center;
		gap: 9px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-ui);
		font-size: 12.5px;
		font-weight: 600;
		padding: 9px 10px;
		border-radius: 8px;
		cursor: pointer;
	}
	.plus-menu button:hover {
		background: color-mix(in srgb, var(--fg) 7%, transparent);
	}
	.slash-menu {
		position: absolute;
		bottom: calc(100% + 8px);
		left: 0;
		right: 0;
		z-index: 30;
		max-height: 280px;
		overflow-y: auto;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 14px;
		box-shadow: var(--shadow-panel);
		padding: 5px;
	}
	.slash-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-ui);
		padding: 8px 11px;
		border-radius: 9px;
		cursor: pointer;
	}
	.slash-item:hover,
	.slash-item.active {
		background: color-mix(in srgb, var(--accent) 14%, transparent);
	}
	.slash-name {
		font-size: 13px;
		font-weight: 600;
		color: var(--accent);
		font-family: var(--font-body);
	}
	.slash-hint {
		color: var(--fg-muted);
		font-weight: 400;
	}
	.slash-cat {
		font-size: 9.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--fg-muted);
		opacity: 0.6;
		padding: 7px 11px 2px;
	}
	.slash-cat:first-child {
		padding-top: 3px;
	}
	.slash-desc {
		font-size: 11.5px;
		color: var(--fg-muted);
	}
	.incognito-pill {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		margin-top: 16px;
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 12px;
		padding: 6px 14px;
		border-radius: 999px;
		cursor: pointer;
		transition: color 0.14s, border-color 0.14s, background 0.14s;
	}
	.incognito-pill:hover {
		color: var(--fg);
		border-color: var(--accent);
	}
	.incognito-pill.on {
		color: var(--accent);
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
	}
	.attach-btn {
		flex: none;
		width: 34px;
		height: 34px;
		border-radius: 50%;
		border: none;
		background: transparent;
		color: var(--fg-muted);
		cursor: pointer;
		display: grid;
		place-items: center;
		transition: color 0.15s, background 0.15s;
	}
	.attach-btn:hover:not(:disabled) {
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
	}
	.attach-btn:disabled {
		opacity: 0.35;
		cursor: default;
	}
	.web-btn {
		flex: none;
		width: 34px;
		height: 34px;
		border-radius: 50%;
		border: 1px solid transparent;
		background: transparent;
		color: var(--fg-muted);
		cursor: pointer;
		display: grid;
		place-items: center;
		transition: color 0.15s, background 0.15s, border-color 0.15s;
	}
	.web-btn:hover:not(:disabled) {
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
	}
	.web-btn.on {
		color: var(--accent);
		border-color: color-mix(in srgb, var(--accent) 45%, transparent);
		background: color-mix(in srgb, var(--accent) 16%, transparent);
	}
	.web-btn:disabled {
		opacity: 0.35;
		cursor: default;
	}
	textarea {
		flex: 1;
		resize: none;
		background: transparent;
		border: none;
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 14.5px;
		line-height: 1.45;
		padding: 8px 2px;
		max-height: 200px;
		outline: none;
	}
	textarea::placeholder {
		color: var(--fg-muted);
	}
	.send-btn {
		flex: none;
		width: 34px;
		height: 34px;
		border-radius: 50%;
		border: none;
		background: var(--accent);
		color: var(--panel-2);
		cursor: pointer;
		display: grid;
		place-items: center;
		transition: background 0.15s, transform 0.05s, opacity 0.15s;
	}
	.send-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.send-btn:active:not(:disabled) {
		transform: scale(0.92);
	}
	.send-btn:disabled {
		opacity: 0.3;
		cursor: default;
	}

	.image-chip {
		position: relative;
		width: fit-content;
		margin: 4px 0 0 6px;
	}
	.image-chip img {
		max-height: 80px;
		max-width: 150px;
		border-radius: 10px;
		border: 1px solid var(--border);
		display: block;
	}
	.chip-remove {
		position: absolute;
		top: -7px;
		right: -7px;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		border: none;
		background: var(--panel-2);
		color: var(--fg-strong);
		font-size: 14px;
		cursor: pointer;
		box-shadow: 0 0 0 1px var(--border);
	}
	.chip-remove:hover {
		background: var(--red);
	}
	.msg-image {
		max-width: 100%;
		max-height: 320px;
		border-radius: 10px;
		margin-bottom: 8px;
		display: block;
	}
	/* Chip de ficheiro de texto/código anexado (preview no composer). */
	.file-chip {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		position: relative;
		width: fit-content;
		max-width: 100%;
		margin: 4px 0 0 6px;
		padding: 6px 12px 6px 10px;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: color-mix(in srgb, var(--accent) 8%, transparent);
		color: var(--fg-strong);
		font-size: 12.5px;
	}
	.file-name {
		max-width: 220px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* Chip do ficheiro dentro de uma mensagem já enviada. */
	.msg-file {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 8px;
		padding: 4px 10px;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-family: var(--font-ui);
		font-size: 12px;
		color: var(--fg-muted);
	}

	/* ---- Rodapé: modelo + contexto (estilo ChatGPT) ---- */
	.meta-foot {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 14px;
		padding: 8px 0 2px;
		font-size: 11px;
		color: var(--fg-muted);
	}
	.model-picker {
		position: relative;
	}
	.model-pill {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 999px;
		padding: 3px 9px;
		color: var(--fg);
		font-family: var(--font-ui);
		font-size: 11.5px;
		cursor: pointer;
		transition: border-color 0.14s, background 0.14s;
	}
	.model-pill:hover {
		border-color: var(--border);
		background: color-mix(in srgb, var(--fg) 5%, transparent);
	}
	.mp-name {
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.model-menu {
		position: absolute;
		bottom: calc(100% + 6px);
		left: 50%;
		transform: translateX(-50%);
		z-index: 30;
		min-width: 230px;
		max-height: 320px;
		overflow-y: auto;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: 12px;
		box-shadow: var(--shadow-panel);
		padding: 5px;
	}
	.model-opt {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font-family: var(--font-ui);
		font-size: 12px;
		padding: 8px 10px;
		border-radius: 8px;
		cursor: pointer;
		white-space: nowrap;
	}
	.model-opt:hover {
		background: color-mix(in srgb, var(--fg) 7%, transparent);
	}
	.model-opt.on {
		color: var(--accent);
	}
	.ctx {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.ctx-ring {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: conic-gradient(
			var(--accent) calc(var(--p) * 1%),
			color-mix(in srgb, var(--fg) 18%, transparent) 0
		);
		-webkit-mask: radial-gradient(circle 3px at center, transparent 96%, #000 0);
		mask: radial-gradient(circle 3px at center, transparent 96%, #000 0);
	}

	.answer {
		white-space: pre-wrap;
	}
	.streaming-md {
		position: relative;
	}
	.streaming-md :global(.md) {
		display: inline;
	}
	.streaming-md :global(.md p:last-child) {
		display: inline;
	}
	.streaming-md > .caret {
		display: inline-block;
		width: 0.55ch;
		height: 1.1em;
		margin-left: 2px;
		vertical-align: -0.15em;
		background: var(--accent);
		border-radius: 1px;
		animation: pen-caret 1s steps(1) infinite;
	}

	/* Status bar (B5) */
	.status-group {
		display: inline-flex;
		align-items: center;
		gap: 12px;
	}
	.st-tps,
	.st-queue {
		font-size: 11px;
		color: var(--fg-muted);
	}
	.st-queue {
		color: var(--accent);
	}
	.st-health {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 11px;
		color: var(--fg-muted);
	}
	.st-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--green, #50c878);
		box-shadow: 0 0 6px var(--green, #50c878);
	}
	.st-health.bad .st-dot {
		background: var(--red);
		box-shadow: 0 0 6px var(--red);
	}
	.drop-overlay {
		position: absolute;
		inset: 0;
		z-index: 50;
		display: grid;
		place-items: center;
		background: color-mix(in srgb, var(--accent) 10%, transparent);
		border: 2px dashed var(--accent);
		border-radius: 14px;
		pointer-events: none;
		font-size: 14px;
		font-weight: 600;
		color: var(--accent);
		backdrop-filter: blur(2px);
	}
</style>
