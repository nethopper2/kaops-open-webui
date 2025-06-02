export type Banner = {
	id: string;
	type: string;
	title?: string;
	content: string;
	url?: string;
	dismissible?: boolean;
	timestamp: number;
};

export enum TTS_RESPONSE_SPLIT {
	PUNCTUATION = 'punctuation',
	PARAGRAPHS = 'paragraphs',
	NONE = 'none'
}

export type DataSource = {
	id: string;
	name: string;
	context: string;
	syncStatus: 'synced' | 'syncing' | 'error' | 'unsynced';
	lastSync: string; // ISO date string
	icon: string; // Icon name or component
	action?: string; // Optional action text
};
