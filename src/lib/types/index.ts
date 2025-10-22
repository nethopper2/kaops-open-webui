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
	permission?: string;
	sync_status: 'synced' | 'syncing' | 'error' | 'embedding' | 'embedded' | 'unsynced' | 'deleting' | 'deleted' | 'incomplete';
	last_sync: string | null; // ISO date string
	// Progress tracking fields
	files_processed?: number;
	files_total?: number;
	mb_processed?: number;
	mb_total?: number;
	sync_start_time?: number;
	sync_results?: {
		latest_sync?: {
			added: number;
			updated: number;
			removed: number;
			skipped: number;
			runtime_ms: number;
			api_calls: number;
			skip_reasons: Record<string, number>;
			sync_timestamp: number;
		};
		overall_profile?: {
			total_files: number;
			total_size_bytes: number;
			last_updated: number;
			folders_count: number;
		};
	};
	icon: string; // Icon name or component
	action?: string; // Optional action text
	layer?: string; // Optional layer information
};
