<script lang="ts">
	import { modelFamily } from '$lib/models';
	import { providerLogo } from '$lib/providers';
	let { name, size = 16 }: { name: string; size?: number } = $props();
	const logo = $derived(providerLogo(name));
	const f = $derived(modelFamily(name));
</script>

{#if logo}
	<span
		class="logo"
		style="--c:{logo.color}; width:{size}px; height:{size}px"
		title={name}
	>
		<svg viewBox="0 0 24 24" fill="currentColor" width={Math.round(size * 0.78)} height={Math.round(size * 0.78)}>
			{@html logo.svg}
		</svg>
	</span>
{:else}
	<span
		class="badge"
		style="--c:{f.color}; width:{size}px; height:{size}px; font-size:{Math.round(size * 0.58)}px"
		title={name}
	>
		{f.label}
	</span>
{/if}

<style>
	.badge,
	.logo {
		flex: none;
		display: inline-grid;
		place-items: center;
		border-radius: 5px;
		line-height: 1;
		color: var(--c);
	}
	.badge {
		font-weight: 700;
		background: color-mix(in srgb, var(--c) 18%, transparent);
		box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 35%, transparent);
	}
	.logo svg {
		display: block;
	}
</style>
