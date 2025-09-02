<script lang="ts">
  import InitialView from '$lib/components/private-ai/toolbars/token-replacer/views/InitialView.svelte';
  import ActionsView from '$lib/components/private-ai/toolbars/token-replacer/views/ActionsView.svelte';
  import EditValuesView from '$lib/components/private-ai/toolbars/token-replacer/views/EditValuesView.svelte';
  import { isChatStarted } from '$lib/stores';
  import { currentTokenReplacerSubView } from './stores';

  export let modelId: string | null = null;
  $: void modelId;

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
