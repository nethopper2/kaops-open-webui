<script lang="ts">
import Spinner from '../common/Spinner.svelte';
import { SvelteFlowProvider } from '@xyflow/svelte';
import { Pane, PaneResizer } from 'paneforge';
import { createEventDispatcher, getContext, onDestroy, onMount } from 'svelte';
import Drawer from '../common/Drawer.svelte';
import EllipsisVertical from '../icons/EllipsisVertical.svelte';
import {
	showPrivateAiModelToolbar, activeRightPane, privateAiModelToolbarComponent, currentSelectedModelId,
	privateAiSelectedModelAvatarUrl, chatId
} from '$lib/stores';
import { calcMinSize, createPaneBehavior, isPaneHandle, type PaneHandle, rightPaneSize } from '$lib/utils/pane';
import XMark from '$lib/components/icons/XMark.svelte';
import { loadPrivateAiToolbarState, type PrivateAiToolbarState } from '$lib/private-ai/state';

/**
 * REMINDER: Auto open/close of this component is orchestrated by Chat.svelte via appHooks 'model.changed'.
 */

const dispatch = createEventDispatcher();
const i18n = getContext('i18n');

// Initial state loaded for the current chat+toolbar; passed to inner toolbar component via prop
let initialToolbarState: PrivateAiToolbarState | null = null;
let lastLoadedKey = '';
let isLoading = false;
async function loadToolbarStateIfNeeded() {
	try {
		const cId = $chatId;
		const tId = $currentSelectedModelId;
		if (!cId || !tId) return;
		const key = `${cId}|${tId}`;
		if (lastLoadedKey === key && initialToolbarState !== null) return;
		initialToolbarState = await loadPrivateAiToolbarState(cId, tId);
		lastLoadedKey = key;
	} catch {
		// ignore
	}
}

export let pane: unknown;
let activeInPaneGroup = false;
$: activeInPaneGroup = $activeRightPane === 'private';
// When the toolbar is shown and the component is resolved, attempt to load state
$: if ($showPrivateAiModelToolbar) {
	// start loading when toolbar is requested; component may resolve async as well
	isLoading = true;
	loadToolbarStateIfNeeded().finally(() => {
		// only clear loading once the component is resolved too
		if ($privateAiModelToolbarComponent) {
			isLoading = false;
		}
	});
}

// Also, clear loading when the component becomes available later (dynamic import)
$: if ($showPrivateAiModelToolbar && $privateAiModelToolbarComponent && isLoading) {
	isLoading = false;
}

let mediaQuery: MediaQueryList;
let largeScreen = false;
let minSize = 0;
let hasExpanded = false;
let paneHandle: PaneHandle | null = null;
$: paneHandle = isPaneHandle(pane) ? (pane as PaneHandle) : null;

const behavior = createPaneBehavior({
	storageKey: 'privateAiToolbarSize',
	showStore: showPrivateAiModelToolbar,
	isActiveInPaneGroup: () => activeInPaneGroup,
	getMinSize: () => minSize
});

// Public helper to open/resize the pane (delegates to shared behavior)
export const openPane = async () => {
	await behavior.openPane(paneHandle, largeScreen);
};

const handleMediaQuery = async (e: MediaQueryList | MediaQueryListEvent) => {
	const matches = 'matches' in e ? e.matches : (e as MediaQueryList).matches;
	if (matches) {
		largeScreen = true;
	} else {
		largeScreen = false;
		pane = null;
	}
};

onMount(() => {
	// listen to resize 1024px
	mediaQuery = window.matchMedia('(min-width: 1024px)');
	const mqListener = (ev: MediaQueryListEvent) => handleMediaQuery(ev);
	mediaQuery.addEventListener('change', mqListener);
	handleMediaQuery(mediaQuery);

	const container = document.getElementById('chat-container');
	const MIN_SIZE = 350;

	if (container) {
		minSize = calcMinSize(container, MIN_SIZE);

		const resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				minSize = calcMinSize(entry.target as HTMLElement, MIN_SIZE);

				if ($showPrivateAiModelToolbar && activeInPaneGroup) {
					if (paneHandle && paneHandle.isExpanded() && paneHandle.getSize() < minSize) {
						behavior.clamp(paneHandle, minSize);
					}
				}
			}
		});
		resizeObserver.observe(container);
	}
});

