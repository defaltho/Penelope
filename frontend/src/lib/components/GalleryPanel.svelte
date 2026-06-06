<script lang="ts">
	import { onMount } from 'svelte';
	import { listGallery, imageUrl, type GalleryItem } from '$lib/api';

	let { onClose, onOpenConversation, inline = false }: {
		onClose?: () => void;
		onOpenConversation: (id: number) => void;
		inline?: boolean;
	} = $props();

	let items = $state<GalleryItem[]>([]);
	let loading = $state(true);
	let preview = $state<GalleryItem | null>(null);

	onMount(async () => {
		try {
			items = await listGallery();
		} catch (e) {
			console.error('falha a carregar galeria', e);
		} finally {
			loading = false;
		}
	});

	function caption(it: GalleryItem): string {
		return (it.title || it.conv_snippet || 'conversa').trim();
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
	<div class="panel" class:inline role="dialog" aria-label="Galeria">
		<header class="panel-head">
			<h2><span class="dot"></span>Galeria <span class="count">{items.length}</span></h2>
			{#if !inline}
				<button class="close" onclick={() => onClose?.()} aria-label="Fechar">×</button>
			{/if}
		</header>

		<div class="grid-wrap">
			{#if loading}
				<p class="muted">a carregar…</p>
			{:else if items.length === 0}
				<p class="muted">ainda não anexaste imagens</p>
			{:else}
				<div class="grid">
					{#each items as it (it.image_path)}
						<button class="cell" onclick={() => (preview = it)} title={caption(it)}>
							<img src={imageUrl(it.image_path)} alt={caption(it)} loading="lazy" />
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

{#if preview}
	<div
		class="lightbox"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) preview = null;
		}}
	>
		<div class="lb-inner">
			<img src={imageUrl(preview.image_path)} alt={caption(preview)} />
			<div class="lb-bar">
				<span class="lb-cap">{caption(preview)}</span>
				<button
					class="lb-open"
					onclick={() => {
						onOpenConversation(preview!.conversation_id);
						preview = null;
						onClose?.();
					}}
				>
					abrir conversa →
				</button>
			</div>
		</div>
	</div>
{/if}

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
		max-width: 720px;
		max-height: 80dvh;
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

	.grid-wrap {
		flex: 1;
		overflow-y: auto;
		padding: 16px 18px;
	}
	.muted {
		color: var(--fg-muted);
		font-size: 13px;
		text-align: center;
		margin: 32px 0;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		gap: 10px;
	}
	.cell {
		padding: 0;
		border: 1px solid var(--border);
		border-radius: 10px;
		overflow: hidden;
		cursor: pointer;
		aspect-ratio: 1;
		background: var(--panel-2);
	}
	.cell:hover {
		border-color: var(--accent);
	}
	.cell img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.lightbox {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, #000 80%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 60;
		padding: 24px;
	}
	.lb-inner {
		display: flex;
		flex-direction: column;
		gap: 12px;
		max-width: 90vw;
		max-height: 90dvh;
		align-items: center;
	}
	.lb-inner img {
		max-width: 100%;
		max-height: 78dvh;
		border-radius: 10px;
		border: 1px solid var(--border);
	}
	.lb-bar {
		display: flex;
		align-items: center;
		gap: 16px;
	}
	.lb-cap {
		color: var(--fg-muted);
		font-size: 13px;
	}
	.lb-open {
		background: var(--accent);
		color: var(--panel-2);
		border: none;
		font: inherit;
		font-size: 13px;
		padding: 7px 14px;
		border-radius: 999px;
		cursor: pointer;
	}
	.lb-open:hover {
		background: var(--accent-hover);
	}
</style>
