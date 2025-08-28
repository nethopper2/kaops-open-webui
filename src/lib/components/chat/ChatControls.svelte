<script lang="ts">
	import { SvelteFlowProvider } from '@xyflow/svelte';
	import { slide } from 'svelte/transition';
	import { Pane, PaneResizer } from 'paneforge';

	import { onDestroy, onMount, tick } from 'svelte';
 import { mobile, showControls, showCallOverlay, showOverview, showArtifacts, activeRightPane } from '$lib/stores';

	import Modal from '../common/Modal.svelte';
	import Controls from './Controls/Controls.svelte';
	import CallOverlay from './MessageInput/CallOverlay.svelte';
	import Drawer from '../common/Drawer.svelte';
	import Overview from './Overview.svelte';
	import EllipsisVertical from '../icons/EllipsisVertical.svelte';
	import Artifacts from './Artifacts.svelte';

	export let history;
	export let models = [];

	export let chatId = null;

	export let chatFiles = [];
	export let params = {};

	export let eventTarget: EventTarget;
	export let submitPrompt: Function;
	export let stopResponse: Function;
	export let showMessage: Function;
	export let files;
	export let modelId;

	export let pane;
	// When false, keep component mounted but do not render its Pane/Resizer inside the PaneGroup (prevents interference)
	let activeInPaneGroup: boolean = true;
	$: activeInPaneGroup = $activeRightPane === 'controls';
	
	let mediaQuery;
	let largeScreen = false;
	let dragged = false;

	let minSize = 0;

	let hasExpanded = false;
	let opening = false;

	let clampScheduled = false;
	const scheduleClamp = () => {
		if (clampScheduled) return;
		clampScheduled = true;
		setTimeout(() => {
			clampScheduled = false;
			if ($showControls && pane && typeof pane.isExpanded === "function" && typeof pane.getSize === "function") {
				try {
					if (pane.isExpanded() && pane.getSize() < minSize) {
						pane.resize(minSize);
					}
				} catch (err) {
					console.warn('Failed to clamp pane size', err);
				}
			}
		}, 0);
	};

	export const openPane = () => {
		// Only attempt to resize when the desktop PaneGroup is active and this pane is participating
		if (!largeScreen || !activeInPaneGroup || !pane) return;
		const stored = parseInt(localStorage?.chatControlsSize);
		const target = stored && stored > 0 ? stored : Math.max(minSize, 1);
		try {
			if (typeof pane.getSize === 'function') {
				const current = pane.getSize();
				if (current === target) return;
			}
			pane.resize(target);
		} catch (e) {
			// ignore resize errors to avoid noisy logs; safe because pane state will be reconciled by Paneforge
		}
	};

	const handleMediaQuery = async (e) => {
		if (e.matches) {
			largeScreen = true;

			if ($showCallOverlay) {
				showCallOverlay.set(false);
				await tick();
				showCallOverlay.set(true);
			}
		} else {
			largeScreen = false;

			if ($showCallOverlay) {
				showCallOverlay.set(false);
				await tick();
				showCallOverlay.set(true);
			}
			pane = null;
		}
	};

	const onMouseDown = (event) => {
		dragged = true;
	};

	const onMouseUp = (event) => {
		dragged = false;
	};

	onMount(() => {
		// listen to resize 1024px
		mediaQuery = window.matchMedia('(min-width: 1024px)');

		mediaQuery.addEventListener('change', handleMediaQuery);
		handleMediaQuery(mediaQuery);

		// Select the container element you want to observe
		const container = document.getElementById('chat-container');

 	// initialize the minSize based on the container width
		minSize = Math.floor((350 / container.clientWidth) * 100);

		// Create a new ResizeObserver instance
		const resizeObserver = new ResizeObserver((entries) => {
			for (let entry of entries) {
				const width = entry.contentRect.width;
				// calculate the percentage of 200px
				const percentage = (350 / width) * 100;
				// set the minSize to the percentage, must be an integer
				minSize = Math.floor(percentage);

				if ($showControls) {
					if (pane && pane.isExpanded && pane.getSize && pane.isExpanded() && pane.getSize() < minSize) {
						scheduleClamp();
					}
				}
			}
		});

		// Start observing the container's size changes
		resizeObserver.observe(container);

		document.addEventListener('mousedown', onMouseDown);
		document.addEventListener('mouseup', onMouseUp);
	});

	onDestroy(() => {
		showControls.set(false);

		mediaQuery.removeEventListener('change', handleMediaQuery);
		document.removeEventListener('mousedown', onMouseDown);
		document.removeEventListener('mouseup', onMouseUp);
	});

	const closeHandler = () => {
		showControls.set(false);
		showOverview.set(false);
		showArtifacts.set(false);

		if ($showCallOverlay) {
			showCallOverlay.set(false);
		}
	};

	$: if (!chatId) {
		closeHandler();
	}

	// Ensure the pane actually opens to a visible width when activated in the PaneGroup (desktop)
	$: if (largeScreen && activeInPaneGroup && $showControls && pane && !opening) {
		opening = true;
		// Defer to next frame to ensure pane binding is ready and avoid re-entrant resize
		tick().then(() => {
			requestAnimationFrame(() => {
				try {
					openPane?.();
				} catch (err) {
					// ignore
				}
				opening = false;
			});
		});
	}
