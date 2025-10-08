<script lang="ts">
  import { getContext } from 'svelte';
  import InitialView from '$lib/components/private-ai/sidekicks/token-replacer/views/InitialView.svelte';
  import EditValuesView from '$lib/components/private-ai/sidekicks/token-replacer/views/EditValuesView.svelte';
  import { isChatStarted, chatId } from '$lib/stores';
  import { currentTokenReplacerSubView, selectedTokenizedDocPath } from './stores';
	import type { PrivateAiSidekickState } from '$lib/apis/private-ai/sidekicks';

  const i18n = getContext('i18n');

	type TokenReplacerState = {
		tokenizedDocPath?: string;
	};

  export let modelId: string | null = null;
  export let initialState: PrivateAiSidekickState<TokenReplacerState> | null = null;
  $: void modelId;

  // Hydrate selection from the initial state per chat, when showing edit values.
  // Use chatId as the key to ensure we re-hydrate on chat switches but only once per chat.
  let hydratedKey = '';
  $: if ($currentTokenReplacerSubView === 'editValues') {
    const c = $chatId || '';
    const statePath = initialState?.tokenizedDocPath ? String(initialState.tokenizedDocPath) : '';
    if (c && hydratedKey !== c && statePath) {
      // Switching to an existing chat with persisted state: force hydrate from state.
      selectedTokenizedDocPath.set(statePath);
      hydratedKey = c;
    }
    // If we leave chats (c === ''), allow future hydration when another chat loads
    if (!c && hydratedKey !== '') {
      hydratedKey = '';
    }
  }

  // A chat is considered "started" whenever there is an active chat id.
  const started = isChatStarted;
</script>

<div class="flex flex-col w-full h-full">
  {#if $currentTokenReplacerSubView === 'editValues'}
    <EditValuesView />
  {:else}
    <InitialView {modelId} />
  {/if}
</div>
