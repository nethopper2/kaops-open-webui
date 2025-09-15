/**
 * Used to send messages for decoupled communication.
 */
import { createHooks } from 'hookable';

export const appHooks = createHooks<{
	// Used to indicate the user wants only a private model selection.
	'models.select.privateOnly': () => void,
	'theme.changed': (params: { theme: string; mode: 'light' | 'dark' }) => void,
	// Fired whenever the selected model changes (including initial selection on page load)
	'model.changed': (params: { prevModelId: string | null; modelId: string | null; canShowPrivateAiToolbar: boolean }) => void,
	// Request Chat to submit a new prompt
	'chat.submit': (params: { prompt: string }) => void,
	// Open/close/update a chat-level overlay that renders over the chat content area
	'chat.overlay': (params: { action: 'open' | 'close' | 'update'; title?: string; component?: any; props?: Record<string, unknown> }) => void,
	// Token Replacer: request preview to scroll to and highlight a token by id
	'private-ai.token-replacer.preview.select-token': (params: { id: string; state: 'draft' | 'saved' }) => void,
	// Token Replacer: preview component opened/closed notification
	'private-ai.token-replacer.preview.closed': () => void
	'private-ai.token-replacer.preview.opened': () => void
}>();



