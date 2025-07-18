<script setup lang="ts">
import { confirm } from 'devextreme/ui/dialog';
import { DxForm, DxItem as DxFormItem } from 'devextreme-vue/form';
import { DxPopup, DxToolbarItem } from 'devextreme-vue/popup';
import 'devextreme-vue/tag-box';
import 'devextreme-vue/text-area';
import { computed, onBeforeMount, ref, type useHost, watch } from 'vue';
import { toast } from 'svelte-sonner';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { apiFetch } from '$lib/apis/private-ai/fetchClients';
import { DxLoadPanel } from 'devextreme-vue/load-panel';
import { useTheme } from '../composables/useTheme';

// Use a partial of FileSystemItem
export type FileItem = Pick<FileSystemItem, 'isDirectory' | 'path'>;

const props = defineProps<{
	fileItem?: FileItem;
	i18n: { t: (s: string) => string };
	svelteHost?: ReturnType<typeof useHost>
}>();

const emit = defineEmits(['update:visible', 'saved', 'cancelled']);
const localVisible = defineModel<boolean>('visible', { default: false });

const loadingVisible = ref(false);
const tagChoices = ref([] as Array<string>);
const metadataExists = ref(false);
const metadataToEdit = ref(getEmptyMetadata());

const fileOrDirectoryName = computed(() => {
	return (props.fileItem?.path ?? '').split('/').pop() ?? '';
});

async function saveMetadata() {
	try {
		if (props.fileItem) {
			const response = await apiFetch(`/storage/metadata`, {
				method: 'PUT',
				body: {
					filePath: props.fileItem.path,
					tags: metadataToEdit.value.tags,
					contextData: metadataToEdit.value.contextData
				}
			});

			if (response.success) {
				toast.success(props.i18n.t(`Metadata saved`));
				localVisible.value = false;
				emit('saved');
			} else {
				throw new Error(response.message);
			}
		} else {
			console.warn('No current file item');
		}
	} catch (err) {
		console.error('Error saving metadata:', err);
		toast.error(props.i18n.t(`Failed to save metadata`));
	}
}

async function deleteMetadata() {
	try {
		if (props.fileItem) {
			const response = await apiFetch(`/storage/metadata`, {
				method: 'DELETE',
				query: {
					filePath: props.fileItem.path
				}
			});

			if (response.success) {
				toast.success(props.i18n.t(`Metadata deleted`));
				localVisible.value = false;
			} else {
				throw new Error(response.message);
			}
		} else {
			console.warn('No current file item');
		}
	} catch (err) {
		console.error('Error deleting metadata:', err);
		toast.error(props.i18n.t(`Failed to delete metadata`));
	}
}

async function showConfirmDeleteDialog() {
	try {
		let result = await confirm(
			props.i18n.t('Are you sure you want to delete this metadata?'),
			props.i18n.t('Confirm Deletion')
		);
		if (result) {
			void deleteMetadata();
		}
	} catch (err) {
		console.error(err);
	}
}

function getEmptyMetadata() {
	return {
		contextData: '',
		tags: [] as Array<string>
	};
}

async function loadMetadata() {
	if (props.fileItem) {
		try {
			metadataExists.value = false;
			const { metadata } = await apiFetch('/storage/metadata', {
				query: {
					filePath: props.fileItem.path
				}
			});

			if (metadata) {
				metadataToEdit.value = structuredClone(metadata);
				metadataExists.value = true;
			} else {
				console.warn('No metadata found for file: ', props.fileItem.path);
				metadataToEdit.value = getEmptyMetadata();
				metadataExists.value = false;
			}
		} catch (err) {
			console.error(err);
			metadataToEdit.value = getEmptyMetadata();
			metadataExists.value = false;
		}
	}
}

async function loadTagOptions() {
	try {
		const { tags } = await apiFetch('/storage/tags');

		if (Array.isArray(tags)) {
			tagChoices.value = tags;
		} else {
			console.warn('No tags found');
			tagChoices.value = [];
		}
	} catch (err) {
		console.error(err);
		tagChoices.value = [];
	}
}

async function handleDialogShowing() {
	try {
		loadingVisible.value = true;
		await Promise.all([loadTagOptions(), loadMetadata()]);
	} catch (err) {
		console.error(err);
	} finally {
		loadingVisible.value = false;
	}
}

