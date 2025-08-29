<script lang="ts">
import { onMount, tick } from 'svelte';
import Tooltip from '$lib/components/common/Tooltip.svelte';
import Select from 'svelte-select';
import Eye from '$lib/components/icons/Eye.svelte';
import FilePreviewDialog from '$lib/components/chat/MessageInput/FilePreviewDialog.svelte';
import { fetchDocxFiles } from '$lib/apis/tokenizedFiles';

export let modelId: string | null = null;
$: void modelId; // mark as used

type TokenFile = { id: number | string; url: string; name?: string; [key: string]: unknown };

let tokenizedFiles: TokenFile[] = [];
let selectedTokenizedDocId = '';

// Derived selected option object for svelte-select
$: selectedTokenizedDoc = (tokenizedFiles ?? []).find((f) => String(f.id) === String(selectedTokenizedDocId)) ?? null;

let loadingFiles = false;
let filesFetched = false;

async function fetchTokenFiles() {
	if (filesFetched) return;
	if (loadingFiles) return;

	loadingFiles = true;
	try {
		const docxResult = await fetchDocxFiles();
		tokenizedFiles = (Array.isArray(docxResult) ? docxResult : (docxResult?.files ?? [])).map((file, id) => ({
			...file,
			id
		}));
		filesFetched = true;
	} finally {
		loadingFiles = false;
	}
}

// Preview dialog state
let showPreviewDialog = false;
let previewFile: TokenFile | null | undefined = null;

function openPreviewDialog() {
	previewFile = tokenizedFiles.find((f) => String(f.id) === String(selectedTokenizedDocId));
	showPreviewDialog = true;
}

function closePreviewDialog() {
	showPreviewDialog = false;
	previewFile = null;
}

async function updatePromptWithFilenames() {
	const docxFile = tokenizedFiles.find((f) => String(f.id) === String(selectedTokenizedDocId));
	let docxUrl = docxFile?.url || '';
	if (docxUrl.includes('?')) docxUrl = docxUrl.split('?')[0];
	await tick();
	const chatInputElement = document.getElementById('chat-input') as HTMLElement | null;
	if (chatInputElement) {
		chatInputElement.dispatchEvent(new Event('input'));
	}
}

onMount(() => {
	// In the future we may lazy-load and refresh on demand, but for now we load once on mount.
	fetchTokenFiles();
});
</script>

{#if showPreviewDialog}
	<FilePreviewDialog
		show={showPreviewDialog}
		file={previewFile}
		previewType="docx"
		on:close={closePreviewDialog}
	/>
{/if}

<div class="px-2 py-2">
	<div class="text-xs text-gray-500 mb-2 text-left">
		Let's get started. To replace tokens in your document, select a document from the list below.
	</div>
	<div class="flex gap-2 items-center">
		<div class="flex items-center gap-2 w-full min-w-0">
			<!-- https://svelte-select-examples.vercel.app -->
			<Select
				items={tokenizedFiles}
				value={selectedTokenizedDoc}
				placeholder="Select a Document"
				label="name"
				itemId="id"
				clearable={true}
				class="w-full max-w-full"
				containerStyles="max-width: 100%; min-width: 0;"
				inputStyles="text-overflow: ellipsis; white-space: nowrap; overflow: hidden;"
				showChevron
				loading={loadingFiles}
				on:select={async (e) => {
            const v = e.detail;
            selectedTokenizedDocId = String(v?.value ?? v?.id ?? '');
            await updatePromptWithFilenames();
          }}
				on:clear={async () => {
            selectedTokenizedDocId = '';
            await updatePromptWithFilenames();
          }}
			/>
			<Tooltip content="Preview Mineral File" placement="top">
				<button
					class="p-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 disabled:opacity-50 hover:bg-gray-100 dark:hover:bg-gray-800"
					disabled={selectedTokenizedDocId === ""}
					aria-label="Preview Mineral File"
					on:click={() => openPreviewDialog()}
				>
					<Eye className="w-5 h-5" />
				</button>
			</Tooltip>
		</div>
	</div>
</div>
