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
}

/** Faz o pedido e encaminha cada evento para o callback respetivo. */
export async function streamChat(
	message: string,
	conversationId: number | null,
	cb: ChatCallbacks,
	imageBase64?: string | null,
	model?: string | null,
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
				model: model ?? null
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

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			// O sse-starlette emite CRLF; normalizar para LF antes de dividir.
			buffer = buffer.replace(/\r\n/g, '\n');

			// Os eventos SSE são separados por uma linha em branco.
			let sep: number;
			while ((sep = buffer.indexOf('\n\n')) !== -1) {
				const block = buffer.slice(0, sep);
				buffer = buffer.slice(sep + 2);
				dispatch(block, cb);
			}
		}
	} catch (e) {
		if ((e as Error)?.name === 'AbortError') return;
		cb.onError(`Stream interrompido: ${e instanceof Error ? e.message : String(e)}`);
	}
}

function dispatch(block: string, cb: ChatCallbacks): void {
	let event = 'message';
	const dataLines: string[] = [];
	for (const line of block.split('\n')) {
		if (line.startsWith('event:')) event = line.slice(6).trim();
		else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
	}
	if (dataLines.length === 0) return;

	let payload: any;
	try {
		payload = JSON.parse(dataLines.join('\n'));
	} catch {
		return;
	}

	if (event === 'token') cb.onToken(payload.token ?? '');
	else if (event === 'done') cb.onDone(payload.conversation_id);
	else if (event === 'error') cb.onError(payload.error ?? 'erro desconhecido');
}
