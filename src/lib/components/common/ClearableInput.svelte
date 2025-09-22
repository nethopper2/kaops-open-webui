<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	// Props
	export let id: string = 'clearable-input';
	export let value: string = '';
	export let placeholder: string = '';
	export let ariaLabel: string | undefined = undefined;
	export let autocomplete: string = 'off';
	export let spellcheck: boolean = false;
	// Optional: expose name and type in case needed in forms
	export let name: string | undefined = undefined;
	export let type: 'text' | 'search' = 'text';

	let inputEl: HTMLInputElement | null = null;

	function clear() {
		value = '';
		// Keep focus on input for better UX
		queueMicrotask(() => {
			inputEl?.focus();
		});
	}

	function onKeydown(e: KeyboardEvent) {
		// Allow Esc to clear when there is a value
		if (e.key === 'Escape' && value) {
			e.preventDefault();
			clear();
		}
	}

	function onInput(e: Event) {
		const target = e.currentTarget as HTMLInputElement | null;
		value = target ? target.value : '';
	}
</script>

<style>
	/* Hide the native WebKit clear (x) button for search inputs within this component */
	:global(.clearable-input-wrapper) input[type="search"]::-webkit-search-cancel-button {
		-webkit-appearance: none;
		appearance: none;
		height: 0;
		width: 0;
		margin: 0;
		padding: 0;
	}
</style>

<div class="clearable-input-wrapper relative w-full">
	<label class="sr-only" for={id}>{ariaLabel ?? placeholder}</label>
	<input
		bind:this={inputEl}
		{id}
		class="w-full pr-10 px-3 py-2 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
		{placeholder}
		{autocomplete}
		{spellcheck}
		{name}
		type={type}
		value={value}
		on:input={onInput}
		on:keydown={onKeydown}
	/>
	{#if value}
		<button
			type="button"
			class="absolute inset-y-0 top-0 right-2 my-auto h-6 w-6 inline-flex items-center justify-center rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-700"
			aria-label={$i18n.t('Clear input')}
			on:click={clear}
		>
			<!-- Heroicons mini x-mark -->
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" class="h-4 w-4">
				<path fill-rule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm3.53-10.47a.75.75 0 0 0-1.06-1.06L10 8.94 7.53 6.47a.75.75 0 1 0-1.06 1.06L8.94 10l-2.47 2.47a.75.75 0 1 0 1.06 1.06L10 11.06l2.47 2.47a.75.75 0 1 0 1.06-1.06L11.06 10l2.47-2.47Z" clip-rule="evenodd" />
			</svg>
		</button>
	{/if}
</div>
