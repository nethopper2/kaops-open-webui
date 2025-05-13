<script setup lang="ts">
import 'devextreme/dist/css/dx.dark.css';
import { DxButton } from 'devextreme-vue/button';
import { DxContextMenu, DxFileManager, DxItem, DxPermissions } from 'devextreme-vue/file-manager';
import { DxForm, DxItem as DxFormItem } from 'devextreme-vue/form';
import { DxPopup, DxToolbarItem } from 'devextreme-vue/popup';
import 'devextreme-vue/tag-box';
import 'devextreme-vue/text-area';
import { DxTextBox } from 'devextreme-vue/text-box';
import RemoteFileSystemProvider from 'devextreme/file_management/remote_provider';
import type { ContextMenuItemClickEvent } from 'devextreme/ui/file_manager';
import { onMounted, ref } from 'vue';
import { getBackendConfig } from '$lib/apis';
import { type $Fetch, ofetch } from 'ofetch';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { toast } from 'svelte-sonner';

const props = defineProps(['i18n'])

let apiFetch: $Fetch;

const loading = ref(true);
const currentFileItem = ref<FileSystemItem>();

let fileSystemProvider: RemoteFileSystemProvider;

const itemViewConfig = {
	details: {
		columns: [
			// TODO: This should not prevent the icons from showing, but it does. How to fix this?
			//  Seems it is a bug in DevExtreme Vue.
			'name',
			// customize to show the time in the Date Modified column
			{
				dataField: 'dateModified',
				dataType: 'datetime',
				caption: 'Date Modified',
				width: 'auto'
			},
			'size'
		]
	}
};

async function handleContextMenuItemClick(e: ContextMenuItemClickEvent) {
	if (e.itemData.options.action === 'editMetadata') {
		currentFileItem.value = e.fileSystemItem;
		await loadMetadata();
		showEditMetadataPopup.value = true;
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

				if(response.success) {
					toast.success(
						props.i18n.t(`Metadata saved`)
					);
					showEditMetadataPopup.value = false;
				} else {
					throw new Error(response.message);
				}
			} else {
				console.warn('No current file item');
			}
		} catch (err) {
			console.log('ERROR', props.i18n);
			toast.error(
				props.i18n.t(`Failed to save metadata`)
			);
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
		endpointUrl: `${backendConfig.private_ai.rest_api_base_url}/api/storage/file-manager`, // TODO: cleanup - need env var for this?
		requestHeaders: {
			Authorization: 'Bearer ' + localStorage.getItem('token')
		}
	});

	loading.value = false;
});
</script>

<template>
	<dx-file-manager
		v-if="!loading"
		:file-system-provider="fileSystemProvider"
		:item-view="itemViewConfig"
		:on-context-menu-item-click="handleContextMenuItemClick"
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
.dx-filemanager {
	height: 100% !important;
}

/* a work around for hiding the checkboxes since selection-mode="none" causes a build error and is a hack */
.dx-filemanager .dx-checkbox {
	display: none !important;
}
</style>
