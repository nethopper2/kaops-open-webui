<script>
import KnowledgePrivateAI from '$lib/components/workspace/KnowledgePrivateAI.svelte';
import { config } from '$lib/stores';
import Knowledge from '$lib/components/workspace/Knowledge.svelte';
</script>

{#if $config?.private_ai?.enable_upstream_ui}
	<Knowledge />
{:else}
	<KnowledgePrivateAI />
{/if}
