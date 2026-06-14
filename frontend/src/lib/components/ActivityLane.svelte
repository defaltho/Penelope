<script lang="ts">
	import Spinner from './Spinner.svelte';

	// Mostra a fase atual do turno (B2): pesquisa web, memória, a pensar, etc.
	// kind controla o ícone/emoji; text é a etiqueta. rotateVerbs só na fase 'thinking'.
	let { kind = 'thinking', text = '' }: { kind?: string; text?: string } = $props();

	const EMOJI: Record<string, string> = {
		web: '🌐',
		memory: '◈',
		thinking: '',
		tool: '⚙'
	};
	const emoji = $derived(EMOJI[kind] ?? '');
</script>

<div class="lane">
	{#if emoji}<span class="emoji">{emoji}</span>{/if}
	<Spinner label={text} rotateVerbs={kind === 'thinking' && !text} />
</div>

<style>
	.lane {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 4px 0;
		opacity: 0.95;
	}
	.emoji {
		font-size: 13px;
		line-height: 1;
	}
</style>
