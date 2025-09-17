<script lang="ts">
import { getContext, onDestroy, onMount } from 'svelte';
import { toast } from 'svelte-sonner';
import { ensureFilesFetched, selectedTokenizedDoc, selectedTokenizedDocPath } from '../stores';
import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
import { appHooks } from '$lib/utils/hooks';
import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
import { chatId, currentSelectedModelId } from '$lib/stores';
import {
	getTokenReplacementValues,
	putTokenReplacementValues,
	type TokenReplacementValue
} from '$lib/apis/private-ai/sidekicks/token-replacer';
import {
	clearTokenReplacerDraft,
	loadTokenReplacerDraft,
	saveTokenReplacerDraft,
	type TokenReplacerDraft
} from '../drafts';
import Spinner from '$lib/components/common/Spinner.svelte';
import Eye from '$lib/components/icons/Eye.svelte';
import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
import Tooltip from '$lib/components/common/Tooltip.svelte';
import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte';
import DOMPurify from 'dompurify';
import ListBullet from '$lib/components/icons/ListBullet.svelte';
import XMark from '$lib/components/icons/XMark.svelte';
import Minus from '$lib/components/icons/Minus.svelte';

const i18n = getContext('i18n');

function openPreviewPanel() {
	const file = $selectedTokenizedDoc;
	if (file) {
		appHooks.callHook('chat.overlay', {
			action: 'open',
			title: $i18n.t('Preview'),
			component: TokenizedDocPreview,
			props: { file, previewType: 'docx' }
		});
		isPreviewOpen = true;
		// After opening, inform the preview of which tokens currently have drafts
		try {
			const draftIds: string[] = [];
			for (let i = 0; i < tokens.length; i++) {
				const t = tokens[i];
				const state = computeTokenState(t);
				if (state === 'draft') {
					const ids = tokenOccurrences[t] ?? [];
					if (ids.length > 0) {
						draftIds.push(...ids);
					} else {
						// Fallback to legacy sequential id
						draftIds.push(`nh-token-${i + 1}`);
					}
				}
			}
			if (draftIds.length > 0) {
				appHooks.callHook('private-ai.token-replacer.preview.set-draft-ids', { ids: draftIds });
			}
		} catch {}
	}
}

function getFirstOccurrenceId(token: string, idx: number): string {
	const ids = tokenOccurrences[token];
	if (Array.isArray(ids) && ids.length > 0) return ids[0];
	// Fallback to legacy sequential id when occurrences are missing
	return `nh-token-${idx + 1}`;
}

function onPreviewTokenClick(idx: number, token: string) {
	const id = getFirstOccurrenceId(token, idx);
	const v = (values[token] ?? '').trim();
	const s = (savedValues[token] ?? '').trim();
	const state: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
	appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state });
	lastPreviewSelection = { id, state };
	lastPreviewToken = token;
}

// Stubbed data types
type Token = string;
type ReplacementValues = Record<string, string>;

// Prevent re-saving drafts during certain lifecycle windows (e.g., right after successful submit)
let suppressDraftPersistence = false;

let isLoading = true;
let isSubmitting = false;
let loadError: string | null = null;
let submitError: string | null = null;
let submitSuccess = false;

// Local state
let tokens: Token[] = [];
// values = current editable values (may include drafts)
let values: ReplacementValues = {};
// savedValues = last known server-saved values from GET or after successful PUT
let savedValues: ReplacementValues = {};
// Map of token -> occurrence IDs (in document order) for preview navigation
let tokenOccurrences: Record<string, string[]> = {};
let searchQuery = '';
let showConfirm = false;
let showGenerateConfirm = false;

// Track if the TokenizedDocPreview overlay is open
let isPreviewOpen = false;
let removeOverlayHook: (() => void) | null = null;
let removePreviewClosedHook: (() => void) | null = null;
// Track the last previewed token selection to update highlight state on edits
let lastPreviewSelection: { id: string; state: 'draft' | 'saved' } | null = null;
let lastPreviewToken: string | null = null;

// Local overlay for token occurrences
let isTokenOverlayOpen = false;
let overlayToken: string | null = null;
let overlayTokenIndex = -1; // index in filteredTokens when opened
let overlayOccurrences: string[] = [];
let overlayCurrentIdx = 0;

$: overlayState = overlayToken ? computeTokenState(overlayToken) : 'saved';

