<script lang="ts">
  import { getContext } from 'svelte';
  import InitialView from '$lib/components/private-ai/sidekicks/token-replacer/views/InitialView.svelte';
  import EditValuesView from '$lib/components/private-ai/sidekicks/token-replacer/views/EditValuesView.svelte';
  import { isChatStarted } from '$lib/stores';
  import { currentTokenReplacerSubView, selectedTokenizedDocPath } from './stores';
	import type { PrivateAiSidekickState } from '$lib/apis/private-ai/sidekicks';

  const i18n = getContext('i18n');

	type TokenReplacerState = {
		tokenizedDocPath?: string;
	};

  export let modelId: string | null = null;
  export let initialState: PrivateAiSidekickState<TokenReplacerState> | null = null;
  $: void modelId;

  // Hydrate selection from the initial state once, but only after a chat has started
  let hydrated = false;
  $: if (!hydrated && $started && initialState?.tokenizedDocPath) {
    selectedTokenizedDocPath.set(String(initialState.tokenizedDocPath));
    hydrated = true;
  }

  // A chat is considered "started" whenever there is an active chat id.
  const started = isChatStarted;
</script>

<div class="flex flex-col w-full h-full">
  {#if $started}
    <EditValuesView />
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
