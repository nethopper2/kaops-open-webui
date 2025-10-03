/**
 * Used to send messages for decoupled communication.
 */
import { createHooks } from 'hookable';

export type PrivateAiExtras = {
	directive?: {
		name: string
		payload?: Record<string, unknown>;
	}
	metadata?: Record<string, unknown>;
};

export const appHooks = createHooks<{
	// Used to indicate the user wants only a private model selection.
	'models.select.privateOnly': () => void;
	'theme.changed': (params: { theme: string; mode: 'light' | 'dark' }) => void;
	// Fired whenever the selected model changes (including initial selection on page load)
	'model.changed': (params: {
		prevModelId: string | null;
		modelId: string | null;
		canShowPrivateAiToolbar: boolean;
	}) => void;
	// Request Chat to submit a new prompt
	'chat.submit': (params: {
		prompt: string;
		title?: string;
		privateAi?: PrivateAiExtras;
	}) => void;
	// Open/close/update a chat-level overlay that renders over the chat content area
	'chat.overlay': (params: {
		action: 'open' | 'close' | 'update';
		title?: string;
		component?: any;
		props?: Record<string, unknown>;
	}) => void;
	// Token Replacer: request preview to scroll to and highlight a token by id
	'private-ai.token-replacer.preview.select-token': (params: {
		id: string;
		state: 'draft' | 'saved';
	}) => void;
	// Token Replacer: preview component opened/closed notification
	'private-ai.token-replacer.preview.closed': () => void;
	'private-ai.token-replacer.preview.opened': () => void;
	// Token Replacer: user clicked a token in the preview (id is the occurrence id)
	'private-ai.token-replacer.preview.token-clicked': (params: { id: string }) => void;
	// Token Replacer: set specific ID groups for color/status tints
	'private-ai.token-replacer.preview.set-draft-ids': (params: { ids: string[] }) => void;
	'private-ai.token-replacer.preview.set-saved-ids': (params: { ids: string[] }) => void;
	'private-ai.token-replacer.preview.set-status-ids': (params: {
		draftIds?: string[];
		savedIds?: string[];
		noneIds?: string[];
	}) => void;
	// Token Replacer: provide replacement values per token occurrence id
	'private-ai.token-replacer.preview.set-values': (params: {
		byId: Record<string, { draft?: string; saved?: string }>;
	}) => void;
	// Token Replacer: request preview to reload its HTML, then reselect/scroll to a token
	'private-ai.token-replacer.preview.reload': (params: {
		id: string;
		state: 'draft' | 'saved';
	}) => void;
	// Token Replacer: preview finished rendering (initial load or reload)
	'private-ai.token-replacer.preview.reloaded': () => void;
}>();
