<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { fly } from 'svelte/transition';
	import Check from '../../icons/Check.svelte';
	import ChevronDown from '../../icons/ChevronDown.svelte';

	const dispatch = createEventDispatcher();

	export let value = '';
	export let placeholder = 'Select a file';
	export let items: Array<{ idx: string; name: string; url?: string }> = [];
	export let onSelect: (value: string) => void = () => {};

	let searchValue = '';
	let show = false;
	let inputElement: HTMLInputElement;
	let dropdownElement: HTMLDivElement;
	let focusedIndex = -1;
	let displayValue = ''; // Separate value for display

	$: filteredItems = searchValue
		? items.filter((item) => 
			item.name.toLowerCase().includes(searchValue.toLowerCase())
		)
		: items;

	$: selectedItem = items.find((item) => String(item.idx) === String(value));

	// Update input value when show state or selectedItem changes
	$: if (inputElement) {
		if (show) {
			inputElement.value = displayValue;
		} else {
			inputElement.value = selectedItem ? selectedItem.name : '';
		}
	}

	// Handle option selection
	function handleSelect(item: any) {
		value = item.idx;
		onSelect(item.idx);
		show = false;
		searchValue = '';
		displayValue = '';
		focusedIndex = -1;
	}

	// Handle input changes for filtering
	function handleInput(event: Event) {
		const target = event.target as HTMLInputElement;
		searchValue = target.value;
		displayValue = target.value;
		focusedIndex = -1; // Reset focus when typing
	}

	// Handle keyboard navigation
	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			if (focusedIndex >= 0 && focusedIndex < filteredItems.length) {
				handleSelect(filteredItems[focusedIndex]);
			} else if (filteredItems.length > 0) {
				handleSelect(filteredItems[0]);
			}
		} else if (event.key === 'Escape') {
			event.preventDefault();
			show = false;
			searchValue = '';
			displayValue = '';
			focusedIndex = -1;
		} else if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (show && filteredItems.length > 0) {
				focusedIndex = Math.min(focusedIndex + 1, filteredItems.length - 1);
				// Update display value to show focused item without changing filter
				displayValue = filteredItems[focusedIndex].name;
				if (inputElement) {
					inputElement.value = displayValue;
				}
			}
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (show && filteredItems.length > 0) {
				focusedIndex = Math.max(focusedIndex - 1, 0);
				// Update display value to show focused item without changing filter
				displayValue = filteredItems[focusedIndex].name;
				if (inputElement) {
					inputElement.value = displayValue;
				}
			}
		}
	}

	// Toggle dropdown visibility
	function toggleDropdown() {
		show = !show;
		if (show) {
			setTimeout(() => {
				inputElement?.focus();
			}, 0);
		} else {
			searchValue = '';
			displayValue = '';
			focusedIndex = -1;
		}
	}

	// Close dropdown when clicking outside
	function handleClickOutside(event: MouseEvent) {
		if (dropdownElement && !dropdownElement.contains(event.target as Node)) {
			show = false;
			searchValue = '';
			displayValue = '';
			focusedIndex = -1;
		}
	}

	// Add click outside listener
	$: if (show) {
		setTimeout(() => {
			document.addEventListener('click', handleClickOutside);
		}, 0);
	} else {
		document.removeEventListener('click', handleClickOutside);
	}
</script>

<div class="relative" bind:this={dropdownElement}>
	<!-- Trigger/Input field -->
	<button 
		type="button"
		class="text-sm px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 cursor-pointer hover:border-gray-300 dark:hover:border-gray-600 transition-colors w-full text-left"
		on:click={toggleDropdown}
	>
		<div class="flex items-center justify-between">
			<input
				bind:this={inputElement}
				on:input={handleInput}
				on:keydown={handleKeydown}
				class="w-full bg-transparent outline-hidden border-none focus:outline-none text-sm cursor-pointer pr-6"
				placeholder={placeholder}
				readonly={!show}
			/>
			<ChevronDown className="absolute right-2 w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform {show ? 'rotate-180' : ''}" />
		</div>
	</button>
	
	<!-- Dropdown -->
	{#if show}
		<div 
			class="absolute top-full left-0 right-0 rounded-lg bg-white dark:bg-gray-900 dark:text-white shadow-lg border border-gray-300/30 dark:border-gray-700/40 z-50 max-h-80 overflow-y-auto"
			transition:fly={{ y: -10, duration: 200 }}
		>
			{#each filteredItems as item, index}
				<button
					type="button"
					class="flex w-full font-medium select-none items-center py-2 pl-3 pr-1.5 text-sm text-gray-700 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-850 rounded-lg cursor-pointer transition-all duration-75 text-left {index === focusedIndex ? 'bg-gray-100 dark:bg-gray-850' : ''}"
					on:click={() => handleSelect(item)}
				>
					<span class="truncate flex-1">{item.name}</span>

					{#if value === String(item.idx)}
						<div class="ml-auto flex-shrink-0">
							<Check />
						</div>
					{/if}
				</button>
			{:else}
				<div class="block px-5 py-2 text-sm text-gray-700 dark:text-gray-100">
					No files found
				</div>
			{/each}
		</div>
	{/if}
</div> 