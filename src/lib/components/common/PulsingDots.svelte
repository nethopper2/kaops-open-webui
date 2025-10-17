<script lang="ts">
	export let className: string = '';
	export let color: string = 'text-blue-600 dark:text-blue-400';
</script>

<div class="flex items-center space-x-1 {className}">
	<div class="size-1 bg-current rounded-full animate-pulse {color}"></div>
	<div class="size-1 bg-current rounded-full animate-pulse {color}" style="animation-delay: 0.1s"></div>
	<div class="size-1 bg-current rounded-full animate-pulse {color}" style="animation-delay: 0.2s"></div>
</div>
