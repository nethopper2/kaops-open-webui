<script lang="ts">
  import { getContext } from 'svelte';
  import InitialView from '$lib/components/private-ai/sidekicks/token-replacer/views/InitialView.svelte';
  import ActionsView from '$lib/components/private-ai/sidekicks/token-replacer/views/ActionsView.svelte';
  import EditValuesView from '$lib/components/private-ai/sidekicks/token-replacer/views/EditValuesView.svelte';
  import { isChatStarted } from '$lib/stores';
  import { currentTokenReplacerSubView, selectedTokenizedDocPath } from './stores';
	import type { PrivateAiSidekickState } from '$lib/apis/private-ai/sidekicks';

  const i18n = getContext('i18n');

	type TokenReplacerState = {
		selectedTokenizedDocPath?: string;
	};

  export let modelId: string | null = null;
  export let initialState: PrivateAiSidekickState<TokenReplacerState> | null = null;
  $: void modelId;

  // Hydrate selection from the initial state once
  let hydrated = false;
  $: if (!hydrated && initialState?.selectedTokenizedDocPath) {
    selectedTokenizedDocPath.set(String(initialState.selectedTokenizedDocPath));
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
