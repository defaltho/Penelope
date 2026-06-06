<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<title>Penelope</title>
	<link rel="icon" href={favicon} />
	<meta name="theme-color" content="#0b0b0c" />
</svelte:head>

{@render children()}
