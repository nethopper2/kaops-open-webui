<script setup lang="ts">
import { confirm } from 'devextreme/ui/dialog';
import { DxForm, DxItem as DxFormItem } from 'devextreme-vue/form';
import { DxPopup, DxToolbarItem } from 'devextreme-vue/popup';
import 'devextreme-vue/tag-box';
import 'devextreme-vue/text-area';
import { computed, onBeforeMount, ref, type useHost, watch } from 'vue';
import { toast } from 'svelte-sonner';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { metadataApi, MetadataError, MetadataValidator } from '$lib/apis/metadata';
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
const validationErrors = ref<string[]>([]);

// Character count for context field
const contextCharCount = computed(() => {
	const count = metadataToEdit.value.contextData?.length || 0;
	return count;
});

const contextCharRemaining = computed(() => {
	return 512 - contextCharCount.value;
});

const contextCharCountColor = computed(() => {
	const remaining = contextCharRemaining.value;
	if (remaining < 0) return 'text-red-500';
	if (remaining < 50) return 'text-yellow-500';
	return 'text-gray-500';
});


const fileOrDirectoryName = computed(() => {
	return (props.fileItem?.path ?? '').split('/').pop() ?? '';
});

// Helper function to safely translate strings
function t(key: string, fallback?: string): string {
	if (props.i18n && typeof props.i18n.t === 'function') {
		return props.i18n.t(key);
	}
	return fallback || key;
}

async function saveMetadata() {
	if (!props.fileItem) {
		console.warn('No current file item');
		return;
	}


	try {
		// Clear previous validation errors
		validationErrors.value = [];

		// Prepare metadata object for the new API
		const metadata: Record<string, string> = {};
		
		// Convert tags array to comma-separated string
		if (metadataToEdit.value.tags && metadataToEdit.value.tags.length > 0) {
			metadata.tags = metadataToEdit.value.tags.join(',');
		}
		
		// Add context data
		if (metadataToEdit.value.contextData) {
			metadata.context = metadataToEdit.value.contextData;
		}

		// Validate metadata before sending
		const validation = MetadataValidator.validateMetadata(metadata);
		if (!validation.valid) {
			validationErrors.value = validation.errors;
			toast.error(t('Validation failed. Please check your input.'));
			return;
		}

		// Use merge=true to preserve existing metadata
		await metadataApi.updateMetadata(props.fileItem.path, metadata, true);

		toast.success(t('Metadata saved'));
		localVisible.value = false;
		emit('saved');
	} catch (err) {
		console.error('Error saving metadata:', err);
		
		if (err instanceof MetadataError) {
			toast.error(t(err.message, err.message));
		} else {
			toast.error(t('Failed to save metadata'));
		}
	}
}

async function deleteMetadata() {
	if (!props.fileItem) {
		console.warn('No current file item');
		return;
	}

	try {
		await metadataApi.deleteMetadata(props.fileItem.path);
		toast.success(t('Metadata deleted'));
		localVisible.value = false;
		emit('saved');
	} catch (err) {
		console.error('Error deleting metadata:', err);
		
		if (err instanceof MetadataError) {
			toast.error(t(err.message, err.message));
		} else {
			toast.error(t('Failed to delete metadata'));
		}
	}
}

