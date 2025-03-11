<script lang="ts">
	import Fuse from 'fuse.js';
	import Bolt from '$lib/components/icons/Bolt.svelte';
	import { getContext, createEventDispatcher } from 'svelte';
	import { WEBUI_NAME } from '$lib/stores';

	import { WEBUI_VERSION } from '$lib/constants';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let suggestionPrompts = [];
	export let className = '';
	export let inputValue = '';

	let sortedPrompts = [];

	const fuseOptions = {
		keys: ['content', 'title'],
		threshold: 0.5
	};

	let fuse;
	let filteredPrompts = [];

  let showingAllSuggestions = false;
  function handleMoreClick() {
    showingAllSuggestions = !showingAllSuggestions;
  }  
	// Initialize Fuse
	$: fuse = new Fuse(sortedPrompts, fuseOptions);

	// Update the filteredPrompts if inputValue changes
	// Only increase version if something wirklich geändert hat
	$: getFilteredPrompts(inputValue);

	// Helper function to check if arrays are the same
	// (based on unique IDs oder content)
	function arraysEqual(a, b) {
		if (a.length !== b.length) return false;
		for (let i = 0; i < a.length; i++) {
			if ((a[i].id ?? a[i].content) !== (b[i].id ?? b[i].content)) {
				return false;
			}
		}
		return true;
	}

	const getFilteredPrompts = (inputValue) => {
		if (inputValue.length > 500) {
			filteredPrompts = [];
		} else {
			const newFilteredPrompts = inputValue.trim()
				? fuse.search(inputValue.trim()).map((result) => result.item)
				: sortedPrompts;

			// Compare with the oldFilteredPrompts
			// If there's a difference, update array + version
			if (!arraysEqual(filteredPrompts, newFilteredPrompts)) {
				filteredPrompts = newFilteredPrompts;
			}
		}
	};

	$: if (suggestionPrompts) {
		sortedPrompts = [...(suggestionPrompts ?? [])].sort(() => Math.random() - 0.5);
		getFilteredPrompts(inputValue);
	}

  // Computed property to determine if there are any suggestions
  $: hasSuggestions = filteredPrompts.length > 0;

  // Reactive variable to set the class on the suggestions container
  $: suggestionHeight = (hasSuggestions && showingAllSuggestions) ? 'h-auto max-h-[250px]' : 'h-[46px] overflow-hidden';

</script>

<div class="mb-1 flex gap-1 text-xs font-medium items-center text-gray-400 dark:text-gray-600">
	{#if filteredPrompts.length > 0}
		<Bolt />
		{$i18n.t('Suggested')}
    {#if !showingAllSuggestions}
    <button
      on:click={handleMoreClick}
      class="ml-4 md:order-none text-neutral-500 text-xs rounded-md order-2"
    >
      {showingAllSuggestions ? 'show less' : 'show more'}
    </button>
    {/if}
	{:else}
		<!-- Keine Vorschläge -->

		<div
			class="flex w-full text-center items-center justify-center self-start text-gray-400 dark:text-gray-600"
		>
			{$WEBUI_NAME} ‧ v{WEBUI_VERSION}
		</div>
	{/if}
</div>

<div class={`flex flex-wrap overflow-hidden gap-2 p-1 ${suggestionHeight}`}>
	{#if hasSuggestions}
		{#each filteredPrompts as prompt, idx (prompt.id || prompt.content || prompt.image)}
        <button class="group flex flex-shrink-0 whitespace-nowrap h-[35px] items-center gap-1.5 rounded-full border border-neutral-700 px-4 items-center text-start text-[13px] justify-center transition enabled:hover:bg-neutral-600  disabled:cursor-not-allowed"
        on:click={() => dispatch('select', prompt.content)}  
        >
          {#if prompt.image?.length > 0}
            {@html prompt.image}
          {/if}
          <span class="max-w-full select-none whitespace-nowrap text-red-600 transition group-hover:text-white dark:text-gray-500 custom-hover">{prompt.title[0]}</span>
        </button>
		{/each}
	{/if}
</div>

<style>
	/* Waterfall animation for the suggestions */
	@keyframes fadeInUp {
		0% {
			opacity: 0;
			transform: translateY(20px);
		}
		100% {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.waterfall {
		opacity: 0;
		animation-name: fadeInUp;
		animation-duration: 200ms;
		animation-fill-mode: forwards;
		animation-timing-function: ease;
	}

  /* 
   * NOTE Should not need this custom class. the group-hover 
   * should work, but does not for some reason 
   */
  .group:hover .custom-hover {
    color: white;
  }
</style>
