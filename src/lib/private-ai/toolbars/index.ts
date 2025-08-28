import type { ComponentType } from 'svelte';
import TokenReplacerToolbar from '$lib/components/private-ai/toolbars/TokenReplacerToolbar.svelte';

// Map of model ids to their toolbar components
export const PRIVATE_AI_TOOLBAR_COMPONENTS: Readonly<Record<string, ComponentType>> = Object.freeze({
  'private-ai-token-replacer': TokenReplacerToolbar
});
