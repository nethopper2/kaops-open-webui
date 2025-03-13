<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { marked } from 'marked';

	import { config, user, models as _models, temporaryChatEnabled } from '$lib/stores';
	import { onMount, getContext, tick } from 'svelte';

	import { blur, fade } from 'svelte/transition';

  // NOTE: Keeping the original import for Suggestions.svelte for reference
  //       May allow users to switch between the two components in the future
	// import Suggestions from './Suggestions.svelte';
	import SuggestionButtons from './SuggestionButtons.svelte';
	import { sanitizeResponseContent } from '$lib/utils';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';

	const i18n = getContext('i18n');

	export let modelIds = [];
	export let models = [];
	export let atSelectedModel;

	export let submitPrompt;

	let mounted = false;
	let selectedModelIdx = 0;

	$: if (modelIds.length > 0) {
		selectedModelIdx = models.length - 1;
	}

	$: models = modelIds.map((id) => $_models.find((m) => m.id === id));

  // Listen for input events from SuggestionButtons.svelte
  // Can set it to any text, but initially only used when clearing the input field
  async function setInputPrompt(event) {
    submitPrompt = event.detail.value;
    const chatInputElement = document.getElementById('chat-input');
		await tick();
		if (chatInputElement) {
			chatInputElement.focus();
			chatInputElement.dispatchEvent(new Event('input'));
		}
  }

	onMount(() => {
		mounted = true;
	});
</script>

{#key mounted}
	<div class="m-auto w-full max-w-6xl px-8 lg:px-20">
		<div class="flex justify-start">
			<div class="flex -space-x-4 mb-0.5" in:fade={{ duration: 200 }}>
				{#each models as model, modelIdx}
					<button
						on:click={() => {
							selectedModelIdx = modelIdx;
						}}
					>
						<Tooltip
							content={marked.parse(
								sanitizeResponseContent(models[selectedModelIdx]?.info?.meta?.description ?? '')
							)}
							placement="right"
						>
							<img
								crossorigin="anonymous"
								src={model?.info?.meta?.profile_image_url ??
									($i18n.language === 'dg-DG'
										? `/doge.png`
										: `${WEBUI_BASE_URL}/static/favicon.png`)}
								class=" size-[2.7rem] rounded-full border-[1px] border-gray-200 dark:border-none"
								alt="logo"
								draggable="false"
							/>
						</Tooltip>
					</button>
				{/each}
			</div>
		</div>

		{#if $temporaryChatEnabled}
			<Tooltip
				content="This chat won't appear in history and your messages will not be saved."
				className="w-fit"
				placement="top-start"
			>
				<div class="flex items-center gap-2 text-gray-500 font-medium text-lg my-2 w-fit">
					<EyeSlash strokeWidth="2.5" className="size-5" /> Temporary Chat
				</div>
			</Tooltip>
		{/if}

		<div
			class=" mt-2 mb-4 text-3xl text-gray-800 dark:text-gray-100 font-medium text-left flex items-center gap-4 font-primary"
		>
			<div>
				<div class="text-2xl @sm:text-3xl line-clamp-1" in:fade={{ duration: 100 }}>
          {$i18n.t("Hi, I'm your Private AI", { name: $user.name })}
				</div>

        <div class="text-sm mt-2 line-clamp-1 text-neutral-500">
					{#if models[selectedModelIdx]?.name}
						{models[selectedModelIdx]?.name}
					{:else}
						No model selected
					{/if}
				</div>

				<div in:fade={{ duration: 200, delay: 200 }}>
					{#if models[selectedModelIdx]?.info?.meta?.description ?? null}
						<div
							class="mt-0.5 text-base font-normal text-gray-500 dark:text-gray-400 line-clamp-3 markdown"
						>
							{@html marked.parse(
								sanitizeResponseContent(models[selectedModelIdx]?.info?.meta?.description)
							)}
						</div>
						{#if models[selectedModelIdx]?.info?.meta?.user}
							<div class="mt-0.5 text-sm font-normal text-gray-400 dark:text-gray-500">
								By
								{#if models[selectedModelIdx]?.info?.meta?.user.community}
									<a
										href="https://openwebui.com/m/{models[selectedModelIdx]?.info?.meta?.user
											.username}"
										>{models[selectedModelIdx]?.info?.meta?.user.name
											? models[selectedModelIdx]?.info?.meta?.user.name
											: `@${models[selectedModelIdx]?.info?.meta?.user.username}`}</a
									>
								{:else}
									{models[selectedModelIdx]?.info?.meta?.user.name}
								{/if}
							</div>
						{/if}
					{:else}
						<div class=" font-medium text-gray-400 dark:text-gray-500 line-clamp-1 font-p">
							{$i18n.t('How can I help you today?')}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- <div class=" w-full font-primary" in:fade={{ duration: 200, delay: 300 }}>
			<Suggestions
				className="grid grid-cols-2"
				suggestionPrompts={atSelectedModel?.info?.meta?.suggestion_prompts ??
					models[selectedModelIdx]?.info?.meta?.suggestion_prompts ??
					$config?.default_prompt_suggestions ??
					[]}
				on:select={(e) => {
					submitPrompt(e.detail);
				}}
			/>
		</div> -->

		<div class="mx-0">
			<SuggestionButtons
				className="grid grid-cols-2"
				suggestionPrompts={atSelectedModel?.info?.meta?.suggestion_prompts ??
					models[selectedModelIdx]?.info?.meta?.suggestion_prompts ??
					$config?.default_prompt_suggestions ??
					[]}
				on:select={(e) => {
					submitPrompt(e.detail);
				}}
        on:setInput={setInputPrompt}
			/>
		</div>     
	</div>
{/key}
