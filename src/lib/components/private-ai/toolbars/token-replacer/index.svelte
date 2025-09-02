<script lang="ts">
  import { derived } from 'svelte/store';
  import InitialView from '$lib/components/private-ai/toolbars/token-replacer/views/InitialView.svelte';
  import ActionsView from '$lib/components/private-ai/toolbars/token-replacer/views/ActionsView.svelte';
  import { chatId as chatIdStore } from '$lib/stores';

  export let modelId: string | null = null;
  $: void modelId;

  // Simplified: a chat is considered "started" whenever there is an active chat id.
  const started = derived(chatIdStore, ($chatId) => Boolean($chatId));
</script>

<div class="flex flex-col w-full h-full">
  {#if $started}
    <ActionsView />
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
