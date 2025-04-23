<script>
import { onMount } from 'svelte';
import KnowledgePrivateAI from '$lib/components/workspace/KnowledgePrivateAI.svelte';
import { config, knowledge } from '$lib/stores';
import { getKnowledgeBases } from '$lib/apis/knowledge';
import Knowledge from '$lib/components/workspace/Knowledge.svelte';

onMount(async () => {
	if (config?.features?.enable_upstream_ui) {
		await Promise.all([
			(async () => {
				knowledge.set(await getKnowledgeBases(localStorage.token));
			})()
		]);
	}
	});
</script>

{#if $config?.features?.enable_upstream_ui}
	{#if $knowledge !== null}
	<Knowledge />
	{/if}
{:else}
	<KnowledgePrivateAI />
{/if}
