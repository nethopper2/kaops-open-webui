<script lang="ts">
import { computePosition, offset, flip, shift, autoPlacement } from '@floating-ui/dom';
import Tooltip from '$lib/components/common/Tooltip.svelte';
import CalendarIcon from '$lib/components/icons/CalendarSolid.svelte';
import { createEventDispatcher, getContext, onMount, onDestroy } from 'svelte';
import { settings } from '$lib/stores';
import CustomDateMenu from '$lib/components/chat/ControlPanel/CustomDateMenu.svelte';

const i18n = getContext('i18n');
const dispatch = createEventDispatcher();
const DateOptions = ['All','Last 7 days', 'Last 30 days','Last year', 'Custom'];

let DateSelectorEnabled = false;
let SelectedDate = 'All';
let DateButtonRef;
let DateDropdownRef;
let DateDropdownStyle = '';
let ShowCustomMenu = false;

async function DateDropdownPosition() {
    if (DateButtonRef && DateDropdownRef) {
        const { x, y } = await computePosition(DateButtonRef, DateDropdownRef, {
            placement: 'bottom-start',
            strategy: 'absolute',
        });
        
        DateDropdownStyle = `position: absolute; top: ${y}px; left: ${x}px; z-index: 50;`;
    }
}

function DateToggleDropdown() {
    DateSelectorEnabled = !DateSelectorEnabled;
    if (DateSelectorEnabled && DateButtonRef) {
        DateDropdownPosition();
    }
}

function handlePresetDate(option) {
    SelectedDate = option;
    if (option === 'Custom') {
        ShowCustomMenu = true;
    } else {
        DateSelectorEnabled = false;
        ShowCustomMenu = false;
        
        dispatch('dateselected', { type: 'preset_range', value: option });
    }
}

function handleCustomapply(e) {
    const { from, to } = e.detail;
    const reformatDate = (isoString) => {
        const [year, month, day] = isoString.split('-');
        return `${month}/${day}/${year}`;
    };
    SelectedDate = `${reformatDate(from)} → ${reformatDate(to)}`;
    ShowCustomMenu = false;
    DateSelectorEnabled = false;

    dispatch('dateselected', { type: 'custom_range', value: SelectedDate })
}

function handleCustomcancel(e) {
    ShowCustomMenu = false;
    DateSelectorEnabled = false;
    SelectedDate = 'All';
}

function handleClickOutside(event: MouseEvent) {
  if (DateSelectorEnabled && DateDropdownRef && !DateDropdownRef.contains(event.target) && !DateButtonRef.contains(event.target)) {
    DateSelectorEnabled = false;
  }
}

onMount(() => {
  document.addEventListener('click', handleClickOutside);
});

onDestroy(() => {
  document.removeEventListener('click', handleClickOutside);
});

</script>

<div class='relative inline-block text-left'>
    <Tooltip
        content={$i18n.t('Select date range')}
        placement="top"
    >
        <button
            bind:this={DateButtonRef}
            class="px-2 py-1 flex gap-1.5 text-sm transition-colors duration-300 max-w-full hover:bg-gray-50 dark:hover:bg-gray-800
                {(DateSelectorEnabled || SelectedDate !== 'All')
                    ? ' text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
                    : 'bg-transparent text-gray-600 dark:text-gray-300 '} {($settings?.highContrastMode ??
                    false)
                        ? 'm-1'
                        : 'focus:outline-hidden rounded-full'}"
            on:click={DateToggleDropdown}
        >
            {#if SelectedDate === 'All'}
                <CalendarIcon/>
            {:else}
                {SelectedDate}
            {/if}
            <svg
                class="w-4 h-4 ml-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
            >
                <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M19 9l-7 7-7-7"
                />
            </svg>
        </button>
    </Tooltip>
</div>

{#if DateSelectorEnabled}
    <div
        bind:this={DateDropdownRef}
        style={DateDropdownStyle}
        class="absolute rounded-md shadow-lg max-w-full bg-white dark:bg-gray-800 ring-1 ring-black/5 z-50 min-w-max"
    >
        {#each DateOptions as option}
            <button
                type="button"
                class="flex w-full text-left items-center px-1 py-1 text-sm font-small hover:bg-gray-700 cursor-pointer
                    {SelectedDate === option
                        ? 'text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
                        :''}"
                on:click={() => {handlePresetDate(option)
                }}
            >
                {option}
            </button>
            
            {#if option === 'Custom' && ShowCustomMenu}
                <div class="fixed inset-0 z-[999] flex items-start justify-center bg-black/30"
                    on:click={handleCustomcancel}
                >
                    <div class='mt-10 ml-40 rounded-md shadow-lg w-80 bg-white dark:bg-gray-800 ring-1 ring-black/5 z-50'>
                        <CustomDateMenu
                            on:apply={handleCustomapply}
                            on:cancel={handleCustomcancel}
                        />
                    </div>
                </div>
            {/if}
        {/each}
    </div>
{/if}