onDestroy(() => {
	showPrivateAiModelToolbar.set(false);
});
</script>

<SvelteFlowProvider>
	{#if !largeScreen}
		{#if $showPrivateAiModelToolbar}
			<Drawer
				show={$showPrivateAiModelToolbar}
				onClose={() => {
          showPrivateAiModelToolbar.set(false);
        }}
			>
				<div class="h-full">
					<div
						class="h-full max-h-[100dvh] bg-white text-gray-700 dark:bg-black dark:text-gray-300 flex items-center justify-center">
      {#if isLoading}
								<div class="flex items-center justify-center py-8">
									<div class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
										<Spinner className="size-4" />
										<span>{$i18n.t('Loading...')}</span>
									</div>
								</div>
							{:else if $privateAiModelToolbarComponent}
								<svelte:component this={$privateAiModelToolbarComponent} modelId={$currentSelectedModelId} initialState={initialToolbarState} />
							{:else}
								<div class="text-center">
									<div class="text-base font-semibold">{$i18n.t('Model Sidekick')}</div>
									<div
										class="text-sm text-gray-500 dark:text-gray-400 mt-1">{$i18n.t('No toolbar available for this model.')}</div>
								</div>
							{/if}
					</div>
				</div>
			</Drawer>
		{/if}
	{:else}
		{#if activeInPaneGroup && $showPrivateAiModelToolbar}
			<PaneResizer class="relative flex w-2 items-center justify-center bg-background group"
									 id="private-ai-toolbar-resizer">
				<div class="z-10 flex h-7 w-5 items-center justify-center rounded-xs">
					<EllipsisVertical className="size-4 invisible group-hover:visible" />
				</div>
			</PaneResizer>
		{/if}

		{#if activeInPaneGroup}
			<Pane
				bind:pane
				defaultSize={$rightPaneSize || minSize}
    onResize={(size) => {
          // Mark that the pane has expanded at least once when size > 0
          if (size > 0) {
            hasExpanded = true;
          }
          if ($showPrivateAiModelToolbar && paneHandle && paneHandle.isExpanded()) {
            if (size < minSize) {
              behavior.clamp(paneHandle, minSize);
            }
            behavior.persistSize(size, minSize);
            rightPaneSize.set(size);
          }
        }}
				onCollapse={() => {
					const opening = behavior.isOpening();
					// Ignore collapse events while we are in the process of opening to a visible size
          if (opening) return;
          // Only hide after the pane has actually expanded at least once; ignore initial mount collapse
          if (hasExpanded) {
            showPrivateAiModelToolbar.set(false);
          }
        }}
				collapsible={true}
				class="z-10"
			>
				{#if $showPrivateAiModelToolbar}
					<div class="flex max-h-full min-h-full">
						<div
							class="w-full bg-white dark:shadow-lg dark:bg-gray-850 border border-gray-100 dark:border-gray-850 z-40 pointer-events-auto overflow-y-auto scrollbar-hidden">
							<div class="flex flex-col w-full h-full">
								<div class="flex items-center justify-between dark:text-gray-100 mb-2 p-2">
									<div class="flex items-center gap-2">
										<img src={$privateAiSelectedModelAvatarUrl} alt="" class="size-5 rounded-full object-cover"
												 draggable="false" />
										<div class=" text-lg font-medium self-center font-primary">{$i18n.t('Model Sidekick')}</div>
									</div>
									<button
										class="self-center"
										on:click={() => {
										dispatch('close');
									}}
									>
										<XMark className="size-3.5" />
									</button>
								</div>

        {#if isLoading}
								<div class="flex items-center justify-center py-8">
									<div class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
										<Spinner className="size-4" />
										<span>{$i18n.t('Loading...')}</span>
									</div>
								</div>
							{:else if $privateAiModelToolbarComponent}
								<svelte:component this={$privateAiModelToolbarComponent} modelId={$currentSelectedModelId} initialState={initialToolbarState} />
							{:else}
								<div class="text-center">
									<div
										class="text-sm text-gray-500 dark:text-gray-400 mt-1">{$i18n.t('Not available for this model.')}</div>
								</div>
							{/if}
							</div>
						</div>
					</div>
				{/if}
			</Pane>
		{/if}
	{/if}
</SvelteFlowProvider>
