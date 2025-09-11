<script lang="ts">
  import Select from 'svelte-select';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import Eye from '$lib/components/icons/Eye.svelte';
  import { onMount, tick } from 'svelte';
  import { appHooks } from '$lib/utils/hooks';
  import { isChatStarted, chatId } from '$lib/stores';
  import { ensureFilesFetched, tokenizedFiles, selectedTokenizedDocPath, selectedTokenizedDoc, filesLoading, currentTokenReplacerSubView } from '../stores';
  import { savePrivateAiSidekickState } from '$lib/private-ai/state';
  import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';

  export let modelId: string | null = null;
  $: void modelId;

  function openPreviewDialog() {
    const file = $selectedTokenizedDoc;
    if (file) {
      appHooks.callHook('chat.overlay', {
        action: 'open',
        title: 'Preview',
        component: TokenizedDocPreview,
        props: { file, previewType: 'docx' }
      });
    }
  }

  onMount(() => {
    ensureFilesFetched();
  });
</script>


<div class="flex flex-col w-full px-2 py-2">
  <div class="text-xs text-gray-500 mb-2 text-left">
    <strong>Let's get started!</strong> To replace tokens in your document, select a tokenized document from the list below.
  </div>
  <div class="flex flex-col w-full h-full gap-2 items-center">
    <div class="flex items-center gap-2 w-full min-w-0">
      <Select
        items={$tokenizedFiles}
        value={$selectedTokenizedDoc}
        placeholder="Select a Document"
        label="name"
        itemId="fullPath"
        clearable={true}
        class="w-full max-w-full"
        containerStyles="max-width: 100%; min-width: 0;"
        inputStyles="text-overflow: ellipsis; white-space: nowrap; overflow: hidden;"
        showChevron
        loading={$filesLoading}
        on:select={(e) => {
          const v = e.detail;

          selectedTokenizedDocPath.set(String(v?.fullPath ?? ''));
        }}
        on:clear={() => {
          selectedTokenizedDocPath.set('');
        }}
      />
      <Tooltip content="Preview Document" placement="top">
        <button
          class="p-1 rounded border bg-white dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed {$selectedTokenizedDocPath === '' ? 'border-gray-200 dark:border-gray-800 cursor-not-allowed' : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900'}"
          disabled={$selectedTokenizedDocPath === ""}
          aria-label="Preview Document"
          on:click={() => openPreviewDialog()}
        >
          <Eye className="w-5 h-5" />
        </button>
      </Tooltip>
    </div>

    {#if $selectedTokenizedDocPath !== ""}
      <div class="flex w-full flex-col items-center justify-center mt-6 gap-2">
        <div class="text-sm text-gray-600 dark:text-gray-300 text-center px-2">
          Ready to start replacing tokens in your selected document.
        </div>
        <button
          class="px-6 py-3 rounded-md text-base font-medium bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600"
          disabled={$selectedTokenizedDocPath === ""}
          aria-label={$isChatStarted ? "Continue Token Replacement" : "Begin Token Replacement"}
          on:click={() => {
            const file = $selectedTokenizedDoc;
            const fullPath = $selectedTokenizedDocPath;
            // Build directive envelope as a JSON string
            const directive = {
              _kind: 'openwebui.directive',
              version: 1,
              name: 'token_replacer.begin',
              assistant_only: true,
              payload: {
                file_path: String(fullPath || '')
              }
            };
            const prompt = JSON.stringify(directive);
            appHooks.callHook('chat.submit', { prompt });
            // Switch to the actions sub-view after the beginning
            currentTokenReplacerSubView.set('actions');
            // Persist sidekick UI state (selected document) for this chat+sidekick
            ;(async () => {
              try {
                const tId = modelId;
                if (!tId) return;
                const cNow = $chatId;
                const doSave = async (cid) => {
                  await savePrivateAiSidekickState(cid, tId, { selectedTokenizedDocPath: $selectedTokenizedDocPath });
                };
                if (cNow) {
                  await doSave(cNow);
                } else {
                  // Chat id not yet assigned (new chat). Save once chatId becomes available.
                  const unsub = chatId.subscribe(async (cid) => {
                    if (cid) {
                      try { await doSave(cid); } finally { unsub(); }
                    }
                  });
                }
              } catch {
                // ignore persistence errors
              }
            })();
          }}
        >
          {$isChatStarted ? 'Continue' : 'Begin'}
        </button>
      </div>
    {/if}
  </div>
</div>
