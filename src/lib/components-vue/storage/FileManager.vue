<script setup lang="ts">
import { DxButton } from 'devextreme-vue/button';
import {
	DxColumn,
	DxContextMenu,
	DxDetails,
	DxFileManager,
	DxItem,
	DxItemView,
	DxPermissions,
	DxToolbar
} from 'devextreme-vue/file-manager';
import { DxForm, DxItem as DxFormItem } from 'devextreme-vue/form';
import { DxPopup, DxToolbarItem } from 'devextreme-vue/popup';
import 'devextreme-vue/tag-box';
import 'devextreme-vue/text-area';
import { DxTextBox } from 'devextreme-vue/text-box';
import RemoteFileSystemProvider from 'devextreme/file_management/remote_provider';
import type {
	ContextMenuItemClickEvent,
	ContextMenuShowingEvent
} from 'devextreme/ui/file_manager';
import { onBeforeMount, onMounted, onUnmounted, ref, useHost } from 'vue';
import { getBackendConfig } from '$lib/apis';
import { type $Fetch, ofetch } from 'ofetch';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { toast } from 'svelte-sonner';
import { appHooks } from '$lib/utils/hooks';

const props = defineProps(['i18n']);
const svelteHost = useHost();

// Left as a reminder on how to expose methods as a custom element.
// if (svelteHost) {
// 	svelteHost.customMethod = () => {
// 		console.log('customMethod called');
// 	};
// }

const TRefFileManager = ref();

let apiFetch: $Fetch;

const loading = ref(true);
const currentFileItem = ref<FileSystemItem>();

let fileSystemProvider: RemoteFileSystemProvider;

async function handleContextMenuItemClick(e: ContextMenuItemClickEvent) {
	if (e.itemData.options.action === 'editMetadata') {
		currentFileItem.value = e.fileSystemItem;
		await loadMetadata();
		showEditMetadataPopup.value = true;
	}
}

function handleContextMenuShowing(e: ContextMenuShowingEvent) {
	if (!e.fileSystemItem?.path.length) {
		e.cancel = true; // Prevent the context menu from showing
	}
}

const commonButtonOptions = {
	type: 'default',
	stylingMode: 'contained'
};

const showEditMetadataPopup = ref(false);
const saveButtonOptions = {
	...commonButtonOptions,
	text: 'Save',
	onClick: async (e: MouseEvent) => {
		try {
			if (currentFileItem.value) {
				const response = await apiFetch(`/storage/metadata`, {
					method: 'PUT',
					body: {
						filePathParts: currentFileItem.value.pathKeys,
						tags: metaDataToEdit.value.tags,
						contextData: metaDataToEdit.value.contextData
					}
				});

				if (response.success) {
					toast.success(props.i18n.t(`Metadata saved`));
					showEditMetadataPopup.value = false;
				} else {
					throw new Error(response.message);
				}
			} else {
				console.warn('No current file item');
			}
		} catch (err) {
			console.log('ERROR', props.i18n);
			toast.error(props.i18n.t(`Failed to save metadata`));
		}
	}
};

const tagToAdd = ref('');
const tagChoices = ref([] as Array<string>);

const metaDataToEdit = ref(getEmptyMetadata());

function getEmptyMetadata() {
	return {
		contextData: '',
		tags: [] as Array<string>
	};
}

function addTagOptionAndAutoSelectIt() {
	if (tagToAdd.value.length === 0) return;

	if (!tagChoices.value.includes(tagToAdd.value)) {
		tagChoices.value = [...tagChoices.value, tagToAdd.value];
	}

	if (!metaDataToEdit.value.tags.includes(tagToAdd.value)) {
		metaDataToEdit.value.tags = [...metaDataToEdit.value.tags, tagToAdd.value];
	}

	tagToAdd.value = '';
}

