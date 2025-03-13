<script lang="ts">
	import Fuse from 'fuse.js';
	import Bolt from '$lib/components/icons/Bolt.svelte';
	import { getContext, createEventDispatcher } from 'svelte';
	import { WEBUI_NAME } from '$lib/stores';

	import { WEBUI_VERSION } from '$lib/constants';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let suggestionPrompts = [];
	export let inputValue = '';

	let sortedPrompts = [];

	const fuseOptions = {
		keys: ['content', 'title', 'prompts'],
		threshold: 0.5
	};

	let fuse;
	let filteredPrompts = [];

  let showMore = false;
  function handleMoreClick() {
    showMore = !showMore;
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
    // If the input is too long, don't filter
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

  // Computed property to determine if the suggestions are filtered - is this the best way?
  $: isFilteredPrompts = filteredPrompts.length < sortedPrompts.length;

  // TODO: is there a better way to do this? revisit this implementation.
  $: selectedSuggestion = filteredPrompts.find((p) => p.content === inputValue);

  // Computed property to determine if there is text input
  $: hasInput = inputValue.length > 0;

  // Reactive variable to set the class on the suggestions container
  const fullHeight = 'h-auto max-h-[250px] p-1';
  const oneRowHeight = 'h-[46px] overflow-hidden p-1';
  const noHeight = 'h-0 overflow-hidden p-0';
  $: suggestionHeight = (() => {
    if(hasInput) {
      // Should hide the buttons when there is input
      return noHeight;
    } else {
      // Should show one or more rows of buttons
      if (showMore) {
        return fullHeight;
      } else {
        return oneRowHeight;
      }
    }
  })();

  $: isFullHeight = suggestionHeight === fullHeight;

  // Function to clear the input value
  function clearInput() {
    inputValue = '';
    dispatch('setInput', { value: ''})
  }  
</script>

<div class="mb-1 flex gap-1 text-xs font-medium items-center text-gray-400 dark:text-gray-600">
	{#if filteredPrompts.length > 0}
		<Bolt />
		{$i18n.t('Suggested')}
    {#if !hasInput}
      <button
        on:click={handleMoreClick}
        class="ml-4 md:order-none text-neutral-500 text-xs rounded-md order-2"
      >
        {isFullHeight ? 'show less' : 'show more'}
      </button>
  	{:else}
      <button
        on:click={clearInput}
        class="ml-4 md:order-none text-neutral-500 text-xs rounded-md order-2"
      >
        clear
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

<!-- categories -->
<div class={`flex flex-wrap overflow-hidden gap-2 ${suggestionHeight}`}>
	{#if hasSuggestions}
		{#each filteredPrompts as prompt, idx (prompt.id || prompt.content || prompt.image)}
        <button class="group flex flex-shrink-0 whitespace-nowrap h-[35px] items-center gap-1.5 rounded-full border border-neutral-700 px-4 text-start text-[13px] justify-center transition enabled:hover:bg-neutral-600  disabled:cursor-not-allowed"
        on:click={() => {dispatch('select', prompt.content); selectedSuggestion = prompt.content;}}  
        >
          {#if prompt.image?.length > 0}
            {@html prompt.image}
          {/if}
          <span class="max-w-full select-none whitespace-nowrap transition group-hover:text-white dark:text-gray-500 custom-hover">{prompt.title[0]}</span>
        </button>
		{/each}
	{/if}
</div>

<!-- prompt options -->
{#if isFilteredPrompts && selectedSuggestion?.prompts?.length > 0}
  <div class="suggestions-container left-0 z-[-1] w-full pl-0 ">
    <ul class="w-full flex-col p-2.5 max-lg:flex-col-reverse" style="opacity: 1; will-change: auto;">
  		{#each selectedSuggestion?.prompts as promptOption}
        <li class="w-full" style="opacity: 1; will-change: auto; transform: none;">
          <button class="hover:bg-gray-100 dark:hover:bg-gray-800  flex w-full cursor-pointer items-center justify-start whitespace-pre-wrap rounded-lg px-2.5 py-3 text-start"
            on:click={() => dispatch('select', promptOption)}
            >
            <span class="whitespace-pre-wrap text-sm">
              <span class="text-neutral-500 dark:text-neutral-500 mr-1">{selectedSuggestion?.title?.[0]}</span>
              <span class="text-neutral-900 dark:text-neutral-300 font-light ">{promptOption}</span>
            </span>
          </button>
          <div class="h-[1px] opacity-60 bg-token-border-light"></div>
        </li>
      {/each}
    </ul>
  </div>
{/if}

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
  .bg-token-border-light {
      background-color: #ffffff1a;
  }  
</style>
