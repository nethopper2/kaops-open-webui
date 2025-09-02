<script lang="ts">
  import { onDestroy } from 'svelte';
  import { derived } from 'svelte/store';
  import InitialView from '$lib/components/private-ai/toolbars/token-replacer/views/InitialView.svelte';
  import ActionsView from '$lib/components/private-ai/toolbars/token-replacer/views/ActionsView.svelte';
  import { chatId as chatIdStore } from '$lib/stores';
  import { currentTokenReplacerSubView } from './stores';

  export let modelId: string | null = null;
  $: void modelId;

  // A chat is considered "started" whenever there is an active chat id.
  const started = derived(chatIdStore, ($chatId) => Boolean($chatId));

  // Ensure that when switching to any existing chat, we default to the Actions sub-view.
  // When there is no active chat (new chat), default to the Initial sub-view.
  const unsubChat = chatIdStore.subscribe((id) => {
    if (id && id !== '') {
      currentTokenReplacerSubView.set('actions');
    } else {
      currentTokenReplacerSubView.set('initial');
    }
  });

  onDestroy(() => {
    unsubChat?.();
  });
</script>

<div class="flex flex-col w-full h-full">
  {#if $started}
    {#if $currentTokenReplacerSubView === 'actions'}
      <ActionsView />
    {:else}
      <InitialView {modelId} />
    {/if}
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
