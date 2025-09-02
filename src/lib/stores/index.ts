import { APP_NAME, WEBUI_BASE_URL } from '$lib/constants';
import { type Writable, writable, derived } from 'svelte/store';
import type { ModelConfig } from '$lib/apis';
import type { Banner } from '$lib/types';
import type { Socket } from 'socket.io-client';
import type { ComponentType } from 'svelte';

import emojiShortCodes from '$lib/emoji-shortcodes.json';
import { PRIVATE_AI_TOOLBAR_COMPONENTS } from '$lib/private-ai/toolbars';
import { appHooks } from '$lib/utils/hooks';

// Backend
export const WEBUI_NAME = writable(APP_NAME);
export const config: Writable<Config | undefined> = writable(undefined);
export const user: Writable<SessionUser | undefined> = writable(undefined);

// Electron App
export const isApp = writable(false);
export const appInfo = writable(null);
export const appData = writable(null);

// Frontend
export const MODEL_DOWNLOAD_POOL = writable({});

export const mobile = writable(false);

export const socket: Writable<null | Socket> = writable(null);
export const activeUserIds: Writable<null | string[]> = writable(null);
export const USAGE_POOL: Writable<null | string[]> = writable(null);

export const theme = writable('system');

export const shortCodesToEmojis = writable(
	Object.entries(emojiShortCodes).reduce((acc, [key, value]) => {
		if (typeof value === 'string') {
			acc[value] = key;
		} else {
			for (const v of value) {
				acc[v] = key;
			}
		}

		return acc;
	}, {})
);

export const TTSWorker = writable(null);

export const chatId = writable('');
export const chatTitle = writable('');

export const channels = writable([]);
export const chats = writable(null);
export const pinnedChats = writable([]);
export const tags = writable([]);
export const folders = writable([]);

export const selectedFolder = writable(null);

export const models: Writable<Model[]> = writable([]);
export const isPublicModelChosen = writable(true);

export const prompts: Writable<null | Prompt[]> = writable(null);
export const knowledge: Writable<null | Document[]> = writable(null);
export const tools = writable(null);
export const functions = writable(null);

export const toolServers = writable([]);

export const banners: Writable<Banner[]> = writable([]);

export const settings: Writable<Settings> = writable({});

export const showSidebar = writable(false);
export const showSearch = writable(false);
export const showSettings = writable(false);
export const showShortcuts = writable(false);
export const showArchivedChats = writable(false);
export const showChangelog = writable(false);

// Used to show a toolbar when the selected model supports it.
export const showPrivateAiModelToolbar = writable(false);

export const showControls = writable(false);
export const showOverview = writable(false);
export const showArtifacts = writable(false);
export const showCallOverlay = writable(false);

// Ensure mutual exclusivity between Controls and Private AI Toolbar globally
// This centralizes the logic so only one of these can be true at a time
let __enforcingExclusivePanels = false;
showControls.subscribe((v) => {
	if (__enforcingExclusivePanels) return;
	if (v) {
		__enforcingExclusivePanels = true;
		showPrivateAiModelToolbar.set(false);
		__enforcingExclusivePanels = false;
	}
});
showPrivateAiModelToolbar.subscribe((v) => {
	if (__enforcingExclusivePanels) return;
	if (v) {
		__enforcingExclusivePanels = true;
		showControls.set(false);
		__enforcingExclusivePanels = false;
	}
});

// Single source of truth for which right-side pane is active in the PaneGroup
export const activeRightPane = derived(
	[showControls, showPrivateAiModelToolbar],
	([controls, privateAi]) => (controls ? 'controls' : privateAi ? 'private' : null) as 'controls' | 'private' | null
);


// Selected single model id used for Private AI toolbars
export const currentSelectedModelId: Writable<string | null> = writable<string | null>(null);

// Derived: component to render for the selected model's toolbar (if any)
export const privateAiModelToolbarComponent = derived(currentSelectedModelId, (id): ComponentType | null => {
	if (!id) return null;
	return PRIVATE_AI_TOOLBAR_COMPONENTS[id] ?? null;
});

// Derived: whether Private AI Model Sidekick can be used with the selected model
export const canShowPrivateAiModelToolbar = derived(privateAiModelToolbarComponent, (comp) => Boolean(comp));

// Derived: avatar URL for the selected model (matches ModelSelector avatar)
export const privateAiSelectedModelAvatarUrl = derived(
	[currentSelectedModelId, models],
	([id, $models]) => {
		if (!id) return `${WEBUI_BASE_URL}/static/favicon.png`;
		const model = ($models || []).find((m) => m.id === id);
		return (
			(model?.info as any)?.meta?.profile_image_url ?? `${WEBUI_BASE_URL}/static/favicon.png`
		);
	}
);


// Emit model.changed hook whenever the selected model changes
let __prevHookModelId: string | null = null;
currentSelectedModelId.subscribe((modelId) => {
	const prevModelId = __prevHookModelId;
	__prevHookModelId = modelId;
	try {
		// Compute canShow synchronously to avoid reactive timing issues
		const canShow = !!(modelId && PRIVATE_AI_TOOLBAR_COMPONENTS[modelId]);
		appHooks.callHook('model.changed', {
			prevModelId,
			modelId,
			canShowPrivateAiToolbar: canShow
		});
	} catch {
		// ignore hook errors
	}
});

export const artifactCode = writable(null);

export const temporaryChatEnabled = writable(false);
export const scrollPaginationEnabled = writable(false);
export const currentChatPage = writable(1);