function onOverlayFocus() {
	selectOverlayOccurrence(overlayCurrentIdx);
}

function onOverlayInput(e: Event) {
	if (!overlayToken) return;
	const target = e.currentTarget as HTMLInputElement;
	const v = target.value;
	updateValue(overlayToken, v);
	if (isPreviewOpen) {
		const id = overlayOccurrences[overlayCurrentIdx];
		const newState = computeTokenState(overlayToken, v);
		appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
		lastPreviewSelection = { id, state: newState };
		lastPreviewToken = overlayToken;
	}
}

function computeTokenState(token: string, valueOverride?: string): 'draft' | 'saved' {
	const v = ((valueOverride ?? values[token]) ?? '').trim();
	const s = (savedValues[token] ?? '').trim();
	return v === s ? 'saved' : 'draft';
}

function selectOverlayOccurrence(idx: number) {
	if (!overlayToken || !isPreviewOpen) return;
	overlayCurrentIdx = Math.max(0, Math.min(idx, overlayOccurrences.length - 1));
	const id = overlayOccurrences[overlayCurrentIdx];
	const state = computeTokenState(overlayToken);
	appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state });
	lastPreviewSelection = { id, state };
	lastPreviewToken = overlayToken;
}

function openTokenOverlay(i: number, token: string) {
	overlayToken = token;
	overlayTokenIndex = i;
	// Use provided occurrence IDs if available; otherwise fallback to legacy id
	const ids = tokenOccurrences[token];
	overlayOccurrences = Array.isArray(ids) && ids.length > 0 ? ids : [`nh-token-${i + 1}`];
	isTokenOverlayOpen = true;
	// On open, highlight the first occurrence in the preview if open
	if (isPreviewOpen) {
		selectOverlayOccurrence(0);
	}
}

function closeTokenOverlay() {
	isTokenOverlayOpen = false;
}

function gotoPrevOccurrence() {
	if (overlayOccurrences.length <= 1) return;
	const next = (overlayCurrentIdx - 1 + overlayOccurrences.length) % overlayOccurrences.length;
	selectOverlayOccurrence(next);
}

function gotoNextOccurrence() {
	if (overlayOccurrences.length <= 1) return;
	const next = (overlayCurrentIdx + 1) % overlayOccurrences.length;
	selectOverlayOccurrence(next);
}

// Sticky helpers for measuring header height
let headerEl: HTMLDivElement | null = null;
let headerHeight = 0;
let headerRO: ResizeObserver | null = null;
let headerResizeHandler: (() => void) | null = null;

// Track the visibility of SelectedDocumentSummary so we can show a secondary Preview button
let summaryEl: HTMLDivElement | null = null;
let isSummaryVisible = true;
let summaryRaf = 0;
let summaryScrollHandler: (() => void) | null = null;
let summaryIO: IntersectionObserver | null = null;

function setupSummaryObserver() {
	try {
		summaryIO?.disconnect();
	} catch {}
	if (!summaryEl) return;
	try {
		summaryIO = new IntersectionObserver(
			(entries) => {
				const entry = entries[0];
				isSummaryVisible = !!(entry?.isIntersecting && entry.intersectionRatio > 0);
			},
			{ root: null, rootMargin: `-${headerHeight}px 0px 0px 0px`, threshold: [0, 0.01] }
		);
		summaryIO.observe(summaryEl);
	} catch {}
}

function updateHeaderHeight() {
	headerHeight = headerEl?.offsetHeight ?? 0;
	// Recompute summary visibility when the header size changes
	scheduleSummaryVisibilityCheck();
	// Re-init intersection observer to respect new headerHeight offset
	setupSummaryObserver();
}

function computeSummaryVisibility() {
	if (!summaryEl) {
		isSummaryVisible = true;
		return;
	}
	const rect = summaryEl.getBoundingClientRect();
	// Consider it visible if any part of the summary is within the viewport area below the sticky header
	const visible = rect.bottom > headerHeight && rect.top < window.innerHeight;
	isSummaryVisible = visible;
}

function scheduleSummaryVisibilityCheck() {
	try { cancelAnimationFrame(summaryRaf); } catch {}
	summaryRaf = requestAnimationFrame(computeSummaryVisibility);
}