async function loadMetadata() {
	if (currentFileItem.value) {
		try {
			const { metadata } = await apiFetch('/storage/metadata', {
				query: {
					filePathParts: currentFileItem.value.pathKeys
				}
			});

			if (metadata) {
				metaDataToEdit.value = structuredClone(metadata);
			} else {
				console.warn('No metadata found for file: ', currentFileItem.value.pathKeys);
			}
		} catch (err) {
			console.error(err);
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
	}
}

function handleDialogShowing() {
	loadTagOptions();
}

function handleDialogShown() {
	//
}

function handleDialogHidden() {
	metaDataToEdit.value = getEmptyMetadata();
}

function loadTheme(href: string) {
	unloadCurrentTheme();

	const link = document.createElement('link');
	link.setAttribute('rel', 'stylesheet');
	link.setAttribute('href', href);
	link.setAttribute('data-loaded-theme', 'true'); // easier removal later
	svelteHost?.shadowRoot?.appendChild?.(link);

	// and tell the FileManager to redraw
	TRefFileManager.value?.instance?.repaint?.();
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
	const link = svelteHost?.shadowRoot?.querySelector?.('link[data-loaded-theme="true"]');
	if (link) {
		console.log('removed file manager theme');
		link.remove();
	}
}

let unregisterHooks: () => void;

onBeforeMount(() => {
	// load the proper theme based on the host.
	if(document.documentElement.classList.contains('dark')){
		loadDarkTheme();
	}else{
		loadLightTheme();
	}

	unregisterHooks = appHooks.hook('theme.changed', ({mode}) => {
		if(mode === 'dark') {
			loadDarkTheme();
		} else {
			loadLightTheme();
		}
	});
});

onMounted(async () => {
	loading.value = true;

	const backendConfig = await getBackendConfig();

	apiFetch = ofetch.create({
		baseURL: `${backendConfig.private_ai.rest_api_base_url}/api`,
		onRequest({ request, options }) {
			options.headers ??= new Headers();
			options.headers.set('Authorization', `Bearer ${localStorage.getItem('token')}`);
		}
	});

	fileSystemProvider = new RemoteFileSystemProvider({
		endpointUrl: `${backendConfig.private_ai.rest_api_base_url}/api/storage/file-manager`,
		requestHeaders: {
			Authorization: 'Bearer ' + localStorage.getItem('token')
		}
	});

	loading.value = false;
});

onUnmounted(() => {
	unregisterHooks()
})
</script>

<template>
	<dx-file-manager
		v-if="!loading"
		ref="TRefFileManager"
		:file-system-provider="fileSystemProvider"
		:on-context-menu-item-click="handleContextMenuItemClick"
		:on-context-menu-showing="handleContextMenuShowing"
		root-folder-name="Knowledge Data"
		v-bind="$attrs"
	>
		<dx-permissions
			:create="false"
			:copy="false"
			:move="false"
			:delete="false"
			:rename="false"
			:upload="false"
			:download="false"
		/>

		<dx-context-menu>
			<dx-item text="Edit Metadata" :options="{ action: 'editMetadata' }" />
		</dx-context-menu>

		<dx-item-view>
			<dx-details>
				<dx-column data-field="thumbnail" />
				<dx-column data-field="name" />
				<dx-column
					data-field="dateModified"
					dataType="datetime"
					caption="Date Modified"
					width="auto"
				/>
				<dx-column data-field="size" />
			</dx-details>
		</dx-item-view>

		<dx-toolbar>
			<dx-item name="showNavPane" :visible="true" />
			<dx-item name="refresh" />
			<dx-item name="separator" location="after" />
			<dx-item name="switchView" />
		</dx-toolbar>
	</dx-file-manager>

	<dx-popup
		v-model:visible="showEditMetadataPopup"
		title="Edit Metadata"
		:show-close-button="true"
		@showing="handleDialogShowing"
		@shown="handleDialogShown"
		@hidden="handleDialogHidden"
	>
		<!--
		The content slot is used normally, but as a web component for use with
		svelte, the default slot works.
		-->
		<!-- <template #content>-->
		<div class="flex justify-end gap-2 pb-4">
			<dx-text-box v-model="tagToAdd" placeholder="Tag" />
			<dx-button
				text="Add Tag"
				:options="commonButtonOptions"
				@click="addTagOptionAndAutoSelectIt"
			/>
		</div>

		<form>
			<dx-form v-model:form-data="metaDataToEdit">
				<dx-form-item
					data-field="tags"
					editor-type="dxTagBox"
					:editor-options="{ dataSource: tagChoices, showSelectionControls: true }"
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
		<!-- </template>-->

		<dx-toolbar-item
			widget="dxButton"
			toolbar="bottom"
			location="after"
			:options="{
				text: 'Cancel',
				type: 'default',
				stylingMode: 'outlined',
				onClick: () => {
					showEditMetadataPopup = false;
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
	src: local("DevExtreme Generic Icons"), local("devextreme_generic_icons"), url("/themes/vendor/icons/dxicons.woff2") format("woff2"), url("/themes/vendor/icons/dxicons.woff") format("woff"), url("/themes/vendor/icons/dxicons.ttf") format("truetype");
	font-weight: 400;
	font-style: normal
}

.dx-filemanager {
	height: 100% !important;
}

/* a work around for hiding the checkboxes since selection-mode="none" causes a build error and is a hack */
.dx-filemanager .dx-checkbox {
	display: none !important;
}
</style>
