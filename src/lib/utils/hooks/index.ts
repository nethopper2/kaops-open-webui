/**
 * Used to send messages for decoupled communication.
 */
import { createHooks } from 'hookable';

export const appHooks = createHooks<{
	'models.select.privateOnly': () => void,
	'theme.changed': (params: { theme: string, mode: 'light' | 'dark' }) => void
}>()



