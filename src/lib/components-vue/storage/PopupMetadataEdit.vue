<script setup lang="ts">
import { DxForm, DxItem as DxFormItem } from 'devextreme-vue/form';
import { DxPopup, DxToolbarItem } from 'devextreme-vue/popup';
import 'devextreme-vue/tag-box';
import 'devextreme-vue/text-area';
import { computed, onBeforeMount, ref, toRef, useHost, watch } from 'vue';
import { toast } from 'svelte-sonner';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { apiFetch } from '$lib/apis/private-ai/fetchClients';
import { DxLoadPanel } from 'devextreme-vue/load-panel';
import { appHooks } from '$lib/utils/hooks';

// Use a partial of FileSystemItem
export type FileItem =  Pick<FileSystemItem, 'isDirectory' | 'path'>

const props = defineProps<{
	fileItem?: FileItem;
	i18n: { t: (s: string) => string };
}>()

const svelteHost = useHost();

const emit = defineEmits(['update:visible', 'saved', 'cancelled']);
const localVisible = defineModel<boolean>('visible', { default: false })

const loadingVisible = ref(false);
const tagChoices = ref([] as Array<string>);
const metaDataToEdit = ref(getEmptyMetadata());

const fileOrDirectoryName = computed(() => {
	return (props.fileItem?.path ?? '').split('/').pop() ?? '';
});

const commonButtonOptions = {
	type: 'default',
	stylingMode: 'contained'
};

const saveButtonOptions = {
	...commonButtonOptions,
	text: 'Save',
	onClick: saveMetadata
};

async function saveMetadata() {
	try {
		if (props.fileItem) {
			const response = await apiFetch(`/storage/metadata`, {
				method: 'PUT',
				body: {
					filePath: props.fileItem.path,
					tags: metaDataToEdit.value.tags,
					contextData: metaDataToEdit.value.contextData
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

function getEmptyMetadata() {
	return {
		contextData: '',
		tags: [] as Array<string>
	};
}

async function loadMetadata() {
	if (props.fileItem) {
		try {
			const { metadata } = await apiFetch('/storage/metadata', {
				query: {
					filePath: props.fileItem.path
				}
			});

			if (metadata) {
				metaDataToEdit.value = structuredClone(metadata);
			} else {
				console.warn('No metadata found for file: ', props.fileItem.path);
				metaDataToEdit.value = getEmptyMetadata();
			}
		} catch (err) {
			console.error(err);
			metaDataToEdit.value = getEmptyMetadata();
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
		await Promise.all([loadTagOptions(), loadMetadata()])
	} catch (err) {
		console.error(err);
	} finally {
		loadingVisible.value = false;
	}

}

function handleDialogShown() {
	// Could be used for additional initialization if needed
	console.log('@@ i18n is --> ',props.i18n);
	console.log('@@ i18n.t is --> ',props.i18n.t);
}

function handleDialogHidden() {
	metaDataToEdit.value = getEmptyMetadata();
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

// TODO: cleanup - This them related code is duplicated. Move it to a composable.
function loadTheme(href: string) {
	unloadCurrentTheme();

	const linkHead = document.createElement('link');
	linkHead.setAttribute('rel', 'stylesheet');
	linkHead.setAttribute('href', href);
	linkHead.setAttribute('data-loaded-theme-head', 'true'); // easier removal later
	document.head.appendChild(linkHead);

	const link = document.createElement('link');
	link.setAttribute('rel', 'stylesheet');
	link.setAttribute('href', href);
	link.setAttribute('data-loaded-theme', 'true'); // easier removal later
	svelteHost?.shadowRoot?.appendChild?.(link);

	// TODO: cleanup - need to do this for the popup?
	// and tell the Popup to redraw
	// TRefFileManager.value?.instance?.repaint?.();
}

function loadDarkTheme() {
	// REMINDER: If the devextreme dependency is upgraded, you may need to
	// re-copy the styles from `devextreme/dist/css`
	loadTheme('/themes/vendor/dx.dark.css');
	console.log('loaded file manager dark theme');
}

function loadLightTheme() {
	// REMINDER: If the devextreme dependency is upgraded, you may need to
	// re-copy the styles from `devextreme/dist/css`
	loadTheme('/themes/vendor/dx.light.css');
	console.log('loaded file manager light theme');
}

function unloadCurrentTheme() {
	const linkHead = document.head.querySelector('link[data-loaded-theme-head="true"]');
	if (linkHead) {
		console.log('removed file manager theme from head');
		linkHead.remove();
	}

	const link = svelteHost?.shadowRoot?.querySelector?.('link[data-loaded-theme="true"]');
	if (link) {
		console.log('removed file manager theme from shadowRoot');
		link.remove();
	}
}

let unregisterHooks: () => void;

onBeforeMount(() => {
	// load the proper theme based on the host.
	if (document.documentElement.classList.contains('dark')) {
		loadDarkTheme();
	} else {
		loadLightTheme();
	}

	unregisterHooks = appHooks.hook('theme.changed', ({ mode }) => {
		if (mode === 'dark') {
			loadDarkTheme();
		} else {
			loadLightTheme();
		}
	});
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
		<dx-load-panel  v-model:visible="loadingVisible"/>

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
			<dx-form v-model:form-data="metaDataToEdit">
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
					help-text="Provides additional AI context during RAG"
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
			:options="saveButtonOptions"
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
