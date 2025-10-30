<script lang="ts">
import { createEventDispatcher } from 'svelte';
import DateSelector from '$lib/components/chat/ControlPanel/DateSelector.svelte';
import ResponseTypeSelector from '$lib/components/chat/ControlPanel/ResponseTypeSelector.svelte';
import WebToggle from '$lib/components/chat/ControlPanel/WebToggle.svelte';

export let showDateSelector = true;
export let showResponseTypeSelector = true;
export let showWebToggle = true;

const dispatch = createEventDispatcher();

function handleDateSelected(e) {
    const {type, value} = e.detail;
    if (value === 'All') return;
    dispatch('dateselected', e.detail);
    
    console.log('date selection handled in control panel', e.detail)
}

function handleResponseTypeSelected(e) {
    const {type, value} = e.detail;
    if (value === 'Default') return;
    dispatch('responsetypeselected', e.detail);
    console.log('response type selection handled in control panel', e.detail)
}

</script>

<div
	class="flex flex-wrap items-center justify-center gap-3 px-2 py-1 rounded-3xl border border-gray-200/60 dark:border-gray-800/70 
	       bg-white/80 dark:bg-gray-900/50 dark:text-gray-100 backdrop-blur-md shadow-md 
	       focus-within:border-gray-100 
	       focus-within:dark:border-gray-800 
	       transition-all duration-300 ease-in-out 
		   divide-x-1 divide-gray-200/60 dark:divide-gray-700/60"
>
	{#if showDateSelector}
		<div class="relative px-1">
			<DateSelector on:dateselected={handleDateSelected}/>
		</div>
	{/if}

	{#if showResponseTypeSelector}
		<div class="relative px-1">
			<ResponseTypeSelector on:responsetypeselected={handleResponseTypeSelected}/>
		</div>
	{/if}

	{#if showWebToggle}
		<div class="relative px-1">
			<WebToggle/>
		</div>
	{/if}
</div>