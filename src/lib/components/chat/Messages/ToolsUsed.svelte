<script lang="ts">
import { getContext } from 'svelte';
import Collapsible from '$lib/components/common/Collapsible.svelte';
import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
// import Sparkles from '$lib/components/icons/Sparkles.svelte';

const i18n = getContext('i18n');

interface ToolCall {
	tool_name: string;
}

export let tool_calls: ToolCall[] = [];
export let id = '';

let isCollapsibleOpen = false;

const MAX_VISIBLE_TOOLS = 2;
</script>

{#if tool_calls && tool_calls.length > 0}
	<div class="py-0.5 -mx-0.5 w-full flex gap-1 items-center flex-wrap mb-2.5 text-xs">
		{#if tool_calls.length <= MAX_VISIBLE_TOOLS}
			<div class="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
<!--				<div class="self-center">-->
<!--					<Sparkles className="size-4" />-->
<!--				</div>-->
				<div class="flex items-center gap-1.5 flex-wrap">
					<span>{$i18n.t('Using tools:')}</span>
					{#each tool_calls as tool_call}
						<div
							class="font-medium bg-gray-100 dark:bg-gray-800/70 text-gray-800 dark:text-gray-300 px-2 py-0.5 rounded-lg"
						>
							{tool_call.tool_name}
						</div>
					{/each}
				</div>
			</div>
		{:else}
			<Collapsible
				id={`collapsible-tools-${id}`}
				bind:open={isCollapsibleOpen}
				className="w-full max-w-full"
				buttonClassName="w-fit max-w-full"
			>
				<div
					class="flex w-full overflow-auto items-center gap-2 text-gray-500 hover:text-gray-600 dark:hover:text-gray-400 transition cursor-pointer"
				>
<!--					<div class="self-center">-->
<!--						<Sparkles className="size-4" />-->
<!--					</div>-->
					<div class="flex-1 flex items-center gap-1 overflow-auto scrollbar-none w-full max-w-full">
						<span class="whitespace-nowrap hidden sm:inline shrink-0">{$i18n.t('Using tools')}</span>
						<div class="flex items-center overflow-auto scrollbar-none w-full max-w-full flex-1">
							<div class="flex text-xs font-medium items-center gap-1.5 ml-1">
								{#each tool_calls.slice(0, MAX_VISIBLE_TOOLS) as tool_call}
									<div
										class="font-medium bg-gray-100 dark:bg-gray-800/70 text-gray-800 dark:text-gray-300 px-2 py-0.5 rounded-lg whitespace-nowrap"
									>
										{tool_call.tool_name}
									</div>
								{/each}
							</div>
						</div>
						<div class="flex items-center gap-1 whitespace-nowrap shrink-0">
							<span class="hidden sm:inline">{$i18n.t('and')}</span>
							{tool_calls.length - MAX_VISIBLE_TOOLS}
							<span>{$i18n.t('more')}</span>
						</div>
					</div>
					<div class="shrink-0">
						{#if isCollapsibleOpen}
							<ChevronUp strokeWidth="3.5" className="size-3.5" />
						{:else}
							<ChevronDown strokeWidth="3.5" className="size-3.5" />
						{/if}
					</div>
				</div>
				<div slot="content">
					<div class="flex text-xs font-medium flex-wrap gap-1.5 mt-2 ml-5">
						{#each tool_calls.slice(MAX_VISIBLE_TOOLS) as tool_call}
							<div
								class="font-medium bg-gray-100 dark:bg-gray-800/70 text-gray-800 dark:text-gray-200 px-2 py-0.5 rounded-lg"
							>
								{tool_call.tool_name}
							</div>
						{/each}
					</div>
				</div>
			</Collapsible>
		{/if}
	</div>
{/if}
