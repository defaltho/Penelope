<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listSkills,
		createSkill,
		updateSkill,
		deleteSkill,
		exportSkills,
		importSkills,
		listPendingSkills,
		approvePendingSkill,
		rejectPendingSkill,
		type Skill,
		type PendingSkill
	} from '$lib/api';
	import { downloadJson, pickJsonFile } from '$lib/io';
	import Icon from './Icon.svelte';

	let pending = $state<PendingSkill[]>([]);

	async function loadPending() {
		try {
			pending = await listPendingSkills();
		} catch (e) {
			console.error('falha a carregar skills pendentes', e);
		}
	}
	async function approveP(p: PendingSkill) {
		pending = pending.filter((x) => x.id !== p.id);
		await approvePendingSkill(p.id);
		await load();
	}
	async function rejectP(p: PendingSkill) {
		pending = pending.filter((x) => x.id !== p.id);
		await rejectPendingSkill(p.id);
	}

	let { onClose, inline = false }: { onClose?: () => void; inline?: boolean } = $props();

	async function doExport() {
		try {
			downloadJson('penelope-skills.json', await exportSkills());
		} catch (e) {
			console.error('export falhou', e);
		}
	}
	async function doImport() {
		try {
			const data = await pickJsonFile();
			const arr = Array.isArray(data) ? data : (data as any)?.skills;
			if (!Array.isArray(arr)) {
				alert('ficheiro inválido: esperado uma lista de skills');
				return;
			}
			const { added } = await importSkills(arr);
			alert(`${added} skill(s) importada(s).`);
			await load();
		} catch (e) {
			alert('importação falhou: ficheiro inválido?');
		}
	}

	let skills = $state<Skill[]>([]);
	let loading = $state(true);
	let newName = $state('');
	let newInstruction = $state('');
	let editingId = $state<number | null>(null);
	let editName = $state('');
	let editInstruction = $state('');

	onMount(() => {
		load();
		loadPending();
	});

	async function load() {
		loading = true;
		try {
			skills = await listSkills();
		} catch (e) {
			console.error('falha a carregar skills', e);
		} finally {
			loading = false;
		}
	}

	async function add() {
		if (!newName.trim() || !newInstruction.trim()) return;
		await createSkill(newName.trim(), newInstruction.trim());
		newName = '';
		newInstruction = '';
		await load();
	}

	async function toggle(s: Skill) {
		const enabled = s.enabled ? 0 : 1;
		await updateSkill(s.id, { enabled: !!enabled });
		s.enabled = enabled;
	}

	function startEdit(s: Skill) {
		editingId = s.id;
		editName = s.name;
		editInstruction = s.instruction;
	}
	async function commitEdit() {
		if (editingId == null) return;
		const id = editingId;
		editingId = null;
		if (editName.trim() && editInstruction.trim()) {
			await updateSkill(id, { name: editName.trim(), instruction: editInstruction.trim() });
			const s = skills.find((x) => x.id === id);
			if (s) {
				s.name = editName.trim();
				s.instruction = editInstruction.trim();
			}
		}
	}
	async function remove(s: Skill) {
		if (!confirm(`Apagar a skill "${s.name}"?`)) return;
		await deleteSkill(s.id);
		skills = skills.filter((x) => x.id !== s.id);
	}
</script>

<div
	class="overlay"
	class:inline
	role="presentation"
	onclick={(e) => {
		if (!inline && e.target === e.currentTarget) onClose?.();
	}}
