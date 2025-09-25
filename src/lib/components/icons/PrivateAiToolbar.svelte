<script lang="ts">
  export let className = 'w-5 h-5';
  export let strokeWidth = '1.5';
  // Optional title for accessibility; when not provided, icon is decorative
  export let title: string | null = null;
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={strokeWidth}
  class={className}
  aria-hidden={title ? undefined : 'true'}
  role="img"
>
  {#if title}
    <title>{title}</title>
  {/if}
  <!-- Model cube (represents a model) -->
  <rect x="3.5" y="6" width="9" height="9" rx="1.75" ry="1.75" />
  <path d="M3.5 10.5h9M8 6v9" stroke-linecap="round" />
  <!-- Add-on badge (puzzle piece) in top-right to suggest an extension/add-on -->
  <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 4.75c.414 0 .75.336.75.75v.5h.5a1 1 0 0 1 1 1v1.25a.75.75 0 0 1-1.5 0V8h-1.25a.75.75 0 0 1 0-1.5H16V6c0-.414.336-.75.75-.75z" />
  <!-- Small plus to reinforce addon concept -->
  <path stroke-linecap="round" d="M18.5 12.25v2m-1 1h2" />
</svg>
