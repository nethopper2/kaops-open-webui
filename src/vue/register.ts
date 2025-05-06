import { defineCustomElement } from 'vue'
import MyVueComponent from './index.vue'

// Wrap in defineCustomElement
const MyVueElement = defineCustomElement(MyVueComponent)

// Register globally
customElements.define('my-vue-element', MyVueElement)