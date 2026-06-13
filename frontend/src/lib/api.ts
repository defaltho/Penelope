/** Helpers de API do Penelope (passam pelo proxy /api do Vite). */

export interface ConversationSummary {
	id: number;
	title: string | null;
	created_at: string;
	updated_at: string;
	message_count: number;
	snippet: string;
}

export interface StoredMessage {
	role: 'user' | 'assistant' | 'system';
	content: string;
	image_path: string | null;
	model: string | null;
	tok_per_sec: number | null;
	created_at: string;
}

export interface Fact {
	id: number;
	text: string;
	fact_type: string;
	updated_at: string | null;
}

async function json<T>(res: Response): Promise<T> {
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	return res.json() as Promise<T>;
}

// ---- Conversas ----

export const listConversations = () =>
	fetch('/api/conversations').then(json<ConversationSummary[]>);

export const getMessages = (id: number) =>
	fetch(`/api/conversations/${id}/messages`).then(json<StoredMessage[]>);

export const renameConversation = (id: number, title: string) =>
	fetch(`/api/conversations/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title })
	}).then(json);

export const deleteConversation = (id: number) =>
	fetch(`/api/conversations/${id}`, { method: 'DELETE' }).then(json);

export const compactChat = (conversationId: number) =>
	fetch('/api/chat/compact', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ conversation_id: conversationId })
	}).then(json<{ summary: string; conversation_id: number }>);

// ---- Memória ----

export const listFacts = (q?: string) =>
	fetch('/api/memory/facts' + (q ? `?q=${encodeURIComponent(q)}` : '')).then(json<Fact[]>);

export const editFact = (id: number, text: string) =>
	fetch(`/api/memory/facts/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ text })
	}).then(json);

// Apagar = arquivar (recuperável). O purgar definitivo é uma ação separada.
export const deleteFact = (id: number) =>
	fetch(`/api/memory/facts/${id}`, { method: 'DELETE' }).then(json);

export const listArchivedFacts = () =>
	fetch('/api/memory/facts/archived').then(json<Fact[]>);

export const restoreFact = (id: number) =>
	fetch(`/api/memory/facts/${id}/restore`, { method: 'POST' }).then(json);

export const purgeFact = (id: number) =>
	fetch(`/api/memory/facts/${id}/purge`, { method: 'DELETE' }).then(json);

export const exportFacts = () =>
	fetch('/api/memory/export').then(json<{ text: string; fact_type: string }[]>);
export const importFacts = (facts: { text: string; fact_type?: string }[]) =>
	fetch('/api/memory/import', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ facts })
	}).then(json<{ added: number }>);

// ---- Pesquisa global ----

export interface SearchHit {
	id: number;
	conversation_id: number;
	role: 'user' | 'assistant';
	content: string;
	created_at: string;
	conv_title: string | null;
}

export const searchMessages = (q: string) =>
	fetch('/api/search?q=' + encodeURIComponent(q)).then(json<SearchHit[]>);

// ---- Definições ----

export interface AppSettings {
	chat_model: string;
	dispatch_url: string;
	memory_enabled: boolean;
	skills_enabled: boolean;
	memory_review: boolean;
	skills_auto: boolean;
	temperature: number;
	num_ctx: number;
	max_tokens: number;
	system_extra: string;
	internet_enabled: boolean;
	user_name: string;
	onboarded: boolean;
	ui_anim: boolean;
	ui_welcome: boolean;
	ui_thinking: boolean;
	ui_text_emojis: boolean;
	search_provider: string;
	search_results: number;
	search_url: string;
	tools_disabled: string;
}

export interface WebResult {
	title: string;
	url: string;
	snippet: string;
}
export const searchWeb = (query: string) =>
	fetch('/api/search/web', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ query })
	}).then(json<{ results: WebResult[] }>);

export const exportData = () => fetch('/api/data/export').then(json<unknown>);
export const importData = (data: unknown) =>
	fetch('/api/data/import', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	}).then(json<{ added: Record<string, number> }>);
export const wipeData = (target: string) =>
	fetch(`/api/data/wipe/${target}`, { method: 'POST' }).then(json<{ wiped: string }>);

export interface PendingFact {
	id: number;
	text: string;
	fact_type: string;
	created_at: string;
}

export const listPending = () => fetch('/api/memory/pending').then(json<PendingFact[]>);
export const approvePending = (id: number) =>
	fetch(`/api/memory/pending/${id}/approve`, { method: 'POST' }).then(json);
export const rejectPending = (id: number) =>
	fetch(`/api/memory/pending/${id}`, { method: 'DELETE' }).then(json);

export const getSettings = () => fetch('/api/settings').then(json<AppSettings>);
export const putSettings = (patch: Partial<AppSettings>) =>
	fetch('/api/settings', {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	}).then(json<AppSettings>);

// ---- Modelos / Compare ----

export interface CompareSide {
	model: string;
	text: string;
	error: string | null;
}

export const listModels = () =>
	fetch('/api/models').then(json<{ models: string[] }>).then((r) => r.models);

export const compare = (prompt: string, modelA: string, modelB: string) =>
	fetch('/api/compare', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ prompt, model_a: modelA, model_b: modelB })
	}).then(json<{ left: CompareSide; right: CompareSide }>);

// ---- Documentos ----

export interface Doc {
	id: number;
	title: string;
	content: string;
	updated_at: string;
}

export const listDocuments = () => fetch('/api/documents').then(json<Doc[]>);
export const createDocument = (title: string, content: string) =>
	fetch('/api/documents', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title, content })
	}).then(json<{ id: number }>);
