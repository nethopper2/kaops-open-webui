<script lang="ts">
  import InitialView from '$lib/components/private-ai/toolbars/token-replacer/views/InitialView.svelte';
  import ActionsView from '$lib/components/private-ai/toolbars/token-replacer/views/ActionsView.svelte';
  import EditValuesView from '$lib/components/private-ai/toolbars/token-replacer/views/EditValuesView.svelte';
  import { isChatStarted } from '$lib/stores';
  import { currentTokenReplacerSubView, selectedTokenizedDocId } from './stores';
  import type { PrivateAiToolbarState } from '$lib/private-ai/state';

  export let modelId: string | null = null;
  export let initialState: PrivateAiToolbarState | null = null;
  $: void modelId;

  // Hydrate selection from the initial state once
  let hydrated = false;
  $: if (!hydrated && initialState?.selectedTokenizedDocId) {
    selectedTokenizedDocId.set(String(initialState.selectedTokenizedDocId));
    hydrated = true;
  }

  // A chat is considered "started" whenever there is an active chat id.
  const started = isChatStarted;
</script>

<div class="flex flex-col w-full h-full">
  {#if $started}
    {#if $currentTokenReplacerSubView === 'actions'}
      <ActionsView />
    {:else if $currentTokenReplacerSubView === 'editValues'}
      <EditValuesView />
    {:else}
      <InitialView {modelId} />
    {/if}
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
