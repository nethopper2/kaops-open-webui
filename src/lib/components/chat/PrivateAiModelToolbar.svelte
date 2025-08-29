<script lang="ts">
import { SvelteFlowProvider } from '@xyflow/svelte';
import { Pane, PaneResizer } from 'paneforge';
import { createEventDispatcher, getContext, onDestroy, onMount } from 'svelte';
import Drawer from '../common/Drawer.svelte';
import EllipsisVertical from '../icons/EllipsisVertical.svelte';
import {
	showPrivateAiModelToolbar, activeRightPane, privateAiModelToolbarComponent, currentSelectedModelId,
	privateAiSelectedModelAvatarUrl
} from '$lib/stores';
import { calcMinSize, createPaneBehavior, isPaneHandle, type PaneHandle, rightPaneSize } from '$lib/utils/pane';
import XMark from '$lib/components/icons/XMark.svelte';

const dispatch = createEventDispatcher();
const i18n = getContext('i18n');

export let pane: unknown;
let activeInPaneGroup = false;
$: activeInPaneGroup = $activeRightPane === 'private';

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

// TODO: cleanup
// Keep Pane width in sync with visibility on desktop (defer resizes to avoid assertions)
// $: if (largeScreen && activeInPaneGroup && paneHandle && $showPrivateAiModelToolbar) {
//   if (!paneHandle.isExpanded() || paneHandle.getSize() === 0) {
//     openPane?.();
//   }
// }
// TODO: cleanup
// Ensure pane opens as soon as it becomes active in the PaneGroup (child-driven open)
// $: if (largeScreen && activeInPaneGroup && $showPrivateAiModelToolbar) {
//   openPane?.();
// }
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
				<div class="px-6 py-4 h-full">
					<div
						class="h-full max-h-[100dvh] bg-white text-gray-700 dark:bg-black dark:text-gray-300 flex items-center justify-center">
						{#if $privateAiModelToolbarComponent}
							<svelte:component this={$privateAiModelToolbarComponent} modelId={$currentSelectedModelId} />
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
					// Ignore collapse events while we are in the process of opening to a visible size
          if (behavior.isOpening()) return;
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
							class="w-full px-4 py-4 bg-white dark:shadow-lg dark:bg-gray-850 border border-gray-100 dark:border-gray-850 z-40 pointer-events-auto overflow-y-auto scrollbar-hidden">
							<div class="flex flex-col w-full h-full">
								<div class="flex items-center justify-between dark:text-gray-100 mb-2">
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

								{#if $privateAiModelToolbarComponent}
									<svelte:component this={$privateAiModelToolbarComponent} modelId={$currentSelectedModelId} />
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
