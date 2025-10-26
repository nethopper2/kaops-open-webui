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
	class="flex items-center gap-2 px-2 py-1 rounded-3xl border border-gray-50 dark:border-gray-850 
	       bg-white/90 dark:bg-gray-400/5 dark:text-gray-100 shadow-sm 
	       hover:border-gray-100 focus-within:border-gray-100 
	       hover:dark:border-gray-800 focus-within:dark:border-gray-800 
	       transition-all duration-200"
>
	{#if showDateSelector}
		<div class="relative">
			<DateSelector on:dateselected={handleDateSelected}/>
		</div>
	{/if}

	{#if showResponseTypeSelector}
		<div class="relative">
			<ResponseTypeSelector on:responsetypeselected={handleResponseTypeSelected}/>
		</div>
	{/if}

	{#if showWebToggle}
		<div class="relative">
			<WebToggle/>
		</div>
	{/if}
</div>