import { defineCustomElement } from 'vue';
import FileManager from '$lib/components-vue/storage/FileManager.vue';

if (!customElements.get('file-manager')) {
	// Register globally as a web component.
//  NOTE This has risks:
//   https://www.perplexity.ai/search/what-are-the-risks-of-includin-R93M2GlxSnWv7DOVHLLIiQ
	customElements.define('file-manager', defineCustomElement(FileManager));
}
