<script lang="ts">
import { getContext, onMount, tick } from 'svelte';
import Modal from '$lib/components/common/Modal.svelte';
import Tooltip from '$lib/components/common/Tooltip.svelte';
import { WEBUI_API_BASE_URL } from '$lib/constants';

import { config } from '$lib/stores';
import type { FileItem } from '$lib/components-vue/storage/PopupMetadataEdit.vue';

import XMark from '$lib/components/icons/XMark.svelte';
import Textarea from '$lib/components/common/Textarea.svelte';

 let TModalRef: Modal

// The PopupMetadataEdit component instance.
	let TRefFilePopup: { visible: boolean, fileItem: FileItem, i18n: { t: (s: string) => string }; }
	const i18n = getContext('i18n');

	export let show = false;
	export let citation;
	export let showPercentage = false;
	export let showRelevance = true;

	let mergedDocuments = [];

	function calculatePercentage(distance: number) {
		if (typeof distance !== 'number') return null;
		if (distance < 0) return 0;
		if (distance > 1) return 100;
		return Math.round(distance * 10000) / 100;
	}

	function getRelevanceColor(percentage: number) {
		if (percentage >= 80)
			return 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200';
		if (percentage >= 60)
			return 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200';
		if (percentage >= 40)
			return 'bg-orange-200 dark:bg-orange-800 text-orange-800 dark:text-orange-200';
		return 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200';
	}

	$: if (citation) {
		mergedDocuments = citation.document?.map((c, i) => {
			return {
				source: citation.source,
				document: c,
				metadata: citation.metadata?.[i],
				distance: citation.distances?.[i]
			};
		});
		if (mergedDocuments.every((doc) => doc.distance !== undefined)) {
			mergedDocuments = mergedDocuments.sort(
				(a, b) => (b.distance ?? Infinity) - (a.distance ?? Infinity)
			);
		}
	}

	const decodeString = (str: string) => {
		try {
			return decodeURIComponent(str);
		} catch (e) {
			return str;
		}
	};
</script>

