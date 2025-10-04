<script lang="ts">
import { computePosition, offset, flip, shift, autoPlacement } from '@floating-ui/dom';
import Tooltip from '../common/Tooltip.svelte';
import CalendarIcon from '../icons/CalendarSolid.svelte';
import { getContext } from 'svelte';
import { settings } from '$lib/stores';
import CustomDateMenu from '../chat/CustomDateMenu.svelte';

const i18n = getContext('i18n');

let DateSelectorEnabled = false;
let SelectedDate = 'All';
const DateOptions = ['All','Last 7 days', 'Last 30 days','Last year', 'Custom'];

let DateButtonRef;
let DateDropdownRef;
let DateDropdownStyle = '';

async function DateDropdownPosition() {
    if (DateButtonRef && DateDropdownRef) {
        const { x, y } = await computePosition(DateButtonRef, DateDropdownRef, {
            placement: 'bottom-start',
            strategy: 'absolute',
        });
        DateDropdownStyle = `position: absolute; top: ${y}px; right: ${x}px; z-index: 50;`;
    }
}
function DateToggleDropdown() {
    DateSelectorEnabled = !DateSelectorEnabled;
    if (DateSelectorEnabled && DateButtonRef) {
        DateDropdownPosition();
    }
}

let ShowCustomMenu = false;

function handleapply(e) {
    const { from, to } = e.detail;
    SelectedDate = `${from} → ${to}`;
    ShowCustomMenu = false;
    DateSelectorEnabled = false;
}

function handlecancel(e) {
    ShowCustomMenu = false;
    DateSelectorEnabled = true;
}
</script>

<div class='relative inline-block text-left'>
    <Tooltip
        content={$i18n.t('Select time range')}
        placement="top"
    >
        <button
            bind:this={DateButtonRef}
            class="px-2 py-1 flex gap-1.5 text-sm transition-colors duration-300 max-w-full hover:bg-gray-50 dark:hover:bg-gray-800
                {DateSelectorEnabled
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
        class="absolute rounded-md shadow-lg w-full bg-white dark:bg-gray-800 ring-1 ring-black/5 z-50"
    >
        {#each DateOptions as option}
            <button
                type="button"
                class="flex w-full text-left items-center px-1 py-1 text-sm font-small hover:bg-gray-700 cursor-pointer
                    {SelectedDate === option
                        ? 'text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
                        :''}"
                on:click={() => {
                    SelectedDate = option;
                    if (option === 'Custom') {
                        ShowCustomMenu = true;
                    } else {
                        DateSelectorEnabled = false;
                        ShowCustomMenu = false;
                    }
                }}
            >
                {option}
            </button>
            
            {#if option === 'Custom' && ShowCustomMenu}
                <div class="fixed inset-0 z-[999] flex items-center justify-center bg-black/30"
                    on:click={handlecancel}
                >
                    <div class='rounded-md shadow-lg w-80 bg-white dark:bg-gray-800 ring-1 ring-black/5 z-50'>
                        <CustomDateMenu
                            on:apply={handleapply}
                            on:cancel={handlecancel}
                        />
                    </div>
                </div>
            {/if}
        {/each}
    </div>
{/if}

