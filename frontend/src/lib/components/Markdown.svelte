<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';

	let { source = '' }: { source?: string } = $props();
	const html = $derived(renderMarkdown(source));

	// Copiar o código do bloco quando se carrega no botão "copiar" (delegação).
	function onClick(e: MouseEvent) {
		const btn = (e.target as HTMLElement)?.closest?.('.md-copy') as HTMLElement | null;
		if (!btn) return;
		const code = btn.closest('.md-code')?.querySelector('code')?.textContent ?? '';
		navigator.clipboard?.writeText(code);
		const prev = btn.textContent;
		btn.textContent = 'copiado';
		setTimeout(() => (btn.textContent = prev), 1200);
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="md" onclick={onClick}>{@html html}</div>

<style>
	.md {
		white-space: normal;
	}
	.md :global(p) {
		margin: 0 0 0.6em;
		white-space: pre-wrap;
	}
	.md :global(.md-h) {
		margin: 0.6em 0 0.3em;
		font-weight: 600;
		line-height: 1.3;
	}
	.md :global(h1.md-h) {
		font-size: 1.3em;
	}
	.md :global(h2.md-h) {
		font-size: 1.18em;
	}
	.md :global(h3.md-h),
	.md :global(h4.md-h) {
		font-size: 1.06em;
	}
	.md :global(.md-list) {
		margin: 0.2em 0 0.6em;
		padding-left: 1.4em;
	}
	.md :global(.md-list li) {
		margin: 0.15em 0;
	}
	.md :global(.md-bq) {
		margin: 0.4em 0;
		padding: 0.2em 0.8em;
		border-left: 3px solid color-mix(in srgb, var(--accent) 50%, var(--border));
		color: var(--fg-muted);
	}
	.md :global(.md-ic) {
		font-family: var(--font-mono, monospace);
		font-size: 0.9em;
		background: color-mix(in srgb, var(--fg) 10%, transparent);
		padding: 1px 5px;
		border-radius: 5px;
	}
	.md :global(a) {
		color: var(--accent);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.md :global(.md-code) {
		margin: 0.5em 0;
		border: 1px solid var(--border);
		border-radius: 9px;
		overflow: hidden;
		background: color-mix(in srgb, var(--fg) 5%, var(--bg));
	}
	.md :global(.md-code-head) {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 4px 10px;
		font-size: 11px;
		color: var(--fg-muted);
		border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
	}
	.md :global(.md-lang) {
		text-transform: lowercase;
		letter-spacing: 0.3px;
	}
	.md :global(.md-copy) {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--fg-muted);
		font: inherit;
		font-size: 11px;
		padding: 2px 8px;
		border-radius: 6px;
		cursor: pointer;
	}
	.md :global(.md-copy:hover) {
		color: var(--accent);
		border-color: var(--accent);
	}
	.md :global(pre) {
		margin: 0;
		padding: 10px 12px;
		overflow-x: auto;
	}
	.md :global(pre code) {
		font-family: var(--font-mono, monospace);
		font-size: 12.5px;
		line-height: 1.5;
	}
	.md :global(.md-table) {
		border-collapse: collapse;
		margin: 0.5em 0;
		font-size: 13px;
		display: block;
		overflow-x: auto;
	}
	.md :global(.md-table th),
	.md :global(.md-table td) {
		border: 1px solid var(--border);
		padding: 5px 10px;
		text-align: left;
	}
	.md :global(.md-table th) {
		background: color-mix(in srgb, var(--fg) 7%, transparent);
		font-weight: 600;
	}
</style>
