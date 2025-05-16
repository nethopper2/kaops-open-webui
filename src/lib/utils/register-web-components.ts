import { defineCustomElement } from 'vue';
import FileManager from '$lib/components-vue/storage/FileManager.vue';
import config from 'devextreme/core/config';

// Set the DevExpress license key. Eventually this may need to be an env var when more licenses are added.
// We set this here since these web components use this lib.
config({
	licenseKey:
		'ewogICJmb3JtYXQiOiAxLAogICJjdXN0b21lcklkIjogIjczODBiMDU5LTQ5N2UtNGE3Zi1iMWFiLTliOTczYWM3MjlhMCIsCiAgIm1heFZlcnNpb25BbGxvd2VkIjogMjQyCn0=.E/58RrYHkSVT8/wxZdgKHK3UjeKxvtxjpslLCbnx+9zvRfvgRyvn88zb68oLJBGJPf4ptIfXUcOC8lC2+viJch2q+MAilmWX2zneS/5RqmhZaPUN6Z6LfGCrzkmOE7CeqiOSZQ=='
});

// Register global web components.
//  NOTE This has risks:
//   https://www.perplexity.ai/search/what-are-the-risks-of-includin-R93M2GlxSnWv7DOVHLLIiQ
if (!customElements.get('file-manager')) {
	customElements.define('file-manager', defineCustomElement(FileManager));
}
