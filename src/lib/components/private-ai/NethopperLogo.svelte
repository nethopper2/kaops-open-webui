<script>
import { getContext } from 'svelte';

const i18n = getContext('i18n');
</script>

<div class="flex items-center justify-end text-[9px] pr-8 gap-2">
	<span class="opacity-70">{$i18n.t('Enhanced by')}</span>
	<img src="/static/private-ai/nh-logo-signature.svg" style="height: 18px;" alt="logo"
			 draggable="false" />
</div>
