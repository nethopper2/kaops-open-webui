<script lang="ts">
	import { SvelteFlowProvider } from '@xyflow/svelte';
	import { slide } from 'svelte/transition';
	import { Pane, PaneResizer } from 'paneforge';

	import { onDestroy, onMount, tick } from 'svelte';
import {
	mobile,
	showControls,
	showCallOverlay,
	showOverview,
	showArtifacts,
	showEmbeds,
	activeRightPane
} from '$lib/stores';
 import { calcMinSize, createPaneBehavior, isPaneHandle, type PaneHandle, rightPaneSize } from '$lib/utils/pane';

	import Controls from './Controls/Controls.svelte';
	import CallOverlay from './MessageInput/CallOverlay.svelte';
	import Drawer from '../common/Drawer.svelte';
	import Artifacts from './Artifacts.svelte';
	import Embeds from './ChatControls/Embeds.svelte';

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
	let paneHandle: PaneHandle | null = null;
	$: paneHandle = isPaneHandle(pane) ? (pane as PaneHandle) : null;

	const behavior = createPaneBehavior({
		storageKey: 'chatControlsSize',
		showStore: showControls,
		isActiveInPaneGroup: () => activeInPaneGroup,
		getMinSize: () => minSize
	});

	export const openPane = async () => {
		await behavior.openPane(paneHandle, largeScreen);
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
		const MIN_SIZE = 350;

 	// initialize the minSize based on the container width
		minSize = calcMinSize(container, MIN_SIZE);

		// Create a new ResizeObserver instance
		const resizeObserver = new ResizeObserver((entries) => {
			for (let entry of entries) {
				minSize = calcMinSize(entry.target as HTMLElement, MIN_SIZE);

				if ($showControls && paneHandle && paneHandle.isExpanded() && paneHandle.getSize() < minSize) {
					behavior.clamp(paneHandle, minSize);
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
		showEmbeds.set(false);

		if ($showCallOverlay) {
			showCallOverlay.set(false);
		}
	};

	$: if (!chatId) {
		closeHandler();
	}
</script>

{#if !largeScreen}
	{#if $showControls}
		<Drawer
			show={$showControls}
			onClose={() => {
				showControls.set(false);
			}}
		>
			<div
				class=" {$showCallOverlay || $showOverview || $showArtifacts || $showEmbeds
					? ' h-screen  w-full'
					: 'px-4 py-3'} h-full"
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
				{:else if $showEmbeds}
					<Embeds />
				{:else if $showArtifacts}
					<Artifacts {history} />
				{:else if $showOverview}
					{#await import('./Overview.svelte') then { default: Overview }}
						<Overview
							{history}
							onNodeClick={(e) => {
								const node = e.node;
								showMessage(node.data.message, true);
							}}
							onClose={() => {
								showControls.set(false);
							}}
						/>
					{/await}
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
			 defaultSize={$rightPaneSize || minSize}
			 onResize={(size) => {
					// Mark that the pane has expanded at least once when size > 0
					hasExpanded = hasExpanded || size > 0;

     			if ($showControls && paneHandle && paneHandle.isExpanded()) {
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
						showControls.set(false);
					}
				}}
				collapsible={true}
				class=" z-10 "
			>
				{#if $showControls}
					<div class="flex max-h-full min-h-full">
						<div
							class="w-full {($showOverview || $showArtifacts || $showEmbeds) && !$showCallOverlay
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
							{:else if $showEmbeds}
								<Embeds overlay={dragged} />
							{:else if $showArtifacts}
								<Artifacts {history} overlay={dragged} />
							{:else if $showOverview}
								{#await import('./Overview.svelte') then { default: Overview }}
									<Overview
										{history}
										onNodeClick={(e) => {
											const node = e.node;
											if (node?.data?.message?.favorite) {
												history.messages[node.data.message.id].favorite = true;
											} else {
												history.messages[node.data.message.id].favorite = null;
											}

											showMessage(node.data.message, true);
										}}
										onClose={() => {
											showControls.set(false);
										}}
								 	/>
							{/await}
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
