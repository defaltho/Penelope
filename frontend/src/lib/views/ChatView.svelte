<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { streamChat } from '$lib/chat';
	import Icon from '$lib/components/Icon.svelte';
	import ModelBadge from '$lib/components/ModelBadge.svelte';
	import { getMessages, listModels, getSettings, imageUrl } from '$lib/api';

	let {
		openConvoId = null,
		conversationId = $bindable(null),
		newSignal = 0,
		onConversationsChanged = () => {}
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

	onMount(async () => {
		try {
			const [mdls, settings] = await Promise.all([
				listModels().then((m) => m.filter((x) => !x.includes('embed'))),
				getSettings()
			]);
			models = mdls;
			selectedModel = settings.chat_model || mdls[0] || '';
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
					image: m.image_path ? imageUrl(m.image_path) : undefined
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

	async function send(textOverride?: string) {
		const text = (textOverride ?? input).trim();
		const image = textOverride ? null : pendingImage;
		if ((!text && !image) || streaming) return;

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
					conversationId = id;
					streaming = false;
					const secs = startedAt ? (performance.now() - startedAt) / 1000 : 0;
					if (secs > 0 && tokens > 1) messages[idx].tokPerSec = tokens / secs;
					onConversationsChanged();
				},
				onError: (msg) => {
					errorMsg = msg;
					streaming = false;
					if (messages[idx]?.content === '') messages.splice(idx, 1);
				}
			},
			image,
			selectedModel
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

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
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
			{#if !hasMessages}
				<div class="welcome-screen">
					<div class="wmark"><span class="dot"></span></div>
					<h1>penelope<span class="caret"></span></h1>
					<p>assistente local. lembro-me do que importa.</p>
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
						{#if m.content}{m.content}{:else if streaming && i === messages.length - 1}<span
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
		<div class="composer">
			{#if pendingImage}
				<div class="image-chip">
					<img src={pendingImage} alt="pré-visualização" />
					<button class="chip-remove" onclick={() => (pendingImage = null)} aria-label="remover">×</button>
				</div>
			{/if}
			<div class="input-row">
				<input bind:this={fileInput} type="file" accept="image/*" onchange={onPickFile} hidden />
				<button
					class="attach-btn"
					onclick={() => fileInput.click()}
					disabled={streaming}
					title="anexar imagem"
					aria-label="anexar"
				>
					<Icon name="plus" size={18} />
				</button>
				<textarea
					bind:this={textarea}
					bind:value={input}
					oninput={autoGrow}
					onkeydown={onKeydown}
					placeholder="pergunta alguma coisa…"
					rows="1"
					disabled={streaming}
				></textarea>
				<button
					class="send-btn"
					onclick={() => send()}
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
