<script lang="ts">
import { computePosition, offset, flip, shift, autoPlacement } from '@floating-ui/dom';
import Tooltip from '../common/Tooltip.svelte';
import FaceIcon from '../icons/FaceSmile.svelte'
import { getContext } from 'svelte';
import { settings } from '$lib/stores';
import { Button } from 'bits-ui';

const i18n = getContext('i18n');

let ResponseTypeSelectorEnabled = false;
let ResponseType = 'Default';
const ResponseOptions=['Default','Professional', 'Creative','Constructive'];

let ResponseButtonRef;
let ResponseDropdownRef;
let ResponseDropdownStyle = '';

async function ResponseDropdownPosition() {
    if (ResponseButtonRef && ResponseDropdownRef) {
        const { x, y } = await computePosition(ResponseButtonRef, ResponseDropdownRef, {
            placement: 'bottom-start',
            strategy: 'absolute',
        });
        ResponseDropdownStyle = `position: absolute; top: ${y}px; left: ${x}px; z-index: 50;`;
    }
}
function ResponseToggleDropdown() {
    ResponseTypeSelectorEnabled = !ResponseTypeSelectorEnabled;
    if (ResponseTypeSelectorEnabled && ResponseButtonRef) {
        ResponseDropdownPosition();
    }
}


</script>

<div class="relative inline-block text-left">
    <Tooltip
        content={$i18n.t('Select tone of response')}
        placement="top"
    >
        <button
            bind:this={ResponseButtonRef}
            class="px-2 py-1 flex gap-1.5 text-sm transition-colors duration-300 max-w-full hover:bg-gray-50 dark:hover:bg-gray-800
                {ResponseTypeSelectorEnabled
                    ? ' text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
                    : 'bg-transparent text-gray-600 dark:text-gray-300 '} {($settings?.highContrastMode ??
                    false)
                        ? 'm-1'
                        : 'focus:outline-hidden rounded-full'}"
            on:click={ResponseToggleDropdown}
        >
            {#if ResponseType === 'Default'}
                <FaceIcon/>
            {:else}
                {ResponseType}
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

<div style= {ResponseDropdownStyle} class:hidden={!ResponseTypeSelectorEnabled}>
    <div class="absolute rounded-md shadow-lg bg-white dark:bg-gray-800 ring-1 ring-black/5 z-50">
        {#each ResponseOptions as option}
            <button
                type="button"
                class="flex items-center px-1 py-1 text-sm text-left font-small w-full hover:bg-gray-700 cursor-pointer
                    {ResponseType === option
                        ? 'text-sky-500 dark:text-sky-300 bg-sky-50 dark:bg-sky-200/5'
                        : ''}"
                on:click={() => {
                    ResponseType = option;
                    ResponseTypeSelectorEnabled = false;
                    }}
            >
                {option}
            </button>
        {/each}
    </div>
</div>