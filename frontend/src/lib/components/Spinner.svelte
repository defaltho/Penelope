<script lang="ts">
	import { onMount } from 'svelte';
	import { SPINNER_FRAMES, spinnerVerbs, loadTheme } from '$lib/theme';

	// label: se fornecido, mostra-o fixo; senão roda os verbos do tema.
	let { label = '', rotateVerbs = true }: { label?: string; rotateVerbs?: boolean } = $props();

	let frame = $state(0);
	let verbIdx = $state(0);
	const verbs = spinnerVerbs(loadTheme());

	const reduced =
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

	onMount(() => {
		if (reduced) return; // estático: respeita reduced-motion
		const f = setInterval(() => (frame = (frame + 1) % SPINNER_FRAMES.length), 90);
		const v = rotateVerbs
			? setInterval(() => (verbIdx = (verbIdx + 1) % verbs.length), 1800)
			: undefined;
		return () => {
			clearInterval(f);
			if (v) clearInterval(v);
		};
	});

	const text = $derived(label || verbs[verbIdx]);
</script>

<span class="spinner" aria-live="polite">
	<span class="glyph">{SPINNER_FRAMES[frame]}</span>
	<span class="verb">{text}…</span>
</span>

<style>
	.spinner {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		color: var(--fg-muted);
		font-size: 13px;
		font-family: var(--font-ui);
	}
	.glyph {
		color: var(--accent);
		font-family: var(--font-mono, monospace);
		font-size: 14px;
		line-height: 1;
	}
	.verb {
		opacity: 0.85;
		transition: opacity 0.3s ease;
	}
	@media (prefers-reduced-motion: reduce) {
		.verb {
			transition: none;
		}
	}
</style>