function handleDialogShown() {
	// Could be used for additional initialization if needed
}

function handleDialogHidden() {
	metadataToEdit.value = getEmptyMetadata();
	emit('cancelled');
}

// Watch for changes in fileItem and load metadata when it changes
watch(
	() => props.fileItem,
	async (newValue) => {
		if (newValue) {
			await loadMetadata();
		}
	}
);

// Use the theme composable
const { loadTheme, loadDarkTheme, loadLightTheme, unloadCurrentTheme, setupTheme } = useTheme({ svelteHost: props.svelteHost });

onBeforeMount(() => {
	setupTheme();
});
</script>

<template>
	<dx-popup
		v-model:visible="localVisible"
		:show-close-button="false"
		:max-height="700"
		:max-width="700"
		title="Edit Metadata"
		@showing="handleDialogShowing"
		@shown="handleDialogShown"
		@hidden="handleDialogHidden"
	>
		<dx-load-panel v-model:visible="loadingVisible" />

		<div class="text-xs p-4 mb-4 border border-black/20 dark:border-white/20 rounded">
			<div class="grid grid-cols-none gap-1">
				<div>Path</div>
				<div class="w-full opacity-70">
					{{ fileItem?.path }}
				</div>

				<div>{{ fileItem?.isDirectory ? 'Directory' : 'File' }}</div>
				<div class="grow opacity-70">
					{{ fileOrDirectoryName }}
				</div>
			</div>
		</div>

		<form>
			<dx-form v-model:form-data="metadataToEdit">
				<dx-form-item
					data-field="tags"
					editor-type="dxTagBox"
					:editor-options="{
						dataSource: tagChoices,
						showSelectionControls: true,
						acceptCustomValue: true
						// REMINDER: Search allows filtering, but the input is in the same place as when adding a custom value.
						//           This has potential to be confusing, so this is commented out for now.
						// searchEnabled: true
					}"
					help-text="Enter or choose tags"
				/>
				<dx-form-item
					data-field="contextData"
					editor-type="dxTextArea"
					:help-text="
						fileItem?.isDirectory
							? `To help our AI system generate accurate responses, please briefly describe this directory's purpose, list and explain its contents, outline any naming conventions, and provide instructions for use. Optionally, add example questions you might ask the AI about the files—this helps the AI understand your needs and improves its answers. Update this information whenever the directory changes.`
							: `To help our AI system generate accurate responses, please provide a brief description of this file's purpose, explain its contents, and include instructions for use if applicable. Optionally, add example questions you might ask the AI about this file—this helps the AI understand your needs and improves its answers. If relevant, mention any important details such as the file's format, structure, or dependencies. Be sure to update this information whenever the file changes.`
					"
					:editor-options="{
						height: 200,
						maxLength: 200
					}"
				/>
			</dx-form>
		</form>

		<dx-toolbar-item
			widget="dxButton"
			toolbar="bottom"
			location="before"
			:visible="metadataExists"
			:options="{
				text: 'Delete',
				type: 'danger',
				stylingMode: 'outlined',
				onClick: showConfirmDeleteDialog
			}"
		/>

		<dx-toolbar-item
			widget="dxButton"
			toolbar="bottom"
			location="after"
			:options="{
				text: 'Cancel',
				type: 'default',
				stylingMode: 'outlined',
				onClick: () => {
					localVisible = false;
				}
			}"
		/>

		<dx-toolbar-item
			widget="dxButton"
			toolbar="bottom"
			location="after"
			:options="{
				text: 'Save',
				type: 'default',
				stylingMode: 'contained',
				onClick: saveMetadata
			}"
		/>
	</dx-popup>
</template>

<style>
/**
 * The fonts were copied from the node_module to the static directory in
 * /themes/vendor/icons/
 * The dark & light stylesheets were also copied. This is needed since the shadowRoot
 * was unable to use the font-face from the injected stylesheet.
 */
@font-face {
	font-family: DXIcons;
	src:
		local('DevExtreme Generic Icons'),
		local('devextreme_generic_icons'),
		url('/themes/vendor/icons/dxicons.woff2') format('woff2'),
		url('/themes/vendor/icons/dxicons.woff') format('woff'),
		url('/themes/vendor/icons/dxicons.ttf') format('truetype');
	font-weight: 400;
	font-style: normal;
}
</style>
