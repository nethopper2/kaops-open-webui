<script lang="ts">
  import { getContext } from 'svelte';
  import InitialView from '$lib/components/private-ai/sidekicks/token-replacer/views/InitialView.svelte';
  import EditValuesView from '$lib/components/private-ai/sidekicks/token-replacer/views/EditValuesView.svelte';
  import { currentTokenReplacerSubView } from './stores';
  import type { PrivateAiSidekickState } from '$lib/apis/private-ai/sidekicks';

  const i18n = getContext('i18n');

  type TokenReplacerState = {
    tokenizedDocPath?: string;
  };

  export let modelId: string | null = null;
  export let initialState: PrivateAiSidekickState<TokenReplacerState> | null = null;
  $: void modelId;
</script>

<div class="flex flex-col w-full h-full">
  {#if $currentTokenReplacerSubView === 'editValues'}
    <EditValuesView />
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