// Derived counts and stats
$: totalTokens = tokens.length;
$: providedCount = tokens.reduce((acc, t) => {
	const v = (values[t] ?? '').trim();
	const s = (savedValues[t] ?? '').trim();
	return v.length > 0 && v === s ? acc + 1 : acc;
}, 0);
$: savedCount = tokens.reduce((acc, t) => (((savedValues[t] ?? '').trim().length > 0) ? acc + 1 : acc), 0);
$: emptyCount = tokens.reduce((acc, t) => (((values[t] ?? '').trim().length === 0) ? acc + 1 : acc), 0);
$: draftCount = tokens.reduce((acc, t) => ((values[t] ?? '').trim() !== (savedValues[t] ?? '').trim() ? acc + 1 : acc), 0);
$: progressPercent = totalTokens > 0 ? Math.round((providedCount / totalTokens) * 100) : 0;

// Build confirmation message (markdown supported by ConfirmDialog)
$: confirmMessage = `${$i18n.t('You are about to submit all token/value pairs for the selected document.')}<br><br>` +
	`${$i18n.t('Tokens total')}: <b>${totalTokens}</b><br>` +
	`${$i18n.t('Replacement values provided')}: <b>${providedCount}</b><br>` +
	`${$i18n.t('Replacement values empty')}: <b>${emptyCount}</b><br><br>` +
	`${$i18n.t('All tokens will be submitted, including those not currently visible due to search filters.')}<br><br>` +
	`${$i18n.t('Do you want to continue?')}`;

// Load tokens and values from API
async function loadTokensAndValues(): Promise<{ tokens: Token[]; values: ReplacementValues; occurrences: Record<string, string[]> }> {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	if (!cId || !mId) {
		throw new Error('Missing context: chat or model');
	}
	const res = await getTokenReplacementValues(cId, mId);
	const data = (res as any)?.data ?? res;
	const tokensFromApi: string[] = data?.tokens ?? [];
	const valuesFromApi: Record<string, string> = data?.values ?? {};
	const occFromApi: Record<string, string[]> = data?.occurrences ?? {};
	return { tokens: tokensFromApi, values: valuesFromApi, occurrences: occFromApi };
}

// Submit replacement values to API
async function submitReplacementValues(payload: { token: string; value: string }[]): Promise<void> {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	const dPath = $selectedTokenizedDocPath as string | null;
	if (!cId || !mId || !dPath) {
		throw new Error('Missing context: chat, model, or document path');
	}
	// Filter to TokenReplacementValue type explicitly
	const valuesToSend: TokenReplacementValue[] = payload.map((p) => ({
		token: String(p.token),
		value: String(p.value ?? '')
	}));
	await putTokenReplacementValues(cId, mId, valuesToSend);
}

// Trigger generation of the replacement document via app hook
async function handleGenerate() {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	const dPath = $selectedTokenizedDocPath as string | null;
	if (!cId || !mId || !dPath) {
		toast.error($i18n.t('Missing context: chat, model, or document path'));
		return;
	}
	let dismiss: (() => void) | undefined;
	try {
		// TODO: call the REST api via a new function in `src/lib/apis/private-ai/sidekicks/token-replacer/index.ts`
		dismiss = toast.success($i18n.t('TODO: Generation requested'));
	} catch (e) {
		console.error(e);
		toast.error($i18n.t('Failed to start generation'));
	} finally {
		try {
			dismiss && dismiss();
		} catch {
		}
	}
}

function onGenerateClick() {
	if (draftCount > 0) {
		showGenerateConfirm = true;
	} else {
		void handleGenerate();
	}
}

async function confirmSaveThenGenerate() {
	await handleSubmit();
	// Only proceed to generate if submission didn't error out
	if (!submitError) {
		await handleGenerate();
	}
}

function proceedGenerateWithoutSaving() {
	void handleGenerate();
}

// Derived filtered tokens with filter modes
type TokenFilter = 'all' | 'needing' | 'with' | 'drafts';
let tokenFilter: TokenFilter = 'needing';
$: query = searchQuery.trim().toLowerCase();
$: filteredTokens = tokens
	.map((t) => DOMPurify.sanitize(t, {USE_PROFILES: {html: false}}))
	.filter((t) => {
		const hasSaved = typeof savedValues[t] === 'string' && savedValues[t].trim().length > 0;
		const v = (values[t] ?? '').trim();
		const s = (savedValues[t] ?? '').trim();
		const isDraft = v !== s;
		if (tokenFilter === 'needing') return !hasSaved;
		if (tokenFilter === 'with') return hasSaved;
		if (tokenFilter === 'drafts') return isDraft;
		return true;
	})
	.filter((t) => (query ? t.toLowerCase().includes(query) : true));