<Modal size="lg" bind:show bind:this={TModalRef}>
	<div>
		<div class=" flex justify-between dark:text-gray-300 px-5 pt-4 pb-2">
			<div class=" text-lg font-medium self-center capitalize">
				{#if citation?.source?.name}
					{@const document = mergedDocuments?.[0]}
					{#if document?.metadata?.file_id || document.source?.url?.includes('http')}
						<Tooltip
							className="w-fit"
							content={document.source?.url?.includes('http')
								? $i18n.t('Open link')
								: $i18n.t('Open file')}
							placement="top-start"
							tippyOptions={{ duration: [500, 0] }}
						>
<!--							<a-->
<!--								class="hover:text-gray-500 dark:hover:text-gray-100 underline grow line-clamp-1"-->
<!--								href={document?.metadata?.file_id-->
<!--									? `${WEBUI_API_BASE_URL}/files/${document?.metadata?.file_id}/content${document?.metadata?.page !== undefined ? `#page=${document.metadata.page + 1}` : ''}`-->
<!--									: document.source?.url?.includes('http')-->
<!--										? document.source.url-->
<!--										: `#`}-->
<!--								target="_blank"-->
<!--							>-->
							<a
								class="hover:text-gray-500 dark:hover:text-gray-100 underline grow line-clamp-1"
								href={document?.metadata?.file_id
											? `${$config?.private_ai.citation_document_url}/${document?.metadata?.file_id}`
											: document.source?.url?.includes('http')
												? document.source.url
												: `#`}
								target="_blank"
							>
								{decodeString(citation?.source?.name)}
							</a>
						</Tooltip>
					{:else}
						{decodeString(citation?.source?.name)}
					{/if}
				{:else}
					{$i18n.t('Citation')}
				{/if}
			</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-6 pb-5 md:space-x-4">
			<!-- NOTE: this div used to have a max height max-h-[22rem] -->
			<div
				class="flex flex-col w-full dark:text-gray-200 overflow-y-scroll max-h-[22rem] scrollbar-thin gap-1"
			>
				{#each mergedDocuments as document, documentIdx}
					<div class="flex flex-col w-full gap-2">
						{#if document?.metadata}
						<div class="text-sm font-medium dark:text-gray-300">
							{$i18n.t('Source')}
						</div>

						{#if document.source?.name}
							<Tooltip
								className="w-fit"
								content={$i18n.t('Open file')}
								placement="top-start"
								tippyOptions={{ duration: [500, 0] }}
							>
								<div class="text-sm dark:text-gray-400 flex items-center gap-2 w-fit">
<!--									<a-->
<!--										class="hover:text-gray-500 dark:hover:text-gray-100 underline grow"-->
<!--										href={document?.metadata?.file_id-->
<!--											? `${WEBUI_API_BASE_URL}/files/${document?.metadata?.file_id}/content${document?.metadata?.page !== undefined ? `#page=${document.metadata.page + 1}` : ''}`-->
<!--											: document.source?.url?.includes('http')-->
<!--												? document.source.url-->
<!--												: `#`}-->
<!--										target="_blank"-->
<!--									>-->
									<a
										class="hover:text-gray-500 dark:hover:text-gray-100 underline grow"
										href={document?.metadata?.file_id
											? `${$config?.private_ai.citation_document_url}/${document?.metadata?.file_id}`
											: document.source?.url?.includes('http')
												? document.source.url
												: `#`}
										target="_blank"
									>
										{decodeString(document?.metadata?.name ?? document.source.name)}
									</a>
									{#if Number.isInteger(document?.metadata?.page)}
										<span class="text-xs text-gray-500 dark:text-gray-400">
											({$i18n.t('page')}
											{document.metadata.page + 1})
										</span>
									{/if}

									<button
										class="flex text-xs items-center space-x-1 px-2 py-1 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition"
										on:click={() => {
											// Stop the focus trap in the Modal so the vue Dialog can be clicked.
											TModalRef.deactivateFocusTrap()

											TRefFilePopup.show({
												path: document?.metadata?.file_id,
												isDirectory: false,
											})
										}}
										aria-label="Edit Metadata"
									>
										<div class="self-center mr-2 font-medium line-clamp-1">
											{$i18n.t('Edit Metadata')}
										</div>
									</button>
								</div>
							</Tooltip>
							{#if document.metadata?.parameters}
								<div>
									<div class="text-sm font-medium dark:text-gray-300 mt-2 mb-0.5">
										{$i18n.t('Parameters')}
									</div>

									<Textarea readonly value={JSON.stringify(document.metadata.parameters, null, 2)}
									></Textarea>
								</div>
							{/if}
						{/if}
					{/if}

						<div>
							<div
								class=" text-sm font-medium dark:text-gray-300 flex items-center gap-2 w-fit mb-1"
							>
								{$i18n.t('Content')}

								{#if showRelevance && document.distance !== undefined}
									<Tooltip
										className="w-fit"
										content={$i18n.t('Relevance')}
										placement="top-start"
										tippyOptions={{ duration: [500, 0] }}
									>
										<div class="text-sm my-1 dark:text-gray-400 flex items-center gap-2 w-fit">
											{#if showPercentage}
												{@const percentage = calculatePercentage(document.distance)}

												{#if typeof percentage === 'number'}
													<span
														class={`px-1 rounded-sm font-medium ${getRelevanceColor(percentage)}`}
													>
														{percentage.toFixed(2)}%
													</span>
												{/if}
											{:else if typeof document?.distance === 'number'}
												<span class="text-gray-500 dark:text-gray-500">
													({(document?.distance ?? 0).toFixed(4)})
												</span>
											{/if}
										</div>
									</Tooltip>
								{/if}

								{#if Number.isInteger(document?.metadata?.page)}
									<span class="text-sm text-gray-500 dark:text-gray-400">
										({$i18n.t('page')}
										{document.metadata.page + 1})
									</span>
								{/if}
							</div>

							{#if document.metadata?.html}
								<iframe
									class="w-full border-0 h-auto rounded-none"
									sandbox="allow-scripts allow-forms allow-same-origin"
									srcdoc={document.document}
									title={$i18n.t('Content')}
								></iframe>
							{:else}
								<pre class="text-sm dark:text-gray-400 whitespace-pre-line">
                {document.document}
              	</pre>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>

	<!-- NOTE: This popup sometimes takes up space even when hidden, if this issue returns, would like to be able to catch the vue event to show/hide this div to remedy the issue. -->
	<!--	<div style:display={isPopupMetadataEditVisible ? 'block' : 'none'}>-->
	<popup-metadata-edit
		bind:this={TRefFilePopup}
		i18n={$i18n}
	/>
<!--	</div>-->
</Modal>