export const isLastActiveTab = writable(true);
export const playingNotificationSound = writable(false);

export type Model = OpenAIModel | OllamaModel;

type BaseModel = {
	id: string;
	name: string;
	info?: ModelConfig;
	owned_by: 'ollama' | 'openai' | 'arena';
};

export interface OpenAIModel extends BaseModel {
	owned_by: 'openai';
	external: boolean;
	source?: string;
}

export interface OllamaModel extends BaseModel {
	owned_by: 'ollama';
	details: OllamaModelDetails;
	size: number;
	description: string;
	model: string;
	modified_at: string;
	digest: string;
	ollama?: {
		name?: string;
		model?: string;
		modified_at: string;
		size?: number;
		digest?: string;
		details?: {
			parent_model?: string;
			format?: string;
			family?: string;
			families?: string[];
			parameter_size?: string;
			quantization_level?: string;
		};
		urls?: number[];
	};
}

type OllamaModelDetails = {
	parent_model: string;
	format: string;
	family: string;
	families: string[] | null;
	parameter_size: string;
	quantization_level: string;
};

type Settings = {
	pinnedModels?: never[];
	toolServers?: never[];
	detectArtifacts?: boolean;
	showUpdateToast?: boolean;
	showChangelog?: boolean;
	showEmojiInCall?: boolean;
	voiceInterruption?: boolean;
	collapseCodeBlocks?: boolean;
	expandDetails?: boolean;
	notificationSound?: boolean;
	notificationSoundAlways?: boolean;
	stylizedPdfExport?: boolean;
	notifications?: any;
	imageCompression?: boolean;
	imageCompressionSize?: any;
	widescreenMode?: null;
	largeTextAsFile?: boolean;
	promptAutocomplete?: boolean;
	hapticFeedback?: boolean;
	responseAutoCopy?: any;
	richTextInput?: boolean;
	params?: any;
	userLocation?: any;
	webSearch?: boolean;
	memory?: boolean;
	autoTags?: boolean;
	autoFollowUps?: boolean;
	splitLargeChunks?(body: any, splitLargeChunks: any): unknown;
	backgroundImageUrl?: null;
	landingPageMode?: string;
	iframeSandboxAllowForms?: boolean;
	iframeSandboxAllowSameOrigin?: boolean;
	scrollOnBranchChange?: boolean;
	directConnections?: null;
	chatBubble?: boolean;
	copyFormatted?: boolean;
	models?: string[];
	conversationMode?: boolean;
	speechAutoSend?: boolean;
	responseAutoPlayback?: boolean;
	audio?: AudioSettings;
	showUsername?: boolean;
	notificationEnabled?: boolean;
	highContrastMode?: boolean;
	title?: TitleSettings;
	splitLargeDeltas?: boolean;
	chatDirection?: 'LTR' | 'RTL' | 'auto';
	ctrlEnterToSend?: boolean;
	showUpdateToast?: boolean;

	system?: string;
	seed?: number;
	temperature?: string;
	repeat_penalty?: string;
	top_k?: string;
	top_p?: string;
	num_ctx?: string;
	num_batch?: string;
	num_keep?: string;
	options?: ModelOptions;
};

type ModelOptions = {
	stop?: boolean;
};

type AudioSettings = {
	stt: any;
	tts: any;
	STTEngine?: string;
	TTSEngine?: string;
	speaker?: string;
	model?: string;
	nonLocalVoices?: boolean;
};

type TitleSettings = {
	auto?: boolean;
	model?: string;
	modelExternal?: string;
	prompt?: string;
};

type Prompt = {
	command: string;
	user_id: string;
	title: string;
	content: string;
	timestamp: number;
};

type Document = {
	collection_name: string;
	filename: string;
	name: string;
	title: string;
};

type Config = {
	license_metadata: any;
	status: boolean;
	name: string;
	version: string;
	default_locale: string;
	default_models: string;
	default_prompt_suggestions: PromptSuggestion[];
	features: {
		auth: boolean;
		auth_trusted_header: boolean;
		enable_api_key: boolean;
		enable_signup: boolean;
		enable_login_form: boolean;
		enable_web_search?: boolean;
		enable_google_drive_integration: boolean;
		enable_onedrive_integration: boolean;
		enable_image_generation: boolean;
		enable_admin_export: boolean;
		enable_admin_chat_access: boolean;
		enable_community_sharing: boolean;
		enable_autocomplete_generation: boolean;
		enable_direct_connections: boolean;
		enable_version_update_check: boolean;
		enable_upstream_ui: boolean;
		enable_file_ingestion: boolean;
	};
	oauth: {
		providers: {
			[key: string]: string;
		};
	};
	ui?: {
		pending_user_overlay_title?: string;
		pending_user_overlay_description?: string;
	};
	private_ai: {
		// citation_document_url is likely temporary until we have multiple sources for rag data.
		citation_document_url: string;
		// If true, some original open web ui interfaces are shown instead of Private AI.
		enable_upstream_ui: boolean;
		rest_api_base_url: string;
		webui_custom?: {
			logo?: string;
			logoMaxHeight?: string;
			bgImageAuth?: string;
			bgImageAuthLight?: string;
		};
    docker_image?: string;
	};
};

type PromptSuggestion = {
	content: string;
	title: [string, string];
};

type SessionUser = {
	permissions: any;
	id: string;
	email: string;
	name: string;
	role: string;
	profile_image_url: string;
};
