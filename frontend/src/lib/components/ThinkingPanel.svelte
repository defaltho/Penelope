<script lang="ts">
	import Spinner from './Spinner.svelte';

	// content: texto de raciocínio (<think>…</think>). active: ainda a gerar.
	let { content = '', active = false }: { content?: string; active?: boolean } = $props();

	// Aberto por defeito enquanto raciocina; o utilizador pode alternar.
	let userToggled = $state(false);
	let openState = $state(true);
	const open = $derived(userToggled ? openState : active);

	function toggle() {
		userToggled = true;
		openState = !open;
	}
</script>

<div class="think" class:active>
	<button class="think-head" onclick={toggle} aria-expanded={open}>
		{#if active}
			<Spinner label="a raciocinar" rotateVerbs={false} />
		{:else}
			<span class="lbl">raciocínio</span>
		{/if}
		<span class="chev" class:open>▸</span>
	</button>
	{#if open && content.trim()}
		<div class="think-body">{content.trim()}</div>
	{/if}
</div>

<style>
	.think {
		margin: 2px 0 8px;
		border-left: 2px solid color-mix(in srgb, var(--accent) 45%, var(--border));
		background: color-mix(in srgb, var(--accent) 6%, transparent);
		border-radius: 0 8px 8px 0;
	}
	.think-head {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		background: transparent;
		border: none;
		color: var(--fg-muted);
		font-family: var(--font-ui);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		padding: 6px 10px;
		cursor: pointer;
	}
	.lbl {
		opacity: 0.8;
	}
	.chev {
		margin-left: auto;
		transition: transform 0.18s ease;
	}
	.chev.open {
		transform: rotate(90deg);
	}
	.think-body {
		padding: 2px 12px 10px;
		font-family: var(--font-body);
		font-size: 13px;
		line-height: 1.5;
		color: var(--fg-muted);
		white-space: pre-wrap;
	}
	@media (prefers-reduced-motion: reduce) {
		.chev {
			transition: none;
		}
	}
</style>
