/**
 * Slash-commands do compositor de chat.
 *
 * Só DADOS + parsing. A execução vive no ChatView (`runCommand`).
 */

export interface SlashCommand {
	name: string;
	hint?: string;
	desc: string;
	takesArg?: boolean;
}

export const COMMANDS: SlashCommand[] = [
	{ name: 'help', desc: 'Mostra os comandos disponíveis.' },
	{ name: 'new', desc: 'Começa uma conversa nova.' },
	{ name: 'search', hint: '<texto>', desc: 'Pesquisa na web e responde (requer internet).', takesArg: true },
	{ name: 'image', desc: 'Anexa uma imagem.' },
	{ name: 'retry', desc: 'Regenera a última resposta.' },
	{ name: 'clear', desc: 'Limpa o ecrã da conversa atual.' },
	{ name: 'compact', desc: 'Resume e compacta o contexto da conversa.' },
	{ name: 'model', hint: '[nome]', desc: 'Troca o modelo.', takesArg: true },
	{ name: 'incognito', desc: 'Alterna o modo anónimo.' },
	{ name: 'think', desc: 'Alterna mostrar o raciocínio do modelo.' },
];

export function matchCommands(input: string): SlashCommand[] {
	if (!input.startsWith('/')) return [];
	const frag = input.slice(1);
	if (frag.includes(' ')) return [];
	const f = frag.toLowerCase();
	return COMMANDS.filter((c) => c.name.startsWith(f));
}

export function parseCommand(input: string): { name: string; rest: string } | null {
	if (!input.startsWith('/')) return null;
	const m = input.slice(1).match(/^(\S+)\s*([\s\S]*)$/);
	if (!m) return null;
	const name = m[1].toLowerCase();
	return { name, rest: m[2].trim() };
}

export function helpText(): string {
	const lines = COMMANDS.map(
		(c) => `/${c.name}${c.hint ? ' ' + c.hint : ''} : ${c.desc}`
	);
	return 'Comandos disponíveis:\n' + lines.join('\n');
}