function updateValue(token: string, value: string) {
	suppressDraftPersistence = false; // user changed something; allow drafts to persist again
	values = { ...values, [token]: value };
	persistDraftDebounced();
}

function handleInput(token: string, id?: string) {
	return (e: Event) => {
		const target = e.currentTarget as HTMLInputElement;
		updateValue(token, target.value);
		// If this token is currently selected in preview, update highlight state when it flips.
		if (isPreviewOpen && id && lastPreviewSelection?.id === id) {
			const v = (target.value ?? '').trim();
			const s = (savedValues[token] ?? '').trim();
			const newState: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
			if (lastPreviewSelection.state !== newState) {
				appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
				lastPreviewSelection.state = newState;
			}
		}
	};
}


const iconBtnBase = 'inline-flex items-center justify-center h-7 w-7 mt-0.5 rounded border';
const iconBtnNeutral = 'border-gray-300 text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800';
const iconBtnActive = 'border-amber-300 bg-amber-100 text-amber-700 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-300';

function handleRemoveTokenClick(token: string, id?: string) {
	// Clicking the remove button clears the value (marks as removed)
	updateValue(token, '');
	if (isPreviewOpen && id && lastPreviewSelection?.id === id) {
		const v = ''.trim();
		const s = (savedValues[token] ?? '').trim();
		const newState: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
		if (lastPreviewSelection.state !== newState) {
			appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
			lastPreviewSelection.state = newState;
		}
	}
}

function getInputId(token: string): string {
	return `input-${token.replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase().slice(0, 64)}`;
}

function getContextIds() {
	const cId = $chatId as string | null;
	const mId = $currentSelectedModelId as string | null;
	const tId = $selectedTokenizedDocPath as string | null;
	return { cId, mId, tId };
}

function mergeDraftValues(base: ReplacementValues, draftVals: Record<string, string> | undefined, allowedTokens: string[]): ReplacementValues {
	if (!draftVals) return base;
	const allowed = new Set(allowedTokens);
	const filtered: ReplacementValues = {};
	for (const [k, v] of Object.entries(draftVals)) {
		if (allowed.has(k)) {
			filtered[k] = v ?? '';
		}
	}
	// Important: API (base) takes precedence over drafts on conflict.
	// Draft values are used only for tokens that are not provided by the API.
	return { ...filtered, ...base };
}

let saveTimeout: ReturnType<typeof setTimeout> | null = null;
const DEBOUNCE_MS = 250;

async function persistDraftNow() {
	if (suppressDraftPersistence) return;
 const { cId, mId, tId } = getContextIds();
	if (!cId || !mId || !tId) return;
	// If no non-empty values, clear any existing draft instead of saving empties
	const hasAny = tokens.some((t) => (values[t]?.trim()?.length ?? 0) > 0);
	if (!hasAny) {
		await clearTokenReplacerDraft(cId, mId, tId);
		return;
	}
	const draft: TokenReplacerDraft = { values, updatedAt: Date.now() };
	await saveTokenReplacerDraft(cId, mId, tId, draft);
}

function persistDraftDebounced() {
	if (saveTimeout) clearTimeout(saveTimeout);
	saveTimeout = setTimeout(() => {
		persistDraftNow();
	}, DEBOUNCE_MS);
}

async function handleSubmit() {
	submitError = null;
	submitSuccess = false;
	isSubmitting = true;

	try {
		// Build payload from ALL tokens, not only filtered ones
		const payload = tokens.map((t) => ({ token: t, value: values[t] ?? '' }));
		await submitReplacementValues(payload);
		// On success, server-saved values now match local edits
		savedValues = { ...values };
		submitSuccess = true;
		suppressDraftPersistence = true; // prevent re-saving this session unless user edits again
		// If a token is currently selected in preview, reload preview and reselect/scroll to it when loaded
		if (isPreviewOpen && lastPreviewSelection) {
			appHooks.callHook('private-ai.token-replacer.preview.reload', {
				id: lastPreviewSelection.id,
				state: 'saved'
			});
			lastPreviewSelection.state = 'saved';
		}
		// Clear the saved draft on successful submit so future sessions start fresh
  const { cId, mId, tId } = getContextIds();
		if (cId && mId && tId) {
			await clearTokenReplacerDraft(cId, mId, tId);
		}
		toast.success($i18n.t('🎉 Replacement values submitted!'));
	} catch (e) {
		console.error(e);
		submitError = $i18n.t('Failed to submit replacement values.');
		toast.error(submitError);
	} finally {
		isSubmitting = false;
	}
}

