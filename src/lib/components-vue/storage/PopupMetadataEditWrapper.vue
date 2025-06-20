<script setup lang="ts">
/**
 * This is a wrapper for PopupMetadataEdit since it is used both as a vue child and a svelte child.
 */

import FileSystemItem from 'devextreme/file_management/file_system_item';
import PopupMetadataEdit from '$lib/components-vue/storage/PopupMetadataEdit.vue';
import { ref, useHost } from 'vue';

const props = defineProps(['i18n']);
const svelteHost = useHost();

const currentFileItem = ref<FileSystemItem>();
const visible  = ref(false);

if (svelteHost) {
	svelteHost.show = (fileItem: FileSystemItem) => {
		currentFileItem.value = fileItem
		visible.value = true;
	};

	svelteHost.hide = () => {
		visible.value = false;
	};
}
</script>

<template>
	<div>
		<popup-metadata-edit
			v-model:visible="visible"
			:file-item="currentFileItem as FileSystemItem"
			:i18n="i18n"
		/>
	</div>
</template>
