<script lang="ts">
	import { createEventDispatcher, tick, onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import Check from '../../icons/Check.svelte';
	import ChevronDown from '../../icons/ChevronDown.svelte';
	import Tooltip from '../../common/Tooltip.svelte';
	import XMark from '../../icons/XMark.svelte';

	const dispatch = createEventDispatcher();

	export let value = '';
	export let placeholder = 'Select a file';
	export let items: Array<{ idx: string; name: string; url?: string }> = [];
	export let onSelect: (value: string) => void = () => {};
	export let onOpen: () => void = () => {};

	let searchValue = '';
	let show = false;
	let inputElement: HTMLInputElement;
	let dropdownElement: HTMLDivElement;
	let listElement: HTMLDivElement;
	let openUp = false;
	let focusedIndex = -1;
	let displayValue = ''; // Separate value for display

	// Tooltip overflow helpers and state
	let itemRefs: Array<HTMLSpanElement | null> = [];
	let overflowMap: Record<number, boolean> = {};
	let isTriggerOverflowing = false;
	// Tooltip content for trigger, only when overflowed and closed
	$: triggerTooltipContent = !show && isTriggerOverflowing && selectedItem ? selectedItem.name : '';

	function isOverflowing(el: HTMLElement): boolean {
		if (!el) return false;
		// consider both horizontal and vertical overflow (for 2-line clamp)
		return el.scrollWidth - el.clientWidth > 1 || el.scrollHeight - el.clientHeight > 1;
	}

	// Action to collect per-item text element refs (for overflow detection)
	function collectItemRef(node: HTMLElement, index: number) {
		itemRefs[index] = node as HTMLSpanElement;
		return {
			update(i: number) {
				itemRefs[i] = node as HTMLSpanElement;
			},
			destroy() {
				if (itemRefs[index] === node) itemRefs[index] = null;
			}
		};
	}

	// Button refs to enable scrolling to the selected item
	let itemButtonRefs: Array<HTMLButtonElement | null> = [];
	function collectItemButtonRef(node: HTMLElement, index: number) {
		itemButtonRefs[index] = node as HTMLButtonElement;
		return {
			update(i: number) {
				itemButtonRefs[i] = node as HTMLButtonElement;
			},
			destroy() {
				if (itemButtonRefs[index] === node) itemButtonRefs[index] = null;
			}
		};
	}

	function scrollToIndex(index: number) {
		if (index == null || index < 0) return;
		const el = itemButtonRefs[index];
		if (el) {
			el.scrollIntoView({ block: 'nearest' });
		}
	}

	// Recalculate overflows
	async function recalcItemOverflows() {
		await tick();
		const next: Record<number, boolean> = {};
		filteredItems.forEach((_, i) => {
			const el = itemRefs[i] as HTMLElement | null | undefined;
			next[i] = !!(el && isOverflowing(el));
		});
		overflowMap = next;
	}

	async function recalcOverflows() {
		await tick();
		if (inputElement && !show) {
			isTriggerOverflowing = isOverflowing(inputElement);
		}
		if (show) {
			await recalcItemOverflows();
		}
	}

	function updatePlacement() {
		if (!dropdownElement) return;
		const rect = dropdownElement.getBoundingClientRect();
		const spaceBelow = window.innerHeight - rect.bottom;
		const spaceAbove = rect.top;
		const margin = 8;
		const desired = 320; // 20rem
		const preferUp = spaceBelow < desired && spaceAbove > spaceBelow;
		openUp = preferUp;
		if (listElement) {
			const avail = preferUp ? (spaceAbove - margin) : (spaceBelow - margin);
			const max = Math.max(120, Math.min(desired, avail));
			if (isFinite(max)) {
				listElement.style.maxHeight = `${max}px`;
			}
		}
	}

	onMount(() => {
		const handler = () => {
			recalcOverflows();
			if (show) updatePlacement();
		};
		const scrollHandler = () => {
			if (show) updatePlacement();
		};
		window.addEventListener('resize', handler);
		window.addEventListener('scroll', scrollHandler, true);
		return () => {
			window.removeEventListener('resize', handler);
			window.removeEventListener('scroll', scrollHandler, true);
		};
	});

	// Reactive checks
	$: if (inputElement && !show) {
		isTriggerOverflowing = isOverflowing(inputElement);
	}
	$: if (show) {
		recalcItemOverflows();
		updatePlacement();
	}

	$: filteredItems = (searchValue
		? items.filter((item) => 
			item.name.toLowerCase().includes(searchValue.toLowerCase())
		)
		: items
	).slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

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
	function handleSelect(item: { idx: string; name: string; url?: string }) {
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

			// Notify parent (optional)
			onOpen?.();

			// When opening, highlight the currently selected item (if any) and scroll to it
			const selectedIdx = filteredItems.findIndex((it) => String(it.idx) === String(value));
			focusedIndex = selectedIdx;
			tick().then(() => {
				updatePlacement();
				scrollToIndex(selectedIdx);
			});
		} else {
			searchValue = '';
			displayValue = '';
			focusedIndex = -1;
		}
	}

	// Clear current selection without toggling dropdown
	async function clearSelection(e?: MouseEvent | KeyboardEvent) {
		// prevent triggering parent button click
		if (e && 'stopPropagation' in e) e.stopPropagation();
		if (e && 'preventDefault' in e) e.preventDefault();

		value = '';
		onSelect('');
		searchValue = '';
		displayValue = '';
		focusedIndex = -1;

		if (inputElement) {
			inputElement.value = '';
		}

		await tick();
		recalcOverflows();
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
	<Tooltip content={triggerTooltipContent} placement="top" offset={[0, 6]} className="block w-full">
		<button 
			type="button"
			class="text-sm px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 cursor-pointer hover:border-gray-300 dark:hover:border-gray-600 transition-colors w-full text-left"
			aria-haspopup="listbox"
			aria-expanded={show}
			aria-controls="filter-select-list"
			on:click={toggleDropdown}
		>
			<div class="flex items-center justify-between relative">
				<input
					bind:this={inputElement}
					on:input={handleInput}
					on:keydown={handleKeydown}
					class="w-full bg-transparent outline-hidden border-none focus:outline-none text-sm cursor-pointer pr-16 overflow-hidden text-ellipsis"
					placeholder={placeholder}
					readonly={!show}
				/>

				{#if selectedItem}
					<Tooltip content="Clear" placement="top" offset={[0, 6]}>
						<span
							role="button"
							tabindex="0"
							aria-label="Clear selection"
							class="absolute inset-y-0 right-8 my-auto flex items-center justify-center p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
							on:click={clearSelection}
							on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') clearSelection(e); }}
						>
							<XMark className="w-4 h-4" />
						</span>
					</Tooltip>
				{/if}

				<ChevronDown className="absolute right-2 w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform {show ? 'rotate-180' : ''}" />
			</div>
		</button>
	</Tooltip>
	
	<!-- Dropdown -->
	{#if show}
		<div 
			id="filter-select-list"
			role="listbox"
			bind:this={listElement}
			class="absolute left-0 rounded-lg bg-white dark:bg-gray-900 dark:text-white shadow-lg border border-gray-300/30 dark:border-gray-700/40 z-50 max-h-80 overflow-y-auto {openUp ? 'bottom-full mb-1' : 'top-full mt-1'}"
			style="min-width: 100%; width: max-content; max-width: min(90vw, 40rem);"
			transition:fly={{ y: openUp ? 10 : -10, duration: 200 }}
		>
			{#each filteredItems as item, index}
				<button
					type="button"
					role="option"
					aria-selected={value === String(item.idx)}
					class={`flex w-full gap-2 font-medium select-none items-start py-2.5 pl-3 pr-2 text-sm rounded-lg cursor-pointer transition-all duration-75 text-left ${
						index === focusedIndex || String(value) === String(item.idx)
							? 'bg-sky-50 dark:bg-sky-200/5 text-sky-700 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-900/40'
							: 'text-gray-700 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-850'
					}`}
					use:collectItemButtonRef={index}
					on:click={() => handleSelect(item)}
				>
					<Tooltip content={overflowMap[index] ? item.name : ''} placement="top" offset={[0, 6]} className="flex-1 block">
						<span use:collectItemRef={index} class="flex-1 two-line-ellipsis break-words whitespace-normal leading-snug">{item.name}</span>
					</Tooltip>

					{#if value === String(item.idx)}
						<div class="ml-auto flex-shrink-0 mt-0.5 text-sky-600 dark:text-sky-300">
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

<style>
	.two-line-ellipsis {
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		overflow: hidden;
	}
</style>