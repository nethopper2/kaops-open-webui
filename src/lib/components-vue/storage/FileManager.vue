<script setup lang="ts">
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
import RemoteFileSystemProvider from 'devextreme/file_management/remote_provider';
import type {
	ContextMenuItemClickEvent,
	ContextMenuShowingEvent
} from 'devextreme/ui/file_manager';
import { onBeforeMount, onMounted, onUnmounted, ref, useHost } from 'vue';
import { getBackendConfig } from '$lib/apis';
import FileSystemItem from 'devextreme/file_management/file_system_item';
import { appHooks } from '$lib/utils/hooks';
import PopupMetadataEdit from './PopupMetadataEdit.vue';

const props = defineProps(['i18n']);
const svelteHost = useHost();

// Left as a reminder on how to expose methods as a custom element.
// if (svelteHost) {
// 	svelteHost.customMethod = () => {
// 		console.log('customMethod called');
// 	};
// }

const TRefFileManager = ref();

const loading = ref(true);
const currentFileItem = ref<FileSystemItem>();

let fileSystemProvider: RemoteFileSystemProvider;

async function handleContextMenuItemClick(e: ContextMenuItemClickEvent) {
	if (e.itemData.options.action === 'editMetadata') {
		currentFileItem.value = e.fileSystemItem;
		showEditMetadataPopup.value = true;
	}
}

function handleContextMenuShowing(e: ContextMenuShowingEvent) {
	if (!e.fileSystemItem?.path.length) {
		e.cancel = true; // Prevent the context menu from showing
	}
}

const showEditMetadataPopup = ref(false);

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

onMounted(async () => {
	loading.value = true;

	const backendConfig = await getBackendConfig();

	fileSystemProvider = new RemoteFileSystemProvider({
		endpointUrl: `${backendConfig.private_ai.rest_api_base_url}/api/storage/file-manager`,
		requestHeaders: {
			Authorization: 'Bearer ' + localStorage.getItem('token')
		}
	});

	loading.value = false;
});

onUnmounted(() => {
	unregisterHooks();
});
</script>

<template>
	<dx-file-manager
		v-if="!loading"
		ref="TRefFileManager"
		:file-system-provider="fileSystemProvider"
		:on-context-menu-item-click="handleContextMenuItemClick"
		:on-context-menu-showing="handleContextMenuShowing"
		:root-folder-name="i18n.t('Knowledge Data')"
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

	<popup-metadata-edit
		v-model:visible="showEditMetadataPopup"
		:file-item="currentFileItem as FileSystemItem"
		:i18n="i18n"
	/>
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

.dx-filemanager {
	height: 100% !important;
}

/* a work around for hiding the checkboxes since selection-mode="none" causes a build error and is a hack */
.dx-filemanager .dx-checkbox {
	display: none !important;
}
</style>
