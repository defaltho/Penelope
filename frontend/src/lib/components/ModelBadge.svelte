<script lang="ts">
	import { modelFamily } from '$lib/models';
	let { name, size = 16 }: { name: string; size?: number } = $props();
	const f = $derived(modelFamily(name));
</script>

<span
	class="badge"
	style="--c:{f.color}; width:{size}px; height:{size}px; font-size:{Math.round(size * 0.58)}px"
	title={name}
>
	{f.label}
</span>

<style>
	.badge {
		flex: none;
		display: inline-grid;
		place-items: center;
		border-radius: 5px;
		font-weight: 700;
		line-height: 1;
		color: var(--c);
		background: color-mix(in srgb, var(--c) 18%, transparent);
		box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 35%, transparent);
	}
</style>