onMount(async () => {
	// Track overlay open/close to show preview buttons only when preview is open
	try {
		const overlayHandler = (params: { action: 'open' | 'close' | 'update'; title?: string; component?: any }) => {
			if (params.action === 'open') {
				isPreviewOpen = params.component === TokenizedDocPreview;
			} else if (params.action === 'close') {
				isPreviewOpen = false;
			}
		};
		appHooks.hook('chat.overlay', overlayHandler);
		removeOverlayHook = () => {
			try {
				appHooks.removeHook('chat.overlay', overlayHandler);
			} catch {
			}
		};
	} catch {
	}
	// Also respond to a direct preview-closed notification from the preview component
	try {
		const previewClosedHandler = () => {
			isPreviewOpen = false;
			isTokenOverlayOpen = false;
		};
		appHooks.hook('private-ai.token-replacer.preview.closed', previewClosedHandler);
		removePreviewClosedHook = () => {
			try {
				appHooks.removeHook('private-ai.token-replacer.preview.closed', previewClosedHandler);
			} catch {
			}
		};
	} catch {
	}
	// Ensure the list of tokenized files is loaded so the selected document summary can resolve on refresh
	try {
		await ensureFilesFetched();
	} catch {
	}
	// Measure header height and watch for changes
	updateHeaderHeight();
	try {
		headerRO = new ResizeObserver(() => updateHeaderHeight());
		if (headerEl) headerRO.observe(headerEl);
	} catch {
	}
	headerResizeHandler = () => updateHeaderHeight();
	window.addEventListener('resize', headerResizeHandler);

	// Track visibility of the SelectedDocumentSummary as the page scrolls/resizes
	summaryScrollHandler = () => scheduleSummaryVisibilityCheck();
	try {
		// passive listeners for performance
		window.addEventListener('scroll', summaryScrollHandler as EventListener, { passive: true } as any);
		window.addEventListener('resize', summaryScrollHandler as EventListener);
	} catch {}
	computeSummaryVisibility();
	// Initialize IntersectionObserver once DOM is ready and the header is measured
	setupSummaryObserver();

	isLoading = true;
	loadError = null;
	try {
		const { tokens: tk, values: vals, occurrences: occ } = await loadTokensAndValues();
		tokens = tk;
		// Track server-saved values separately from editable values
		savedValues = vals;
		tokenOccurrences = occ ?? {};
		let merged = vals;
  const { cId, mId, tId } = getContextIds();
		if (cId && mId && tId) {
			const draft = await loadTokenReplacerDraft(cId, mId, tId);
			if (draft?.values) {
				merged = mergeDraftValues(vals, draft.values, tk);
			}
		}
		values = merged;
	} catch (e) {
		console.error(e);
		loadError = $i18n.t('Failed to load tokens.');
	} finally {
		isLoading = false;
	}
});

onDestroy(() => {
	if (saveTimeout) {
		clearTimeout(saveTimeout);
		saveTimeout = null;
	}
	// Cleanup header observers/listeners
	try {
		headerRO?.disconnect();
	} catch {
	}
	headerRO = null;
	if (headerResizeHandler) {
		window.removeEventListener('resize', headerResizeHandler);
		headerResizeHandler = null;
	}
	// Remove overlay hook listener
	try {
		removeOverlayHook && removeOverlayHook();
	} catch {
	}
	// Cleanup summary visibility listeners
	try {
		if (summaryScrollHandler) {
			window.removeEventListener('scroll', summaryScrollHandler as EventListener);
			window.removeEventListener('resize', summaryScrollHandler as EventListener);
			summaryScrollHandler = null;
		}
		try { cancelAnimationFrame(summaryRaf); } catch {}
		try { summaryIO?.disconnect(); } catch {}
		summaryIO = null;
	} catch {}
	// Persist the latest state when the component is destroyed (e.g., panel closes)
	void persistDraftNow();
});
</script>

