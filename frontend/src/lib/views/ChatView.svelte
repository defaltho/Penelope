<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { streamChat, streamAdventureTurn } from '$lib/chat';
	import Icon from '$lib/components/Icon.svelte';
	import ModelBadge from '$lib/components/ModelBadge.svelte';
	import AdventureSetup from '$lib/components/AdventureSetup.svelte';
	import {
		getMessages,
		listModels,
		getSettings,
		imageUrl,
		createAdventure,
		getAdventure,
		patchAdventure,
		type Adventure,
		type AdventureMode,
		type AdventureTurnEntry
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
		openAdventureId = null,
		onConversationsChanged = () => {},
		onOpenAdventures = () => {}
	}: {
		openConvoId?: number | null;
		conversationId?: number | null;
		newSignal?: number;
		openAdventureId?: string | null;
		onConversationsChanged?: () => void;
		onOpenAdventures?: () => void;
	} = $props();

	interface Msg {
		role: 'user' | 'assistant';
		content: string;
		image?: string;
		model?: string;
		tokPerSec?: number;
	}

	let messages = $state<Msg[]>([]);
	let input = $state('');
	let streaming = $state(false);
	let errorMsg = $state<string | null>(null);
	let pendingImage = $state<string | null>(null);

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

	// Modo aventura (/aidungeon, estilo AI Dungeon) + slash-commands.
	let adventureMode = $state(false);
	let adventureId = $state<string | null>(null);
	let advTurns = $state<AdventureTurnEntry[]>([]); // espelho dos turnos do backend
	let advInfo = $state<{
		title: string;
		scenario: string;
		memory: string;
		authors_note: string;
		model: string;
	} | null>(null);
	let inputMode = $state<'do' | 'say' | 'story'>('do'); // Do/Say/Story
	let redoStack = $state<AdventureTurnEntry[][]>([]); // para /refazer
	let setupOpen = $state(false); // modal Nova/Continuar
	let setupStage = $state<'world' | 'hero' | null>(null); // perguntas híbridas no chat
	let setupWorld = $state('');
	let adventureModel = $state('');
	let adventureFallback = $state('');
	let slashIndex = $state(0);
	let slashHidden = $state(false);
	const slashMatches = $derived(matchCommands(input, adventureMode));
	const slashMenuOpen = $derived(!slashHidden && slashMatches.length > 0);
	$effect(() => {
		// Reset do índice destacado sempre que a lista de sugestões muda.
		slashMatches.length;
		slashIndex = 0;
	});

	const EMOJI_RE =
		/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{FE0F}\u{200D}]/gu;
	function displayContent(c: string): string {
		let out = c;
		if (!uiThinking) out = out.replace(/<think>[\s\S]*?<\/think>/gi, '').trimStart();
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

	let lastAdv = $state<string | null>(null);
	$effect(() => {
		if (openAdventureId && openAdventureId !== lastAdv) {
			lastAdv = openAdventureId;
			continueAdventure(openAdventureId);
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
			adventureModel = settings.adventure_model || '';
			adventureFallback = settings.adventure_model_fallback || '';
		} catch (e) {
			console.error('falha a obter modelos', e);
		}
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

	function onPickFile(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0];
		if (!file) return;
		if (!file.type.startsWith('image/')) {
			errorMsg = 'só são suportadas imagens';
			return;
		}
		const reader = new FileReader();
		reader.onload = () => (pendingImage = reader.result as string);
		reader.readAsDataURL(file);
		fileInput.value = '';
	}

	async function send(textOverride?: string, forceWeb = false) {
		const text = (textOverride ?? input).trim();
		const image = textOverride ? null : pendingImage;
		if ((!text && !image) || streaming) return;

		const useWeb = (forceWeb || webSearch) && internetOn;

		errorMsg = null;
		messages.push({ role: 'user', content: text, image: image ?? undefined });
		if (!textOverride) input = '';
		pendingImage = null;
		autoGrow();

		const idx = messages.push({ role: 'assistant', content: '', model: selectedModel }) - 1;
		streaming = true;
		let tokens = 0;
		let startedAt = 0;
		await scrollToBottom();

		await streamChat(
			text,
			conversationId,
			{
				onToken: (t) => {
					if (startedAt === 0) startedAt = performance.now();
					tokens += 1;
					messages[idx].content += t;
					scrollToBottom();
				},
				onDone: (id) => {
					streaming = false;
					const secs = startedAt ? (performance.now() - startedAt) / 1000 : 0;
					if (secs > 0 && tokens > 1) messages[idx].tokPerSec = tokens / secs;
					// Anónimo: id vem null; não fixa conversa nem refresca a sidebar.
					if (id != null) {
						conversationId = id;
						onConversationsChanged();
					}
				},
				onError: (msg) => {
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
		exitAdventureState();
		autoGrow();
		textarea?.focus();
	}

	/** Repõe o estado interno do modo aventura (sem mensagem). */
	function exitAdventureState() {
		adventureMode = false;
		adventureId = null;
		advTurns = [];
		advInfo = null;
		redoStack = [];
		setupOpen = false;
		setupStage = null;
		setupWorld = '';
		inputMode = 'do';
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
		// Setup híbrido: capturar as respostas às perguntas no chat.
		if (setupStage) {
			input = '';
			autoGrow();
			handleSetupAnswer(text);
			return;
		}
		// Modo aventura: o texto livre é um turno no modo selecionado (Do/Say/Story).
		if (adventureMode) {
			if (!text || streaming) return;
			input = '';
			autoGrow();
			runAdventureTurn(text, inputMode);
			return;
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

	// ---- Modo aventura (AI Dungeon) ----

	/** Reconstrói as mensagens visíveis a partir do espelho de turnos do backend. */
	function renderAdventure() {
		messages = advTurns.map((t) => ({
			role: t.role,
			content: t.content,
			model: t.role === 'assistant' ? advInfo?.model || 'AI Dungeon' : undefined
		}));
	}

	/** Avisa se o modelo de aventura configurado não está instalado (usa-se o fallback). */
	function adventureModelHint() {
		if (adventureModel && !models.includes(adventureModel)) {
			pushInfo(
				`Nota: o modelo de aventura "${adventureModel}" não está instalado. Corre no terminal:\n  ollama pull ${adventureModel}\nEntretanto uso o de reserva "${adventureFallback || selectedModel}".`
			);
		}
	}

	/** /aidungeon: abre o setup, ou sai se o argumento for "sair". */
	function openAdventure(rest: string) {
		if (['sair', 'exit', 'parar', 'stop'].includes(rest.toLowerCase())) {
			if (adventureMode) exitAdventure();
			return;
		}
		setupOpen = true;
	}

	/** Modal -> "Nova aventura": começa as perguntas híbridas no chat. */
	function onSetupNew() {
		setupOpen = false;
		messages = [];
		setupWorld = '';
		setupStage = 'world';
		pushInfo('Vamos criar uma aventura. Em uma frase, que mundo ou cenário queres viver?');
		textarea?.focus();
	}

	/** Recebe a resposta de cada pergunta do setup híbrido. */
	function handleSetupAnswer(text: string) {
		if (!text) return;
		if (setupStage === 'world') {
			setupWorld = text;
			setupStage = 'hero';
			pushInfo('E quem és tu nesta história? (o teu protagonista, em poucas palavras)');
			return;
		}
		if (setupStage === 'hero') {
			const hero = text;
			setupStage = null;
			const scenario = `Mundo: ${setupWorld}\nProtagonista: ${hero}`;
			const title = setupWorld.slice(0, 48);
			startAdventure(title, scenario);
		}
	}

	/** Cria a aventura no backend e gera a abertura (turno "continue"). */
	async function startAdventure(title: string, scenario: string) {
		try {
			const adv = await createAdventure({ title, scenario });
			enterAdventure(adv);
			adventureModelHint();
			pushInfo('A tecer o teu mundo…');
			await runAdventureTurn('', 'continue');
		} catch (e) {
			errorMsg = 'falha a criar a aventura';
			setupStage = null;
		}
	}

	/** Carrega uma aventura existente e entra no modo (a partir da lista/setup). */
	async function continueAdventure(id: string) {
		try {
			const adv = await getAdventure(id);
			enterAdventure(adv);
			renderAdventure();
			adventureModelHint();
			await scrollToBottom();
		} catch (e) {
			errorMsg = 'falha a carregar a aventura';
		}
	}

	function enterAdventure(adv: Adventure) {
		adventureId = adv.id;
		adventureMode = true;
		advTurns = adv.turns ?? [];
		advInfo = {
			title: adv.title,
			scenario: adv.scenario,
			memory: adv.memory,
			authors_note: adv.authors_note,
			model: adv.model
		};
		redoStack = [];
		inputMode = 'do';
		conversationId = null;
		messages = [];
		setupOpen = false;
		setupStage = null;
	}

	/** Enquadra o input do jogador (tem de bater certo com o backend `_mode_frame`). */
	function frameInput(text: string, mode: AdventureMode): string {
		if (mode === 'say') return `> Dizes: "${text}"`;
		if (mode === 'story') return text;
		return `> ${text}`; // do
	}

	async function runAdventureTurn(rawInput: string, mode: AdventureMode) {
		if (!adventureId || streaming) return;
		errorMsg = null;
		redoStack = [];
		const isContinue = mode === 'continue';
		if (!isContinue) {
			advTurns.push({ role: 'user', mode, content: frameInput(rawInput, mode), ts: new Date().toISOString() });
			renderAdventure();
		}
		const idx = messages.push({ role: 'assistant', content: '', model: advInfo?.model || 'AI Dungeon' }) - 1;
		streaming = true;
		await scrollToBottom();

		await streamAdventureTurn(adventureId, rawInput, mode, {
			onToken: (t) => {
				messages[idx].content += t;
				scrollToBottom();
			},
			onDone: () => {
				streaming = false;
				advTurns.push({
					role: 'assistant',
					mode,
					content: messages[idx].content,
					ts: new Date().toISOString()
				});
				renderAdventure();
			},
			onError: (msg) => {
				errorMsg = msg;
				streaming = false;
				if (!isContinue) advTurns.pop(); // reverte o turno não persistido
				renderAdventure();
			}
		});
	}

	/** /repetir (Retry): apaga a última narração e regenera a partir da mesma ação. */
	async function retryAdventure() {
		if (!adventureId || streaming) return;
		if (!advTurns.some((t) => t.role === 'assistant')) {
			pushInfo('Ainda não há nada para repetir.');
			return;
		}
		// remover a última narração
		for (let i = advTurns.length - 1; i >= 0; i--) {
			if (advTurns[i].role === 'assistant') {
				advTurns.splice(i, 1);
				break;
			}
		}
		try {
			await patchAdventure(adventureId, { turns: advTurns });
		} catch (e) {
			errorMsg = 'falha a repetir';
			return;
		}
		renderAdventure();
		await runAdventureTurn('', 'continue');
	}

	/** /retroceder (Undo): apaga o último passo (narração + ação que a despoletou). */
	async function undoAdventure() {
		if (!adventureId || streaming || advTurns.length === 0) return;
		const removed: AdventureTurnEntry[] = [];
		if (advTurns[advTurns.length - 1].role === 'assistant') removed.unshift(advTurns.pop()!);
		if (advTurns.length && advTurns[advTurns.length - 1].role === 'user') removed.unshift(advTurns.pop()!);
		if (removed.length === 0) return;
		redoStack.push(removed);
		try {
			await patchAdventure(adventureId, { turns: advTurns });
		} catch (e) {
			errorMsg = 'falha a retroceder';
			return;
		}
		renderAdventure();
	}

	/** /refazer (Redo): repõe o último passo desfeito. */
	async function redoAdventure() {
		if (!adventureId || streaming || redoStack.length === 0) return;
		const group = redoStack.pop()!;
		advTurns.push(...group);
		try {
			await patchAdventure(adventureId, { turns: advTurns });
		} catch (e) {
			errorMsg = 'falha a refazer';
			return;
		}
		renderAdventure();
	}

	/** /editar: edita o texto da última narração. */
	async function editLastNarration() {
		if (!adventureId || streaming) return;
		let i = advTurns.length - 1;
		while (i >= 0 && advTurns[i].role !== 'assistant') i--;
		if (i < 0) return;
		const novo = window.prompt('Editar a última narração:', advTurns[i].content);
		if (novo == null) return;
		advTurns[i].content = novo;
		try {
			await patchAdventure(adventureId, { turns: advTurns });
		} catch (e) {
			errorMsg = 'falha a editar';
			return;
		}
		renderAdventure();
	}

	async function setAdventureField(field: 'memory' | 'authors_note' | 'title', value: string) {
		if (!adventureId || !advInfo) return;
		try {
			await patchAdventure(adventureId, { [field]: value } as any);
			(advInfo as any)[field === 'title' ? 'title' : field] = value;
		} catch (e) {
			errorMsg = 'falha a guardar';
		}
	}

	async function addStoryCard(rest: string) {
		if (!adventureId) return;
		const [keysPart, ...txt] = rest.split('|');
		const keys = keysPart.split(',').map((k) => k.trim()).filter(Boolean);
		const text = txt.join('|').trim();
		if (keys.length === 0 || !text) {
			pushInfo('Uso: /cartao <gatilho1, gatilho2> | <texto>');
			return;
		}
		try {
			const adv = await getAdventure(adventureId);
			const cards = [...(adv.story_cards ?? []), { keys, text }];
			await patchAdventure(adventureId, { story_cards: cards });
			pushInfo(`Story Card criado (gatilhos: ${keys.join(', ')}).`);
		} catch (e) {
			errorMsg = 'falha a criar o cartão';
		}
	}

	function showScenario() {
		if (!advInfo) return;
		const parts = [`Título: ${advInfo.title}`, `Modelo: ${advInfo.model || '(reserva)'}`];
		if (advInfo.scenario) parts.push('\nCenário:\n' + advInfo.scenario);
		if (advInfo.memory) parts.push('\nMemória:\n' + advInfo.memory);
		if (advInfo.authors_note) parts.push('\nNota de autor:\n' + advInfo.authors_note);
		pushInfo(parts.join('\n'));
	}

	function exitAdventure() {
		exitAdventureState();
		pushInfo('Saíste da aventura. Fica guardada na aba Aventuras.');
	}

	/** Subcomando de modo (Do/Say/Story): muda o modo e, se houver texto, joga já. */
	function adventureCmd(rest: string, mode: 'do' | 'say' | 'story') {
		if (!adventureMode) {
			errorMsg = 'Entra no modo aventura com /aidungeon.';
			return;
		}
		inputMode = mode;
		if (rest) runAdventureTurn(rest, mode);
		else textarea?.focus();
	}

	function runCommand(name: string, rest: string) {
		input = '';
		slashHidden = false;
		autoGrow();
		switch (name) {
			case 'help':
				pushInfo(helpText(adventureMode));
				break;
			case 'ajuda':
				pushInfo(helpText(true));
				break;
			case 'aidungeon':
				openAdventure(rest);
				break;
			case 'new':
				newConversation();
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
				if (adventureMode) retryAdventure();
				else regenerate(messages.length);
				break;
			// --- Subcomandos de aventura (estilo AI Dungeon) ---
			case 'fazer':
				adventureCmd(rest, 'do');
				break;
			case 'dizer':
				adventureCmd(rest, 'say');
				break;
			case 'historia':
				adventureCmd(rest, 'story');
				break;
			case 'continuar':
				if (adventureMode) runAdventureTurn('', 'continue');
				break;
			case 'repetir':
				retryAdventure();
				break;
			case 'retroceder':
				undoAdventure();
				break;
			case 'refazer':
				redoAdventure();
				break;
			case 'editar':
				editLastNarration();
				break;
			case 'lembrar':
				if (rest && advInfo) {
					const mem = (advInfo.memory ? advInfo.memory + '\n' : '') + rest;
					setAdventureField('memory', mem);
					pushInfo('Memória da história atualizada.');
				}
				break;
			case 'nota':
				if (advInfo) {
					setAdventureField('authors_note', rest);
					pushInfo('Nota de autor atualizada.');
				}
				break;
			case 'cartao':
				addStoryCard(rest);
				break;
			case 'cenario':
				showScenario();
				break;
			case 'guardar':
				if (rest && advInfo) {
					setAdventureField('title', rest);
					pushInfo(`Aventura renomeada para "${rest}".`);
				} else {
					pushInfo('Aventura guardada.');
				}
				break;
			case 'aventuras':
				onOpenAdventures();
				break;
			case 'sair':
				if (adventureMode) exitAdventure();
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

<div class="chat-area">
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
						{#if m.content}{m.role === 'assistant' ? displayContent(m.content) : m.content}{:else if streaming && i === messages.length - 1}<span
								class="dots"><span></span><span></span><span></span></span
							>{/if}
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
		{#if adventureMode}
			<div class="adv-bar">
				<div class="adv-modes" role="group" aria-label="modo de jogada">
					<button class:on={inputMode === 'do'} onclick={() => (inputMode = 'do')} title="Ação (Do)">Fazer</button>
					<button class:on={inputMode === 'say'} onclick={() => (inputMode = 'say')} title="Falar (Say)">Dizer</button>
					<button class:on={inputMode === 'story'} onclick={() => (inputMode = 'story')} title="Narrar (Story)">História</button>
				</div>
				<div class="adv-actions">
					<button class="adv-continue" onclick={() => runAdventureTurn('', 'continue')} disabled={streaming} title="Continuar: o MJ avança">
						<Icon name="play" size={13} /> Continuar
					</button>
					<button onclick={retryAdventure} disabled={streaming} title="Repetir (Retry)" aria-label="Repetir"><Icon name="refresh" size={14} /></button>
					<button onclick={undoAdventure} disabled={streaming} title="Retroceder (Undo)" aria-label="Retroceder"><Icon name="undo" size={14} /></button>
					<button onclick={() => onOpenAdventures()} title="Aventuras guardadas" aria-label="Aventuras"><Icon name="dice" size={14} /></button>
					<button onclick={exitAdventure} title="Sair da aventura" aria-label="Sair"><Icon name="x" size={14} /></button>
				</div>
			</div>
		{/if}
		<div class="composer">
			{#if pendingImage}
				<div class="image-chip">
					<img src={pendingImage} alt="pré-visualização" />
					<button class="chip-remove" onclick={() => (pendingImage = null)} aria-label="remover">×</button>
				</div>
			{/if}
			<div class="input-row">
				<input bind:this={fileInput} type="file" accept="image/*" onchange={onPickFile} hidden />
					{#if slashMenuOpen}
						<div class="slash-menu" role="listbox" tabindex="-1">
							{#each slashMatches as c, i (c.name)}
								<button
									class="slash-item"
									class:active={i === slashIndex}
									onmousedown={(e) => {
										e.preventDefault();
										pickSlash(c);
									}}
								>
									<span class="slash-name">/{c.name}{#if c.hint}<span class="slash-hint"> {c.hint}</span>{/if}</span>
									<span class="slash-desc">{c.desc}</span>
								</button>
							{/each}
						</div>
					{/if}
					{#if plusMenuOpen}
						<div class="plus-menu">
							<button onclick={() => { plusMenuOpen = false; fileInput.click(); }}>
								<Icon name="paperclip" size={14} /> Anexar imagem
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
					title="anexar imagem"
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
					placeholder={adventureMode
						? inputMode === 'say'
							? 'o que dizes… (/ para comandos da aventura)'
							: inputMode === 'story'
								? 'escreve a narração… (/ para comandos)'
								: 'a tua ação… (/ para comandos)'
						: setupStage
							? 'responde para criares a aventura…'
							: 'pergunta alguma coisa…  (/ para comandos)'}
					rows="1"
					disabled={streaming}
				></textarea>
				<button
					class="send-btn"
					onclick={submit}
					disabled={streaming || (input.trim() === '' && !pendingImage)}
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
			<span class="ctx" title="janela de contexto estimada">
				<span class="ctx-ring" style="--p:{contextPct}"></span>{contextPct}% contexto
			</span>
		</div>
	</div>

	{#if setupOpen}
		<AdventureSetup
			onNew={onSetupNew}
			onContinue={(id) => {
				setupOpen = false;
				continueAdventure(id);
			}}
			onClose={() => (setupOpen = false)}
		/>
	{/if}
</div>

<style>
	.chat-area {
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
		font-family: var(--font-body);
		font-size: 14.5px;
		white-space: pre-wrap;
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

	/* ---- Composer simplificado ---- */
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
	.adv-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		flex-wrap: wrap;
		margin-bottom: 8px;
		padding: 0 4px;
	}
	.adv-modes {
		display: inline-flex;
		background: color-mix(in srgb, var(--panel) 92%, var(--bg));
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 3px;
	}
	.adv-modes button {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 12px;
		font-weight: 600;
		padding: 5px 13px;
		border-radius: 999px;
		cursor: pointer;
		transition: color 0.13s, background 0.13s;
	}
	.adv-modes button:hover {
		color: var(--fg);
	}
	.adv-modes button.on {
		color: var(--panel-2);
		background: var(--accent);
	}
	.adv-actions {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.adv-actions button {
		display: inline-grid;
		place-items: center;
		gap: 5px;
		grid-auto-flow: column;
		min-width: 30px;
		height: 30px;
		padding: 0 8px;
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
	.adv-actions button:hover:not(:disabled) {
		color: var(--accent);
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.adv-actions button:disabled {
		opacity: 0.4;
		cursor: default;
	}
	.adv-continue {
		color: var(--fg) !important;
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

	.dots {
		display: inline-flex;
		gap: 4px;
		padding: 4px 0;
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
