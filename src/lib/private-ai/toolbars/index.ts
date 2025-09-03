import type { ComponentType } from 'svelte';

// Single source of truth: map toolbar id -> async component loader
const PRIVATE_AI_TOOLBAR_LOADERS = {
  'private-ai-token-replacer': async () =>
    (await import('$lib/components/private-ai/toolbars/token-replacer/index.svelte')).default as ComponentType
} as const;

export type PrivateAiToolbarId = keyof typeof PRIVATE_AI_TOOLBAR_LOADERS;
export const PRIVATE_AI_TOOLBAR_IDS = Object.freeze(
  Object.keys(PRIVATE_AI_TOOLBAR_LOADERS) as PrivateAiToolbarId[]
);

export function canSupportToolbar(id: string | null | undefined): boolean {
  return !!id && id in PRIVATE_AI_TOOLBAR_LOADERS;
}

// Dynamic loader to avoid circular imports with $lib/stores
export async function loadPrivateAiToolbarComponent(id: string | null | undefined): Promise<ComponentType | null> {
  if (!id) return null;
  const loader = PRIVATE_AI_TOOLBAR_LOADERS[id as PrivateAiToolbarId] as
    | (() => Promise<ComponentType>)
    | undefined;
  return loader ? await loader() : null;
}