>
	<div class="panel" class:inline role="dialog" aria-label="Skills">
		<header class="panel-head">
			<h2><span class="dot"></span>Skills <span class="count">{skills.length}</span></h2>
			<div class="head-actions">
				<button class="io-btn" onclick={doImport} title="Importar">
					<Icon name="upload" size={14} /> importar
				</button>
				<button class="io-btn" onclick={doExport} title="Exportar">
					<Icon name="download" size={14} /> exportar
				</button>
				{#if !inline}
					<button class="close" onclick={() => onClose?.()} aria-label="Fechar">×</button>
				{/if}
			</div>
		</header>

		<div class="body">
			<div class="new-skill">
				<input class="in" placeholder="nome (ex.: Tom formal)" bind:value={newName} />
				<textarea
					class="in ta"
					placeholder="instrução (ex.: Responde sempre em tom formal e conciso)"
					bind:value={newInstruction}
				></textarea>
				<button class="add" onclick={add} disabled={!newName.trim() || !newInstruction.trim()}>
					+ adicionar skill
				</button>
			</div>

			{#if pending.length}
				<div class="pending">
					<div class="pending-head">
						<Icon name="lightbulb" size={13} /> a aprovar <span class="count">{pending.length}</span>
					</div>
					{#each pending as p (p.id)}
						<div class="pend-item">
							<div class="pend-main">
								<span class="pend-name">{p.name}</span>
								<span class="pend-instr">{p.instruction}</span>
							</div>
							<div class="pend-actions">
								<button class="ok" onclick={() => approveP(p)} title="Aprovar" aria-label="Aprovar">✓</button>
								<button class="no" onclick={() => rejectP(p)} title="Rejeitar" aria-label="Rejeitar">✕</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<div class="list">
				{#if loading}
					<p class="muted">a carregar…</p>
				{:else if skills.length === 0}
					<p class="muted">sem skills ainda. cria a primeira acima.</p>
				{/if}

				{#each skills as s (s.id)}
					<div class="skill" class:off={!s.enabled}>
						{#if editingId === s.id}
							<input class="in" bind:value={editName} />
							<textarea class="in ta" bind:value={editInstruction}></textarea>
							<div class="row-actions">
								<button class="mini primary" onclick={commitEdit}>guardar</button>
								<button class="mini" onclick={() => (editingId = null)}>cancelar</button>
							</div>
						{:else}
							<div class="skill-head">
								<button
									class="toggle"
									class:on={s.enabled}
									onclick={() => toggle(s)}
									title={s.enabled ? 'ativa' : 'inativa'}
									aria-label="Ativar/desativar"
								>
									<span class="knob"></span>
								</button>
								<span class="skill-name">{s.name}</span>
								<div class="skill-actions">
									<button onclick={() => startEdit(s)} title="Editar" aria-label="Editar">✎</button>
									<button onclick={() => remove(s)} title="Apagar" aria-label="Apagar">🗑</button>
								</div>
							</div>
							<p class="skill-text">{s.instruction}</p>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, #000 55%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 50;
		padding: 20px;
	}
	.panel {
		width: 100%;
		max-width: 560px;
		max-height: 82dvh;
		display: flex;
		flex-direction: column;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
	}

	.overlay.inline {
		position: static;
		inset: auto;
		flex: 1;
		min-width: 0;
		padding: 0;
		background: transparent;
		backdrop-filter: none;
		-webkit-backdrop-filter: none;
		animation: none;
	}
	.panel.inline {
		flex: 1;
		max-width: none;
		max-height: none;
		height: 100dvh;
		border: none;
		border-radius: 0;
		box-shadow: none;
		animation: none;
	}
	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 18px;
		border-bottom: 1px solid var(--border);
	}
	.panel-head h2 {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.panel-head .dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent);
	}
	.count {
		color: var(--fg-muted);
		font-size: 12px;
		font-weight: 400;
	}
	.close {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
	}
	.close:hover {
		color: var(--fg-strong);
	}
	.head-actions {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.io-btn {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 11px;
		padding: 5px 9px;
		border-radius: 8px;
		cursor: pointer;
		transition: color 0.14s, border-color 0.14s;
	}
	.io-btn:hover {
		color: var(--accent);
		border-color: var(--accent);
	}

	.body {
		flex: 1;
		overflow-y: auto;
		padding: 16px 18px;
	}

	.in {
		width: 100%;
		background: var(--bg);
		border: 1px solid var(--border);
		color: var(--fg-strong);
		font-family: var(--font-body);
		font-size: 13.5px;
		padding: 8px 11px;
		border-radius: 9px;
		outline: none;
		margin-bottom: 8px;
	}
	.in:focus {
		border-color: var(--accent);
	}
	.ta {
		resize: vertical;
		min-height: 52px;
		line-height: 1.4;
	}

	.new-skill {
		border: 1px dashed var(--border);
		border-radius: 12px;
		padding: 12px;
		margin-bottom: 18px;
	}
	.add {
		width: 100%;
		background: transparent;
		border: 1px solid var(--accent);
		color: var(--accent);
		font: inherit;
		font-size: 13px;
		padding: 7px;
		border-radius: 9px;
		cursor: pointer;
		margin-bottom: 0;
	}
	.add:disabled {
		opacity: 0.4;
		cursor: default;
		border-color: var(--border);
		color: var(--fg-muted);
	}

	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		margin: 24px 0;
	}

	.pending {
		margin-bottom: 16px;
		padding: 8px;
		border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
		border-radius: 12px;
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.pending-head {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		color: var(--accent);
		padding: 2px 4px 8px;
	}
	.pend-item {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		padding: 8px 4px;
	}
	.pend-main {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}
	.pend-name {
		font-size: 13px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.pend-instr {
		font-family: var(--font-body);
		font-size: 12.5px;
		color: var(--fg);
		line-height: 1.4;
	}
	.pend-actions {
		display: flex;
		gap: 4px;
	}
	.pend-actions button {
		width: 24px;
		height: 24px;
		border-radius: 7px;
		border: 1px solid var(--border);
		background: transparent;
		cursor: pointer;
		font-size: 12px;
		line-height: 1;
	}
	.pend-actions .ok {
		color: var(--green);
		border-color: color-mix(in srgb, var(--green) 45%, transparent);
	}
	.pend-actions .ok:hover {
		background: color-mix(in srgb, var(--green) 18%, transparent);
	}
	.pend-actions .no {
		color: var(--red);
		border-color: color-mix(in srgb, var(--red) 45%, transparent);
	}
	.pend-actions .no:hover {
		background: color-mix(in srgb, var(--red) 18%, transparent);
	}

	.skill {
		border: 1px solid var(--border);
		border-radius: 11px;
		padding: 11px 12px;
		margin-bottom: 10px;
		transition: opacity 0.15s;
	}
	.skill.off {
		opacity: 0.55;
	}
	.skill-head {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.skill-name {
		flex: 1;
		font-size: 13.5px;
		font-weight: 600;
		color: var(--fg-strong);
	}
	.skill-text {
		margin: 8px 0 0;
		font-family: var(--font-body);
		font-size: 13px;
		color: var(--fg);
		line-height: 1.45;
		white-space: pre-wrap;
	}
	.skill-actions {
		display: flex;
		gap: 2px;
	}
	.skill-actions button {
		background: transparent;
		border: none;
		color: var(--fg-muted);
		cursor: pointer;
		font-size: 12px;
		padding: 2px 4px;
	}
	.skill-actions button:hover {
		color: var(--fg-strong);
	}

	.toggle {
		flex: none;
		width: 34px;
		height: 19px;
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
		width: 15px;
		height: 15px;
		border-radius: 50%;
		background: var(--fg-muted);
		transition: transform 0.15s, background 0.15s;
	}
	.toggle.on .knob {
		transform: translateX(15px);
		background: var(--accent);
	}

	.row-actions {
		display: flex;
		gap: 8px;
	}
	.mini {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font: inherit;
		font-size: 12px;
		padding: 5px 12px;
		border-radius: 8px;
		cursor: pointer;
	}
	.mini.primary {
		border-color: var(--accent);
		color: var(--accent);
	}
</style>
