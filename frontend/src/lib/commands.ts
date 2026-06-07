/**
 * Slash-commands do compositor de chat (estilo Claude Code / AI Dungeon).
 *
 * Este módulo é só DADOS + parsing. A execução de cada comando vive no
 * ChatView (`runCommand`), porque depende do estado da vista (modelo, modo
 * anónimo, aventura ativa, etc.). Assim mantém-se desacoplado e fácil de testar.
 *
 * Os comandos têm `scope`:
 *   - 'global'    -> só no chat normal
 *   - 'adventure' -> só dentro do modo /aidungeon (subcomandos estilo AI Dungeon)
 *   - 'both'      -> em qualquer um
 *
 * Nota: a system message do Mestre-de-Jogo e o sampler do Harbinger são tratados
 * no backend (config.adventure_system_prompt + /adventures/{id}/turn); o frontend
 * já não envia o system prompt do jogo.
 */

export type CommandScope = 'global' | 'adventure' | 'both';

export interface SlashCommand {
	/** Nome sem a barra (ex.: "fazer"). */
	name: string;
	/** Dica dos argumentos a mostrar no menu (ex.: "<texto>"). */
	hint?: string;
	/** Descrição curta para o menu e para /ajuda. */
	desc: string;
	/** Onde o comando é válido. */
	scope: CommandScope;
	/** Se true, selecionar no menu preenche o input em vez de executar logo. */
	takesArg?: boolean;
}

export const COMMANDS: SlashCommand[] = [
	// --- Globais (chat normal) ---
	{ name: 'help', desc: 'Mostra os comandos disponíveis.', scope: 'global' },
	{ name: 'aidungeon', hint: '[continuar]', desc: 'Entra no modo aventura (AI Dungeon).', scope: 'global' },
	{ name: 'new', desc: 'Começa uma conversa nova.', scope: 'global' },
	{ name: 'search', hint: '<texto>', desc: 'Pesquisa na web e responde (requer internet).', scope: 'global', takesArg: true },
	{ name: 'image', desc: 'Anexa uma imagem.', scope: 'global' },
	{ name: 'retry', desc: 'Regenera a última resposta.', scope: 'global' },
	// --- Em qualquer modo ---
	{ name: 'model', hint: '[nome]', desc: 'Troca o modelo.', scope: 'both', takesArg: true },
	{ name: 'incognito', desc: 'Alterna o modo anónimo.', scope: 'both' },
	{ name: 'think', desc: 'Alterna mostrar o raciocínio do modelo.', scope: 'both' },
	// --- Aventura (subcomandos, estilo AI Dungeon) ---
	{ name: 'fazer', hint: '<ação>', desc: 'Modo Do: a tua personagem faz uma ação.', scope: 'adventure', takesArg: true },
	{ name: 'dizer', hint: '<fala>', desc: 'Modo Say: a tua personagem fala.', scope: 'adventure', takesArg: true },
	{ name: 'historia', hint: '<texto>', desc: 'Modo Story: escreves narração e o MJ responde-lhe.', scope: 'adventure', takesArg: true },
	{ name: 'continuar', desc: 'O Mestre-de-Jogo avança sem tu agires.', scope: 'adventure' },
	{ name: 'repetir', desc: 'Retry: regenera a última narração.', scope: 'adventure' },
	{ name: 'retroceder', desc: 'Undo: apaga o último passo da história.', scope: 'adventure' },
	{ name: 'refazer', desc: 'Redo: repõe o passo desfeito.', scope: 'adventure' },
	{ name: 'editar', desc: 'Edita o texto da última narração.', scope: 'adventure' },
	{ name: 'lembrar', hint: '<texto>', desc: 'Memória: facto que o MJ deve manter sempre.', scope: 'adventure', takesArg: true },
	{ name: 'nota', hint: '<texto>', desc: 'Nota de autor: orienta o estilo/foco.', scope: 'adventure', takesArg: true },
	{ name: 'cartao', hint: '<gatilho> | <texto>', desc: 'Story Card: contexto acionado por palavra-chave.', scope: 'adventure', takesArg: true },
	{ name: 'cenario', desc: 'Mostra o cenário/contexto atual.', scope: 'adventure' },
	{ name: 'guardar', hint: '[título]', desc: 'Guarda/renomeia a aventura.', scope: 'adventure', takesArg: true },
	{ name: 'aventuras', desc: 'Abre a lista de aventuras guardadas.', scope: 'adventure' },
	{ name: 'sair', desc: 'Sai do modo aventura.', scope: 'adventure' },
	{ name: 'ajuda', desc: 'Mostra os comandos da aventura.', scope: 'adventure' }
];

/** Aliases (PT + EN do AI Dungeon) que não aparecem no menu mas funcionam. */
const ALIASES: Record<string, string> = {
	clear: 'new',
	exit: 'sair',
	do: 'fazer',
	say: 'dizer',
	story: 'historia',
	continue: 'continuar',
	undo: 'retroceder',
	redo: 'refazer',
	edit: 'editar',
	remember: 'lembrar',
	note: 'nota',
	card: 'cartao',
	save: 'guardar',
	scene: 'cenario',
	adventures: 'aventuras'
};

/** Comandos visíveis no modo atual (aventura mostra adventure+both; normal mostra global+both). */
export function visibleCommands(inAdventure: boolean): SlashCommand[] {
	return COMMANDS.filter((c) =>
		inAdventure ? c.scope !== 'global' : c.scope !== 'adventure'
	);
}

/** Comandos que correspondem ao que está a ser escrito (só enquanto se digita o nome). */
export function matchCommands(input: string, inAdventure = false): SlashCommand[] {
	if (!input.startsWith('/')) return [];
	const frag = input.slice(1);
	if (frag.includes(' ')) return []; // já passámos o nome do comando
	const f = frag.toLowerCase();
	return visibleCommands(inAdventure).filter((c) => c.name.startsWith(f));
}

/** Separa "/cmd resto..." em { name, rest }. Resolve aliases. */
export function parseCommand(input: string): { name: string; rest: string } | null {
	if (!input.startsWith('/')) return null;
	const m = input.slice(1).match(/^(\S+)\s*([\s\S]*)$/);
	if (!m) return null;
	const name = m[1].toLowerCase();
	return { name: ALIASES[name] ?? name, rest: m[2].trim() };
}

/** Texto de ajuda gerado a partir do registo, conforme o modo. */
export function helpText(inAdventure = false): string {
	const lines = visibleCommands(inAdventure).map(
		(c) => `/${c.name}${c.hint ? ' ' + c.hint : ''} : ${c.desc}`
	);
	const head = inAdventure ? 'Comandos da aventura:' : 'Comandos disponíveis:';
	return head + '\n' + lines.join('\n');
}
