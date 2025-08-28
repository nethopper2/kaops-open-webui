<script lang="ts">
  // Placeholder Token Replacer toolbar UI
  // This is rendered inside the PrivateAiModelToolbar pane via svelte:component
  export let modelId: string | null = null;
</script>

<div class="w-full h-full flex items-center justify-center px-4 py-4">
  <div class="text-center">
    <div class="text-base font-semibold">Token Replacer Toolbar</div>
    <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">
      Placeholder for model-specific controls{#if modelId} for <span class="font-mono">{modelId}</span>{/if}.
    </div>
  </div>
</div>
