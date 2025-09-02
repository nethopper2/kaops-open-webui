<script lang="ts">
  import Select from 'svelte-select';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import Eye from '$lib/components/icons/Eye.svelte';
  import FilePreviewDialog from '$lib/components/chat/MessageInput/FilePreviewDialog.svelte';
  import { fetchDocxFiles } from '$lib/apis/tokenizedFiles';
  import { onMount, tick } from 'svelte';
  import { appHooks } from '$lib/utils/hooks';

  export let modelId: string | null = null;
  $: void modelId;

  type TokenFile = { id: number | string; url: string; name?: string; [key: string]: unknown };

  let tokenizedFiles: TokenFile[] = [];
  let selectedTokenizedDocId = '';

  $: selectedTokenizedDoc = (tokenizedFiles ?? []).find((f) => String(f.id) === String(selectedTokenizedDocId)) ?? null;

  let loadingFiles = false;
  let filesFetched = false;

  async function fetchTokenFiles() {
    if (filesFetched || loadingFiles) return;
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

<div class="flex flex-col w-full px-2 py-2">
  <div class="text-xs text-gray-500 mb-2 text-left">
    <strong>Let's get started!</strong> To replace tokens in your document, select a tokenized document from the list below.
  </div>
  <div class="flex flex-col w-full h-full gap-2 items-center">
    <div class="flex items-center gap-2 w-full min-w-0">
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

    {#if selectedTokenizedDocId !== ""}
      <div class="flex w-full flex-col items-center justify-center mt-6 gap-2">
        <div class="text-sm text-gray-600 dark:text-gray-300 text-center px-2">
          Ready to start replacing tokens in your selected document.
        </div>
        <button
          class="px-6 py-3 rounded-md text-base font-medium bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600"
          disabled={selectedTokenizedDocId === ""}
          aria-label="Begin Token Replacement"
          on:click={() => {
            const file = tokenizedFiles.find((f) => String(f.id) === String(selectedTokenizedDocId));
            const name = file?.name ?? 'selected document';
            let url = file?.url || '';
            if (url.includes('?')) url = url.split('?')[0];
            const prompt = `Begin the token replacement assistant session. The user has selected a tokenized document named "${name}". Please briefly explain how we will proceed to replace tokens in this document, what information you will need, and how the user can confirm or adjust replacements. Document URL: ${url}`;
            appHooks.callHook('chat.submit', { prompt });
          }}
        >
          Begin
        </button>
      </div>
    {/if}
  </div>
</div>