async function showConfirmDeleteDialog() {
	try {
		let result = await confirm(
			t('Are you sure you want to delete this metadata?'),
			t('Confirm Deletion')
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
	if (!props.fileItem) {
		return;
	}


	try {
		metadataExists.value = false;
		
		const response = await metadataApi.getMetadata(props.fileItem.path);

		if (response.exists && response.metadata.metadata) {
			const apiMetadata = response.metadata.metadata;
			
			// Convert API response to our form format
			const contextData = apiMetadata.context || '';
			const tags = apiMetadata.tags ? apiMetadata.tags.split(',').map(tag => tag.trim()).filter(tag => tag) : [];
			
			metadataToEdit.value = {
				contextData: contextData,
				tags: tags
			};
			
			
			metadataExists.value = true;
		} else {
			console.warn('No metadata found for file: ', props.fileItem.path);
			metadataToEdit.value = getEmptyMetadata();
			metadataExists.value = false;
		}
	} catch (err) {
		console.error('Error loading metadata:', err);
		
		// If it's a 404, that's expected for files without metadata
		if (err instanceof MetadataError && err.statusCode === 404) {
			metadataToEdit.value = getEmptyMetadata();
			metadataExists.value = false;
		} else {
			// For other errors, show a toast but don't break the UI
			toast.error(t('Failed to load metadata'));
			metadataToEdit.value = getEmptyMetadata();
			metadataExists.value = false;
		}
	}
}

async function loadTagOptions() {
	// For now, we'll use an empty array since the new API doesn't have a dedicated tags endpoint
	// In the future, this could be implemented by fetching all metadata and extracting unique tags
	try {
		// TODO: Implement batch metadata fetch to get all available tags
		// For now, use empty array - users can still add custom tags
		tagChoices.value = [];
	} catch (err) {
		console.error('Error loading tag options:', err);
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
	validationErrors.value = [];
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

		<!-- Validation Errors Display -->
		<div v-if="validationErrors.length > 0" class="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
			<div class="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
				{{ t('Validation Errors') }}
			</div>
			<ul class="text-sm text-red-700 dark:text-red-300 list-disc list-inside space-y-1">
				<li v-for="error in validationErrors" :key="error">{{ error }}</li>
			</ul>
		</div>

		<form class="space-y-6">
			<!-- Tags Section -->
			<div>
				<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
					Tags
				</label>
				<dx-form v-model:form-data="metadataToEdit">
					<dx-form-item
						data-field="tags"
						editor-type="dxTagBox"
						:label="{ visible: false }"
						:editor-options="{
							dataSource: tagChoices,
							showSelectionControls: true,
							acceptCustomValue: true,
							onValueChanged: (e: any) => {
								if (metadataToEdit) {
									metadataToEdit.tags = e.value;
								}
							}
						}"
					/>
				</dx-form>
				<div class="mt-1 text-xs text-gray-600">
					Enter tags
				</div>
			</div>

			<!-- Context Section -->
			<div>
				<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
					Context
				</label>
				<dx-form v-model:form-data="metadataToEdit">
					<dx-form-item
						data-field="contextData"
						editor-type="dxTextArea"
						:label="{ visible: false }"
						:editor-options="{
							height: 120,
							maxLength: 512,
							onValueChanged: (e: any) => {
								if (metadataToEdit) {
									metadataToEdit.contextData = e.value;
								}
							}
						}"
					/>
				</dx-form>
				<!-- Help text with tooltip under the form element -->
				<div class="mt-1 flex items-start gap-1 text-xs text-gray-600">
					<div class="relative inline-flex items-center justify-center w-3 h-3 text-gray-400 hover:text-gray-600 cursor-help group mt-0.5">
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3 h-3">
							<path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
						</svg>
						<!-- Tooltip - positioned to the right of the icon -->
						<div class="absolute bottom-full left-0 mb-2 px-3 py-2 text-xs text-white dark:text-gray-900 bg-gray-900 dark:bg-gray-100 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-[9999] w-80 max-w-[calc(100vw-2rem)]">
							{{ fileItem?.isDirectory
								? "To help our AI system generate accurate responses, please briefly describe this directory's purpose, list and explain its contents, outline any naming conventions, and provide instructions for use. Optionally, add example questions you might ask the AI about the files—this helps the AI understand your needs and improves its answers. Update this information whenever the directory changes."
								: "To help our AI system generate accurate responses, please provide a brief description of this file's purpose, explain its contents, and include instructions for use if applicable. Optionally, add example questions you might ask the AI about this file—this helps the AI understand its needs and improves its answers. If relevant, mention any important details such as the file's format, structure, or dependencies. Be sure to update this information whenever the file changes."
							}}
							<!-- Tooltip arrow - positioned to match left alignment -->
							<div class="absolute top-full left-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-100"></div>
						</div>
					</div>
					<span>
						{{ fileItem?.isDirectory
							? "Briefly describe this directory's purpose and contents to help our AI system generate accurate responses."
							: "Briefly describe this file's purpose and contents to help our AI system generate accurate responses."
						}}
					</span>
				</div>
				<!-- Character counter for context field -->
				<div class="mt-2 text-right">
					<span :class="contextCharCountColor" class="text-sm">
						<span v-if="contextCharRemaining >= 0">
							{{ contextCharRemaining }} remaining, 512 max
						</span>
						<span v-else class="text-red-500 font-medium">
							{{ Math.abs(contextCharRemaining) }} over limit, 512 max
						</span>
					</span>
				</div>
			</div>
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