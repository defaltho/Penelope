/**
 * Buffer de fluidez de streaming (B1). O Ollama entrega tokens em blocos
 * irregulares (às vezes vários caracteres de uma vez, às vezes pausas); este
 * buffer desacopla a CHEGADA de rede do RENDER, drenando caracteres a um ritmo
 * suave via requestAnimationFrame para um efeito de escrita contínua.
 *
 * Uso:
 *   const buf = new StreamBuffer((chunk) => { messages[idx].content += chunk; });
 *   onToken: (t) => buf.push(t),
 *   onDone:  ()  => buf.flush(),   // despeja o resto de imediato
 *   onError/abort: () => buf.stop(),
 *
 * Respeita prefers-reduced-motion: nesse caso aplica tudo de imediato (sem RAF).
 */
export class StreamBuffer {
	private queue = '';
	private raf: number | null = null;
	private readonly reduced: boolean;

	constructor(private readonly apply: (chunk: string) => void) {
		this.reduced =
			typeof window !== 'undefined' &&
			!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	}

	push(token: string): void {
		if (!token) return;
		if (this.reduced || typeof requestAnimationFrame === 'undefined') {
			this.apply(token);
			return;
		}
		this.queue += token;
		this.ensureLoop();
	}

	/** Despeja imediatamente o que falta (fim do stream). */
	flush(): void {
		this.stop();
		if (this.queue) {
			this.apply(this.queue);
			this.queue = '';
		}
	}

	/** Cancela o loop e descarta a fila (erro/abort). */
	stop(): void {
		if (this.raf !== null && typeof cancelAnimationFrame !== 'undefined') {
			cancelAnimationFrame(this.raf);
		}
		this.raf = null;
	}

	private ensureLoop(): void {
		if (this.raf !== null) return;
		const tick = () => {
			this.raf = null;
			if (!this.queue) return;
			// Ritmo adaptativo: drena ~1/8 do backlog por frame (mínimo 2 chars),
			// para acompanhar respostas rápidas sem ficar a "engasgar".
			const n = Math.max(2, Math.ceil(this.queue.length / 8));
			this.apply(this.queue.slice(0, n));
			this.queue = this.queue.slice(n);
			if (this.queue) this.raf = requestAnimationFrame(tick);
		};
		this.raf = requestAnimationFrame(tick);
	}
}
