import type { ComponentType } from 'svelte';

// Single source of truth: map sidekick id -> async component loader
const PRIVATE_AI_SIDEKICK_LOADERS = {
  'private-ai-token-replacer': async () =>
    (await import('$lib/components/private-ai/sidekicks/token-replacer/index.svelte')).default as ComponentType
} as const;

export type PrivateAiSidekickId = keyof typeof PRIVATE_AI_SIDEKICK_LOADERS;
export const PRIVATE_AI_SIDEKICK_IDS = Object.freeze(
  Object.keys(PRIVATE_AI_SIDEKICK_LOADERS) as PrivateAiSidekickId[]
);

export function canSupportSidekick(id: string | null | undefined): boolean {
  return !!id && id in PRIVATE_AI_SIDEKICK_LOADERS;
}

// Dynamic loader to avoid circular imports with $lib/stores
export async function loadPrivateAiSidekickComponent(id: string | null | undefined): Promise<ComponentType | null> {
  if (!id) return null;
  const loader = PRIVATE_AI_SIDEKICK_LOADERS[id as PrivateAiSidekickId] as
    | (() => Promise<ComponentType>)
    | undefined;
  return loader ? await loader() : null;
}