<div class="flex flex-col w-full items-stretch justify-start">
	<!-- Header -->
	<div
		bind:this={headerEl}
		class="px-4 py-2 sticky top-0 bg-white dark:bg-gray-900 z-20">
 	<div class="flex items-center justify-between">
			<div class="hidden sm:flex items-center gap-1 text-[11px] text-gray-700 dark:text-gray-300">
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 border border-green-300/70 dark:border-green-700/60 text-green-800 dark:text-green-300">
					{$i18n.t('Complete')}: {providedCount}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 border border-blue-300/70 dark:border-blue-700/60 text-blue-800 dark:text-blue-300">
					{$i18n.t('Drafts')}: {draftCount}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-300 dark:bg-amber-600/30 border border-amber-300/70 dark:border-amber-700/60 text-amber-800 dark:text-amber-300">
					{$i18n.t('Incomplete')}: {emptyCount}
				</span>
				<span
					class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800/50 border border-gray-300/70 dark:border-gray-700/60 text-gray-800 dark:text-gray-200">
					{$i18n.t('Total')}: {totalTokens}
				</span>
			</div>
			{#if !isSummaryVisible}
				<div class="ml-auto">
					<Tooltip content={$i18n.t('Preview Document')} placement="left">
						<button
							type="button"
							class="inline-flex items-center justify-center h-6 w-6 rounded border border-gray-300 dark:border-gray-700 text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
							on:click={openPreviewPanel}
							aria-label={$i18n.t('Preview')}
							title={$i18n.t('Preview')}
						>
							<Eye class="h-4 w-4" />
						</button>
					</Tooltip>
				</div>
			{/if}
		</div>
		<div class="relative mt-1 w-full h-2.5 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden" role="progressbar"
				 aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPercent}
				 aria-label={$i18n.t('Completion progress')}>
			<div class="h-full bg-green-500 dark:bg-green-400 transition-[width] duration-300"
					 style={`width: ${progressPercent}%`}></div>
			<!-- Centered progress label -->
			<span class="pointer-events-none absolute inset-0 pl-6 flex items-center text-[8px] leading-none text-gray-700 dark:text-gray-200 select-none">
				{progressPercent}% {$i18n.t('Complete')}
			</span>
		</div>
	</div>

	<!-- Content area container (page scroll) -->
	<div class="relative">
		<!-- Selected document summary (non-sticky) -->
		<div class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900" bind:this={summaryEl}>
			<SelectedDocumentSummary on:preview={openPreviewPanel} />
		</div>

		<!-- Overlay scope wrapper: covers from below SelectedDocumentSummary -->
		<div class="relative">
			<!-- Search and filtering (sticky within scroll container) -->

			<!-- Content area -->
			{#if isTokenOverlayOpen && overlayToken}
				<!-- Token occurrences overlay (scoped within EditValuesView search+content area) -->
				<div
					class="sticky z-30 bg-gray-50 dark:bg-gray-900 border-l border-r border-gray-200 dark:border-gray-800 overflow-y-auto"
					style={`top: ${headerHeight}px; height: calc(100vh - ${headerHeight}px); min-height: calc(100vh - ${headerHeight}px);`}>
					<div class="p-3 sm:p-4">
						<div class=" text-lg font-medium self-center font-primary">{$i18n.t('Token Occurrences')}</div>
						<div class="flex items-start justify-between gap-3 mb-3">
							<div class="space-y-1">
								<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Token')}</div>
								<div
									class="text-sm font-semibold text-gray-800 dark:text-gray-100 break-words whitespace-pre-wrap">{overlayToken}</div>
							</div>
							<button type="button"
											class="inline-flex flex-shrink-0 items-center justify-center h-8 w-8 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
											aria-label={$i18n.t('Close')} on:click={closeTokenOverlay}>
								<span aria-hidden="true">✕</span>
							</button>
						</div>

						<!-- Synced input -->
						<div class="space-y-2 mb-3">
							<label for="overlay-input"
										 class="block text-xs text-gray-600 dark:text-gray-300">{$i18n.t('Replacement value')}</label>
							<input id="overlay-input"
    						 class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 ${overlayState === 'draft' ? 'ring-1 ring-blue-400 border-blue-400 dark:ring-blue-500 dark:border-blue-500' : ''}`}
										 type="text" placeholder={$i18n.t('Delete from document')}
										 value={overlayToken ? (values[overlayToken] ?? '') : ''} on:focus={onOverlayFocus}
										 on:input={onOverlayInput} autocomplete="off" />
						</div>

						<div class="text-xs text-gray-600 dark:text-gray-300 mb-2">{$i18n.t('Occurrences')}:
									{overlayOccurrences.length}</div>

						<!-- Navigation -->
						<div class="flex flex-wrap items-center gap-2 mb-3">
							<button type="button"
											class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 text-xs text-gray-700 dark:text-gray-300 disabled:opacity-50"
											on:click={gotoPrevOccurrence} disabled={overlayOccurrences.length <= 1}>
								{$i18n.t('Prev')}
							</button>
							<button type="button"
											class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 text-xs text-gray-700 dark:text-gray-300 disabled:opacity-50"
											on:click={gotoNextOccurrence} disabled={overlayOccurrences.length <= 1}>
								{$i18n.t('Next')}
							</button>
							<div class="flex flex-wrap items-center gap-1">
								{#each overlayOccurrences as occId, idx}
									<button type="button"
													class={`px-2 py-1 rounded border text-xs ${idx === overlayCurrentIdx ? 'bg-gray-200 dark:bg-gray-800 border-gray-400 dark:border-gray-600 text-gray-900 dark:text-gray-100' : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
													on:click={() => selectOverlayOccurrence(idx)}>
										{idx + 1}
									</button>
								{/each}
							</div>
						</div>
					</div>
				</div>
			{/if}

			<div
				class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 sticky bg-white dark:bg-gray-900 z-10 shadow"
				style={`top: ${headerHeight}px`}>
				<div class="flex items-center justify-between gap-2 mb-1">
 				<div class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300">
						<AdjustmentsHorizontal className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
						<select
							class="px-2 pr-6 py-1 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs text-gray-900 dark:text-gray-100"
							bind:value={tokenFilter}
							aria-label={$i18n.t('Token filter')}
						>
       <option value="all">{$i18n.t('All tokens')}</option>
							<option value="needing">{$i18n.t('Tokens needing a value')}</option>
							<option value="with">{$i18n.t('Tokens with values')}</option>
							<option value="drafts">{$i18n.t('Drafts')}</option>
						</select>
					</div>
					<button
						class="px-2 py-1 rounded bg-gray-700 text-xs text-white hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-gray-700 dark:hover:bg-gray-800 text-nowrap"
						disabled={isLoading || isSubmitting || tokens.length === 0 || savedCount === 0}
						on:click={onGenerateClick}
					>
						{$i18n.t('Generate Document')}
					</button>
				</div>
				<input
					id="token-search"
					class="w-full px-3 py-2 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
					type="text"
					bind:value={searchQuery}
					placeholder={$i18n.t('Type to filter tokens...')}
					autocomplete="off"
					spellcheck={false}
				/>
			</div>


			<div class="relative px-4 py-2 pb-24 space-y-3">
				{#if isLoading}
					<div class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300" aria-live="polite">
						<Spinner />{$i18n.t('Loading tokens...')}</div>
				{:else if loadError}
					<div class="text-sm text-red-600 dark:text-red-400" role="alert">{loadError}</div>
				{:else}
					{#if filteredTokens.length === 0}
						<div class="text-sm text-gray-600 dark:text-gray-300">
       {#if tokenFilter === 'needing'}
								{$i18n.t('No tokens need a value for the current search.')}
							{:else if tokenFilter === 'with'}
								{$i18n.t('No tokens have a value for the current search.')}
							{:else if tokenFilter === 'drafts'}
								{$i18n.t('No tokens have drafts for the current search.')}
							{:else}
								{$i18n.t('No tokens match your search.')}
							{/if}
						</div>
					{:else}
						<div class="space-y-4">
							{#each filteredTokens as token, i}
								<div class="grid grid-cols-1 lg:grid-cols-3 gap-2 lg:gap-4 items-start">
 								<div
 									class="lg:col-span-1 text-[11px] text-gray-800 dark:text-gray-200 select-text">
 									<div class="flex items-start gap-1">
 										<Tooltip content={token} placement="top" className="inline-flex max-w-full">
 											<span class="token-text">{token}</span>
 										</Tooltip>
 									</div>
 								</div>
									<div class="lg:col-span-2">
										{#key token}
											<div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
									<div class="relative w-full">
										<input
											id={getInputId(token)}
     						class={`w-full px-3 py-2 rounded border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 border-gray-300 dark:border-gray-700 ${((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? 'ring-1 ring-blue-400 border-blue-400 dark:ring-blue-500 dark:border-blue-500' : ''}`}
											type="text"
											placeholder={$i18n.t('Delete from document')}
											aria-label={$i18n.t('Replacement value')}
											aria-describedby={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? `${getInputId(token)}-draft` : undefined}
											value={values[token] ?? ''}
											on:focus={() => onPreviewTokenClick(i, token)}
											on:input={handleInput(token, getFirstOccurrenceId(token, i))}
											autocomplete="off"
										/>
										{#if (values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()}
     						<div id={`${getInputId(token)}-draft`}
     							class="pointer-events-none absolute -top-2 -right-2 text-[10px] inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
     							<span class="inline-block px-1 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700 shadow-sm">{$i18n.t('Draft')}</span>
     							<span class="sr-only">{$i18n.t('Value differs from the last saved value and is not yet saved.')}</span>
     						</div>
										{/if}
									</div>
									{#if (values[token] ?? '') !== ''}
										<Tooltip content={$i18n.t('Remove from document')} placement="top">
											<button
												class={`${iconBtnBase} ${iconBtnNeutral} flex-shrink-0`}
												type="button"
												on:click={() => handleRemoveTokenClick(token, getFirstOccurrenceId(token, i))}
												aria-label={$i18n.t('Remove from document')}
												title={$i18n.t('Remove from document')}>
												<Minus className="h-4 w-4" />
											</button>
										</Tooltip>
									{/if}
 								{#if isPreviewOpen && (tokenOccurrences[token]?.length ?? 0) > 1}
 									<Tooltip content={$i18n.t('List all occurrences')} placement="top">
 										<button
 											type="button"
 											class={`${iconBtnBase} ${iconBtnNeutral} flex-shrink-0`}
 											on:click={() => openTokenOverlay(i, token)}
 											aria-label={$i18n.t('List all occurrences')}
 											title={$i18n.t('List all occurrences')}>
 											<ListBullet className="h-4 w-4" />
 										</button>
 									</Tooltip>
 								{/if}
								</div>
											</div>
										{/key}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>

	<!-- Submit bar (sticky bottom) -->
	<div
		class="px-4 py-3 border-t border-gray-200 dark:border-gray-800 sticky bottom-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-20">
		<div class="flex items-center justify-between gap-3">
			<div class="text-xs text-gray-600 dark:text-gray-400">
				{#if isSubmitting}
					{$i18n.t('Submitting...')}
				{:else if submitSuccess}
          <span class="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
            {$i18n.t('🎉 Replacement values submitted!')}
          </span>
				{:else}
					{$i18n.t('Provide replacement values and submit when ready.')}
				{/if}
			</div>
			<div class="flex items-center gap-2">
				<button
					class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600 text-nowrap"
					disabled={isLoading || isSubmitting || tokens.length === 0 || draftCount === 0}
					on:click={() => (showConfirm = true)}
				>
					{$i18n.t('Submit')}
				</button>
			</div>
		</div>
		{#if submitError}
			<div class="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">{submitError}</div>
		{/if}
	</div>
</div>


<ConfirmDialog
	bind:show={showConfirm}
	title={$i18n.t('Confirm submission')}
	message={confirmMessage}
	cancelLabel={$i18n.t('Cancel')}
	confirmLabel={$i18n.t('Submit All')}
	onConfirm={handleSubmit}
/>

<ConfirmDialog
	bind:show={showGenerateConfirm}
	title={$i18n.t('Unsaved drafts detected')}
	message={`${$i18n.t('You have')} <b>${draftCount}</b> ${$i18n.t('unsaved draft value(s).')}<br><br>${$i18n.t('Would you like to save them before generating the document?')}`}
	cancelLabel={$i18n.t('No, Generate')}
	confirmLabel={$i18n.t('Save and Generate')}
	on:confirm={confirmSaveThenGenerate}
	on:cancel={proceedGenerateWithoutSaving}
/>


<style>
	.token-text {
		display: -webkit-box;
		-webkit-line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
		white-space: pre-wrap;
		word-break: break-word;
	}
</style>
