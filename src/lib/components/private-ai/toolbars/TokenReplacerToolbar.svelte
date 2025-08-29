<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import FilterSelect from '$lib/components/chat/MessageInput/FilterSelect.svelte';
  import Eye from '$lib/components/icons/Eye.svelte';
  import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte';
  import FilePreviewDialog from '$lib/components/chat/MessageInput/FilePreviewDialog.svelte';
  import { fetchDocxFiles, fetchCsvFiles } from '$lib/apis/tokenizedFiles';

  // This is rendered inside the PrivateAiModelToolbar pane via svelte:component
  export let modelId: string | null = null; // Provided by toolbar host
  $: void modelId; // mark as used

  type TokenFile = { idx: number; url: string; name?: string; [key: string]: unknown };

  // Local state moved from MessageInput.svelte
  let docxFiles: TokenFile[] = [];
  let csvFiles: TokenFile[] = [];
  let selectedDocx = '';
  let selectedCsv = '';
  let selectedDocxValue = '';
  let selectedCsvValue = '';
  let loadingFiles = false;
  let refreshingFiles = false;
  let filesFetched = false;
  let filesRefreshAllowed = false;
  let filesFetchedTimeout: ReturnType<typeof setTimeout> | null = null;

  function scheduleRefreshAllowTimer() {
    if (filesFetchedTimeout) {
      clearTimeout(filesFetchedTimeout);
    }
    filesFetchedTimeout = setTimeout(() => {
      filesRefreshAllowed = true;
      filesFetchedTimeout = null;
    }, 5 * 60 * 1000);
  }

  async function fetchTokenFiles(refresh = false) {
    if (!refresh && filesFetched) return;
    if (refresh ? refreshingFiles : loadingFiles) return;

    filesRefreshAllowed = false;
    const haveFiles = (docxFiles?.length ?? 0) > 0 || (csvFiles?.length ?? 0) > 0;
    if (refresh || haveFiles) {
      refreshingFiles = true;
    } else {
      loadingFiles = true;
    }

    try {
      const [docxResult, csvResult] = await Promise.all([fetchDocxFiles(), fetchCsvFiles()]);
      docxFiles = (Array.isArray(docxResult) ? docxResult : (docxResult?.files ?? [])).map((file, idx) => ({ ...file, idx }));
      csvFiles = (Array.isArray(csvResult) ? csvResult : (csvResult?.files ?? [])).map((file, idx) => ({ ...file, idx }));
      filesFetched = true;
    } finally {
      if (refreshingFiles) refreshingFiles = false; else loadingFiles = false;
      scheduleRefreshAllowTimer();
    }
  }

  // Error state
  let showFileSelectionError = false;
  $: if (selectedDocx && selectedCsv) {
    showFileSelectionError = false;
  }

  // Preview dialog state
  let showPreviewDialog = false;
  let previewFile: TokenFile | null = null;
  let previewType: 'docx' | 'csv' | null = null;

  function openPreviewDialog(type: 'docx' | 'csv') {
    if (type === 'docx') {
      previewType = 'docx';
      previewFile = docxFiles.find((f) => String(f.idx) === String(selectedDocxValue));
    } else if (type === 'csv') {
      previewType = 'csv';
      previewFile = csvFiles.find((f) => String(f.idx) === String(selectedCsvValue));
    }
    showPreviewDialog = true;
  }
  function closePreviewDialog() {
    showPreviewDialog = false;
    previewFile = null;
    previewType = null;
  }

  async function updatePromptWithFilenames() {
    const docxFile = docxFiles.find((f) => String(f.idx) === String(selectedDocxValue));
    const csvFile = csvFiles.find((f) => String(f.idx) === String(selectedCsvValue));

    let docxUrl = docxFile?.url || '';
    let csvUrl = csvFile?.url || '';

    if (docxUrl.includes('?')) docxUrl = docxUrl.split('?')[0];
    if (csvUrl.includes('?')) csvUrl = csvUrl.split('?')[0];

    await tick();
    const chatInputElement = document.getElementById('chat-input') as HTMLElement | null;
    if (chatInputElement) {
      chatInputElement.dispatchEvent(new Event('input'));
    }
  }

  onMount(async () => {
    await tick();
    fetchTokenFiles();
    return () => {
      if (filesFetchedTimeout) {
        clearTimeout(filesFetchedTimeout);
        filesFetchedTimeout = null;
      }
    };
  });
</script>

{#if showPreviewDialog}
  <FilePreviewDialog
    show={showPreviewDialog}
    file={previewFile}
    previewType={previewType}
    on:close={closePreviewDialog}
  />
{/if}

<div class="w-full h-full px-2 py-2">
  {#if loadingFiles && (docxFiles.length === 0 && csvFiles.length === 0)}
    <div class="text-gray-500 text-sm">Loading available token files...</div>
  {:else}
    <div class="text-xs text-gray-500 mb-2 text-left">
      Selecting Mineral and Values files auto-populates the prompt box for you.
    </div>
    <div class="flex gap-2 items-center flex-wrap">
      {#if (docxFiles ?? []).length > 0}
        <FilterSelect
          bind:value={selectedDocx}
          items={docxFiles}
          placeholder="Select Mineral File"
          onOpen={() => {
            if (filesRefreshAllowed && !refreshingFiles) {
              fetchTokenFiles(true);
            }
          }}
          onSelect={async (value) => {
            selectedDocx = value;
            selectedDocxValue = value;
            await updatePromptWithFilenames();
          }}
        />
        <Tooltip content="Preview Mineral File" placement="top">
          <button
            class="p-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 disabled:opacity-50 hover:bg-gray-100 dark:hover:bg-gray-800"
            disabled={selectedDocx === ""}
            aria-label="Preview Mineral File"
            on:click={() => openPreviewDialog('docx')}
          >
            <Eye className="w-5 h-5" />
          </button>
        </Tooltip>
      {:else}
        <div class="flex items-center gap-2 px-3 py-2 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <span class="text-sm text-gray-600 dark:text-gray-400">No mineral files available</span>
          <Tooltip content="Upload DOCX files to the workspace to use them here." placement="top">
            <QuestionMarkCircle className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </Tooltip>
        </div>
      {/if}

      {#if (csvFiles ?? []).length > 0}
        <FilterSelect
          bind:value={selectedCsv}
          items={csvFiles}
          placeholder="Select Values File"
          onOpen={() => {
            if (filesRefreshAllowed && !refreshingFiles) {
              fetchTokenFiles(true);
            }
          }}
          onSelect={async (value) => {
            selectedCsv = value;
            selectedCsvValue = value;
            await updatePromptWithFilenames();
          }}
        />
        <Tooltip content="Preview Values File" placement="top">
          <button
            class="p-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 disabled:opacity-50 hover:bg-gray-100 dark:hover:bg-gray-800"
            disabled={selectedCsv === ""}
            aria-label="Preview Values File"
            on:click={() => openPreviewDialog('csv')}
          >
            <Eye className="w-5 h-5" />
          </button>
        </Tooltip>
      {:else}
        <div class="flex items-center gap-2 px-3 py-2 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <span class="text-sm text-gray-600 dark:text-gray-400">No values files available</span>
          <Tooltip content="Upload CSV files to the workspace to use them here." placement="top">
            <QuestionMarkCircle className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </Tooltip>
        </div>
      {/if}
    </div>

    {#if showFileSelectionError}
      <div class="text-gray-500 text-xs mt-1">Please select both a DOCX and a CSV file.</div>
    {/if}
  {/if}
</div>
