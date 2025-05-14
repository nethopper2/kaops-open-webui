import { defineCustomElement } from 'vue';
import FileManager from '$lib/components-vue/storage/FileManager.vue';

// Register global web components.
//  NOTE This has risks:
//   https://www.perplexity.ai/search/what-are-the-risks-of-includin-R93M2GlxSnWv7DOVHLLIiQ
if (!customElements.get('file-manager')) {
	customElements.define('file-manager', defineCustomElement(FileManager));
}