export const updateDocument = (id: number, patch: { title?: string; content?: string }) =>
	fetch(`/api/documents/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	}).then(json);
export const deleteDocument = (id: number) =>
	fetch(`/api/documents/${id}`, { method: 'DELETE' }).then(json);
export const assistDocument = (content: string, instruction: string) =>
	fetch('/api/documents/assist', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ content, instruction })
	}).then(json<{ text: string }>);

// ---- Agents ----

export interface AgentStep {
	thought: string;
	tool: string | null;
	args: Record<string, unknown>;
	observation: string | null;
}

// Aprovação inline de ferramentas perigosas (B8).
export interface AgentPending {
	tool: string;
	args: Record<string, unknown>;
	thought: string;
}
export interface AgentRunResult {
	steps: AgentStep[];
	final: string | null;
	pending?: AgentPending | null;
	state?: Record<string, unknown>;
}
export type AgentDecision = 'allow_once' | 'allow_session' | 'allow_always' | 'deny';

export const agentRun = (task: string) =>
	fetch('/api/agent/run', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ task })
	}).then(json<AgentRunResult>);

// Retoma o loop após o utilizador decidir sobre uma ferramenta pendente.
export const agentResume = (
	state: Record<string, unknown>,
	pending: AgentPending,
	decision: AgentDecision
) =>
	fetch('/api/agent/run', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			state,
			decision,
			pending_tool: pending.tool,
			pending_args: pending.args,
			pending_thought: pending.thought
		})
	}).then(json<AgentRunResult>);

export interface AgentTool {
	name: string;
	desc: string;
	dangerous: boolean;
	requires_internet: boolean;
	enabled: boolean;
}

export const listAgentTools = () => fetch('/api/agent/tools').then(json<AgentTool[]>);

// ---- Notas ----

export interface Note {
	id: number;
	title: string;
	content: string;
	pinned: number;
	created_at: string;
	updated_at: string;
}

export const listNotes = () => fetch('/api/notes').then(json<Note[]>);
export const createNote = (title: string, content: string) =>
	fetch('/api/notes', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title, content })
	}).then(json<{ id: number }>);
export const updateNote = (
	id: number,
	patch: { title?: string; content?: string; pinned?: boolean }
) =>
	fetch(`/api/notes/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	}).then(json);
export const deleteNote = (id: number) =>
	fetch(`/api/notes/${id}`, { method: 'DELETE' }).then(json);

// ---- Tarefas ----

export interface Task {
	id: number;
	text: string;
	done: number;
	created_at: string;
}

export const listTasks = () => fetch('/api/tasks').then(json<Task[]>);
export const createTask = (text: string) =>
	fetch('/api/tasks', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ text })
	}).then(json<{ id: number }>);
export const updateTask = (id: number, patch: { text?: string; done?: boolean }) =>
	fetch(`/api/tasks/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	}).then(json);
export const deleteTask = (id: number) =>
	fetch(`/api/tasks/${id}`, { method: 'DELETE' }).then(json);

// ---- Pipeline (Stage 3) ----

export interface Transaction {
	date: string | null;
	amount: number | null;
	currency: string | null;
	merchant: string | null;
	category: string | null;
	account: string | null;
	notes: string | null;
	confidence: number;
	low_confidence_fields: string[];
}

export const pipelineExtract = (text: string, imageBase64?: string | null) =>
	fetch('/api/pipeline/extract', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ text, image_base64: imageBase64 ?? null })
	}).then(json<Transaction>);

export const pipelineDispatch = (tx: Transaction) =>
	fetch('/api/pipeline/dispatch', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(tx)
	}).then(json<{ id: number; dispatched: boolean; detail: string }>);

// ---- Skills ----

export interface Skill {
	id: number;
	name: string;
	instruction: string;
	enabled: number;
	created_at?: string;
}

export const listSkills = () => fetch('/api/skills').then(json<Skill[]>);

export const createSkill = (name: string, instruction: string) =>
	fetch('/api/skills', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name, instruction })
	}).then(json<Skill>);

export const updateSkill = (
	id: number,
	patch: { name?: string; instruction?: string; enabled?: boolean }
) =>
	fetch(`/api/skills/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	}).then(json);

export const deleteSkill = (id: number) =>
	fetch(`/api/skills/${id}`, { method: 'DELETE' }).then(json);

export interface PendingSkill {
	id: number;
	name: string;
	instruction: string;
	created_at: string;
}

export const listPendingSkills = () =>
	fetch('/api/skills/pending').then(json<PendingSkill[]>);
export const approvePendingSkill = (id: number) =>
	fetch(`/api/skills/pending/${id}/approve`, { method: 'POST' }).then(json);
export const rejectPendingSkill = (id: number) =>
	fetch(`/api/skills/pending/${id}`, { method: 'DELETE' }).then(json);

export const exportSkills = () =>
	fetch('/api/skills/export').then(json<Skill[]>);
export const importSkills = (skills: { name: string; instruction: string; enabled?: boolean }[]) =>
	fetch('/api/skills/import', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ skills })
	}).then(json<{ added: number }>);

// ---- Galeria ----

export interface GalleryItem {
	image_path: string;
	conversation_id: number;
	created_at: string;
	title: string | null;
	conv_snippet: string | null;
}

export const listGallery = () => fetch('/api/gallery').then(json<GalleryItem[]>);

/** Caminho servível de uma imagem persistida. */
export const imageUrl = (path: string) => `/api/images/${path.split('/').pop()}`;
