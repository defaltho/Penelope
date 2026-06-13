/**
 * Cliente SSE do chat. O endpoint /chat do backend é POST (sse-starlette), por
 * isso não dá para usar o EventSource nativo do browser (só faz GET). Lemos o
 * corpo da resposta como stream e parseamos os blocos SSE à mão.
 *
 * Eventos emitidos pelo backend:
 *   event: token  -> { token: string }      (incremento de texto)
 *   event: error  -> { error: string }      (falha no Ollama)
 *   event: done   -> { conversation_id: int } (fim; id da conversa)
 */

export interface ChatCallbacks {
	onToken: (token: string) => void;
	onDone: (conversationId: number) => void;
	onError: (message: string) => void;
	// Eventos de progresso em tempo real (B2): kind ex.: 'web'|'memory'|'thinking'.
	onStatus?: (kind: string, text: string) => void;
}

/** Faz o pedido e encaminha cada evento para o callback respetivo. */
export async function streamChat(
	message: string,
	conversationId: number | null,
	cb: ChatCallbacks,
	imageBase64?: string | null,
	model?: string | null,
	incognito?: boolean,
	webSearch?: boolean,
	systemOverride?: string | null,
	signal?: AbortSignal
): Promise<void> {
	let res: Response;
	try {
		res = await fetch('/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				message,
				conversation_id: conversationId,
				image_base64: imageBase64 ?? null,
				model: model ?? null,
				incognito: !!incognito,
				web_search: !!webSearch,
				system_override: systemOverride ?? null
			}),
			signal
		});
	} catch (e) {
		cb.onError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
		return;
	}

	if (!res.ok || !res.body) {
		cb.onError(`HTTP ${res.status}`);
		return;
	}

	await readSSE(res, (block) => dispatch(block, cb), (msg) => cb.onError(msg));
}

/** Lê o corpo SSE (POST) bloco a bloco, normalizando o CRLF do sse-starlette. */
async function readSSE(
	res: Response,
	onBlock: (block: string) => void,
	onError: (message: string) => void
): Promise<void> {
	const reader = res.body!.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			buffer = buffer.replace(/\r\n/g, '\n');
			let sep: number;
			while ((sep = buffer.indexOf('\n\n')) !== -1) {
				const block = buffer.slice(0, sep);
				buffer = buffer.slice(sep + 2);
				onBlock(block);
			}
		}
	} catch (e) {
		if ((e as Error)?.name === 'AbortError') return;
		onError(`Stream interrompido: ${e instanceof Error ? e.message : String(e)}`);
	}
}

/** Parseia um bloco SSE em { event, payload }. */
function parseBlock(block: string): { event: string; payload: any } {
	let event = 'message';
	const dataLines: string[] = [];
	for (const line of block.split('\n')) {
		if (line.startsWith('event:')) event = line.slice(6).trim();
		else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
	}
	if (dataLines.length === 0) return { event, payload: null };
	try {
		return { event, payload: JSON.parse(dataLines.join('\n')) };
	} catch {
		return { event, payload: null };
	}
}

function dispatch(block: string, cb: ChatCallbacks): void {
	const { event, payload } = parseBlock(block);
	if (!payload) return;
	if (event === 'token') cb.onToken(payload.token ?? '');
	else if (event === 'done') cb.onDone(payload.conversation_id);
	else if (event === 'error') cb.onError(payload.error ?? 'erro desconhecido');
	else if (event === 'status') cb.onStatus?.(payload.kind ?? '', payload.text ?? '');
}