</script>

<SvelteFlowProvider>
	{#if !largeScreen}
		{#if $showControls}
			<Drawer
				show={$showControls}
				onClose={() => {
					showControls.set(false);
				}}
			>
				<div
					class=" {$showCallOverlay || $showOverview || $showArtifacts
						? ' h-screen  w-full'
						: 'px-6 py-4'} h-full"
				>
					{#if $showCallOverlay}
						<div
							class=" h-full max-h-[100dvh] bg-white text-gray-700 dark:bg-black dark:text-gray-300 flex justify-center"
						>
							<CallOverlay
								bind:files
								{submitPrompt}
								{stopResponse}
								{modelId}
								{chatId}
								{eventTarget}
								on:close={() => {
									showControls.set(false);
								}}
							/>
						</div>
					{:else if $showArtifacts}
						<Artifacts {history} />
					{:else if $showOverview}
						<Overview
							{history}
							on:nodeclick={(e) => {
								showMessage(e.detail.node.data.message);
							}}
							on:close={() => {
								showControls.set(false);
							}}
						/>
					{:else}
						<Controls
							on:close={() => {
								showControls.set(false);
							}}
							{models}
							bind:chatFiles
							bind:params
						/>
					{/if}
				</div>
			</Drawer>
		{/if}
	{:else}
		<!-- if $showControls -->

		{#if activeInPaneGroup && $showControls}
			<PaneResizer
				class="relative flex w-2 items-center justify-center bg-background group"
				id="controls-resizer"
			>
				<div class="z-10 flex h-7 w-5 items-center justify-center rounded-xs">
					<EllipsisVertical className="size-4 invisible group-hover:visible" />
				</div>
			</PaneResizer>
		{/if}

		{#if activeInPaneGroup}
			<Pane
				bind:pane
				defaultSize={0}
				onResize={(size) => {
					// Mark that the pane has expanded at least once when size > 0
					hasExpanded = hasExpanded || size > 0;
					console.log('size', size, minSize);

					if ($showControls && pane.isExpanded()) {
						if (size < minSize) {
							scheduleClamp();
						}

						if (size < minSize) {
							localStorage.chatControlsSize = 0;
						} else {
							localStorage.chatControlsSize = size;
						}
					}
				}}
				onCollapse={() => {
					// Ignore collapse events while we are in the process of opening to a visible size
					if (opening) return;
					// Only hide after the pane has actually expanded at least once; ignore initial mount collapse
					if (hasExpanded) {
						showControls.set(false);
					}
				}}
				collapsible={true}
				class=" z-10 "
			>
				{#if $showControls}
					<div class="flex max-h-full min-h-full">
						<div
							class="w-full {($showOverview || $showArtifacts) && !$showCallOverlay
								? ' '
								: 'px-4 py-4 bg-white dark:shadow-lg dark:bg-gray-850  border border-gray-100 dark:border-gray-850'} z-40 pointer-events-auto overflow-y-auto scrollbar-hidden"
							id="controls-container"
						>
							{#if $showCallOverlay}
								<div class="w-full h-full flex justify-center">
									<CallOverlay
										bind:files
										{submitPrompt}
										{stopResponse}
										{modelId}
										{chatId}
										{eventTarget}
										on:close={() => {
											showControls.set(false);
										}}
									/>
								</div>
							{:else if $showArtifacts}
								<Artifacts {history} overlay={dragged} />
							{:else if $showOverview}
								<Overview
									{history}
									on:nodeclick={(e) => {
										if (e.detail.node.data.message.favorite) {
											history.messages[e.detail.node.data.message.id].favorite = true;
										} else {
											history.messages[e.detail.node.data.message.id].favorite = null;
										}

										showMessage(e.detail.node.data.message);
									}}
									on:close={() => {
										showControls.set(false);
									}}
								/>
							{:else}
								<Controls
									on:close={() => {
										showControls.set(false);
									}}
									{models}
									bind:chatFiles
									bind:params
								/>
							{/if}
						</div>
					</div>
				{/if}
			</Pane>
		{/if}
	{/if}
</SvelteFlowProvider>
