<script setup lang="ts">
import { DxFileManager, DxPermissions } from 'devextreme-vue/file-manager'
import RemoteFileSystemProvider from 'devextreme/file_management/remote_provider'

const fileSystemProvider = new RemoteFileSystemProvider({
  endpointUrl: 'http://localhost:3000/api/file-manager', // TODO: cleanup - need env var for this?
})

const itemViewConfig = {
  details: {
    columns: [
      'name',
      // customize to show the time in the Date Modified column
      {
        dataField: 'dateModified',
        dataType: 'datetime',
        caption: 'Date Modified',
        width: 'auto',
      },
      'size',
    ],
  },
}
</script>

<template>
  <!-- @ts-expect-error: 'none' is undocumented but works to hide the checkboxes-->
  <dx-file-manager
    :file-system-provider="fileSystemProvider"
    :item-view="itemViewConfig"
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
  </dx-file-manager>
</template>

<style scoped>
/* a work around for hiding the checkboxes since selection-mode="none" causes a build error and is a hack */
.dx-filemanager .dx-checkbox {
  display: none !important;
}
</style>