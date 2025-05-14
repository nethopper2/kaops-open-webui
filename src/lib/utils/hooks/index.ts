/**
 * Used to send messages for decoupled communication.
 */
import { createHooks } from 'hookable';

export const appHooks = createHooks<{
	'theme.changed': (params: { theme: string, mode: 'light' | 'dark' }) => void
}>()



