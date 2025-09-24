<script lang="ts">
import { getContext, onDestroy, onMount, tick } from 'svelte';
import { toast } from 'svelte-sonner';
import { ensureFilesFetched, selectedTokenizedDoc, selectedTokenizedDocPath } from '../stores';
import TokenizedDocPreview from '../components/TokenizedDocPreview.svelte';
import { appHooks } from '$lib/utils/hooks';
import SelectedDocumentSummary from '../components/SelectedDocumentSummary.svelte';
import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
import { chatId, currentSelectedModelId } from '$lib/stores';
import {
	type GenerateDocumentResult,
	generateTokenReplacerDocument,
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
import Tooltip from '$lib/components/common/Tooltip.svelte';
import DOMPurify from 'dompurify';
import ListBullet from '$lib/components/icons/ListBullet.svelte';
import Minus from '$lib/components/icons/Minus.svelte';
import ClearableInput from '$lib/components/common/ClearableInput.svelte';
import ExpandableTextarea from '$lib/components/common/ExpandableTextarea.svelte';

const i18n = getContext('i18n');

function openPreviewPanel() {
	const file = $selectedTokenizedDoc;
	if (file) {
		appHooks.callHook('chat.overlay', {
			action: 'open',
			title: `👀 ${$i18n.t('Preview')} `,
			component: TokenizedDocPreview,
			props: { file, previewType: 'docx' }
		});
		isPreviewOpen = true;
		// After opening, inform the preview of which tokens currently have drafts/saved/none
		try {
			emitStatusIds();
			emitValuesById();
		} catch {
		}
	}
}

function closePreviewPanel() {
	appHooks.callHook('chat.overlay', { action: 'close' });
}

function emitStatusIds() {
	try {
		const draftIds: string[] = [];
		const savedIds: string[] = [];
		const noneIds: string[] = [];
		for (let i = 0; i < tokens.length; i++) {
			const t = tokens[i];
			const v = (values[t] ?? '').trim();
			const s = (savedValues[t] ?? '').trim();
			const ids = (tokenOccurrences[t] ?? []).length > 0 ? tokenOccurrences[t] : [`nh-token-${i + 1}`];
			if (!v && !s) {
				noneIds.push(...ids);
			} else if (v === s && s) {
				savedIds.push(...ids);
			} else if (v && v !== s) {
				draftIds.push(...ids);
			}
		}
		if (draftIds.length > 0) appHooks.callHook('private-ai.token-replacer.preview.set-draft-ids', { ids: draftIds });
		appHooks.callHook('private-ai.token-replacer.preview.set-status-ids', { draftIds, savedIds, noneIds });
	} catch {
	}
}

function emitValuesById() {
	try {
		const byId: Record<string, { draft?: string; saved?: string }> = {};
		for (let i = 0; i < tokens.length; i++) {
			const t = tokens[i];
			const v = (values[t] ?? '').trim();
			const s = (savedValues[t] ?? '').trim();
			const ids = (tokenOccurrences[t] ?? []).length > 0 ? tokenOccurrences[t] : [`nh-token-${i + 1}`];
			for (const id of ids) {
				const entry: { draft?: string; saved?: string } = {};
				if (s) entry.saved = s;
				if (v && v !== s) entry.draft = v; else if (v && !s) entry.draft = v;
				byId[id] = entry;
			}
		}
		appHooks.callHook('private-ai.token-replacer.preview.set-values', { byId });
	} catch {
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
let showFinalGenerateConfirm = false;

// Track if the TokenizedDocPreview overlay is open
let isPreviewOpen = false;
let removeOverlayHook: (() => void) | null = null;
let removePreviewClosedHook: (() => void) | null = null;
let removePreviewReloadedHook: (() => void) | null = null;
let removePreviewTokenClickedHook: (() => void) | null = null;
// Track the last previewed token selection to update highlight state on edits
let lastPreviewSelection: { id: string; state: 'draft' | 'saved' } | null = null;
let lastPreviewToken: string | null = null;

// Local overlay for token occurrences
let isTokenOverlayOpen = false;
let overlayToken: string | null = null;
let overlayTokenIndex = -1; // index in filteredTokens when opened
let overlayOccurrences: string[] = [];
let overlayCurrentIdx = 0;

// Ref to the overlay container to measure and auto-pin into sticky position
let overlayContainerEl: HTMLDivElement | null = null;
// Sticky search/filter bar element (below header) to account for its height when scrolling inputs
let filterBarEl: HTMLDivElement | null = null;

function getScrollableParent(el: HTMLElement | null): HTMLElement | Window {
	if (!el) return window;
	let parent: HTMLElement | null = el.parentElement;
	while (parent) {
		const style = getComputedStyle(parent);
		const overflowY = style.overflowY;
		const canScroll = (overflowY === 'auto' || overflowY === 'scroll') && parent.scrollHeight > parent.clientHeight;
		if (canScroll && parent !== el) {
			return parent;
		}
		parent = parent.parentElement;
	}
 return window;
}

function scrollTokenInputIntoView(inputEl: HTMLElement) {
	// Scroll so the input appears just below sticky header and filter bar,
	// even when it's currently above the viewport or partially hidden under sticky UI.
	try {
		const stickyOffset = headerHeight + (filterBarEl?.offsetHeight ?? 0) + 8; // small padding
		const scrollParent = getScrollableParent(inputEl);
		if (scrollParent === window) {
			const rect = inputEl.getBoundingClientRect();
			const absoluteTargetTop = window.pageYOffset + rect.top - stickyOffset;
			window.scrollTo({ top: Math.max(absoluteTargetTop, 0), behavior: 'smooth' });
		} else {
			// Internal scroll container: compute the element's position relative to the container and adjust scrollTop
			const parent = scrollParent as HTMLElement;
			const parentRect = parent.getBoundingClientRect();
			const elRect = inputEl.getBoundingClientRect();
			const relativeTop = elRect.top - parentRect.top; // distance from parent's visible top to the element
			const targetScrollTop = parent.scrollTop + relativeTop - stickyOffset;
			parent.scrollTo({ top: Math.max(targetScrollTop, 0), behavior: 'smooth' });
		}
	} catch {
		// no-op
	}
}

async function pinOverlayIntoSticky() {
	await tick();
	if (!overlayContainerEl) return;
	try {
		const rect = overlayContainerEl.getBoundingClientRect();
		const targetTop = Math.max(0, headerHeight);
		const delta = rect.top - targetTop;
		if (delta > 1) {
			const scrollParent = getScrollableParent(overlayContainerEl);
			if (scrollParent === window) {
				window.scrollBy({ top: delta, behavior: 'auto' });
			} else {
				(scrollParent as HTMLElement).scrollBy({ top: delta, behavior: 'auto' as ScrollBehavior });
			}
		}
	} catch {
		// no-op
	}
}

$: overlayState = overlayToken ? computeTokenState(overlayToken) : 'saved';

function onOverlayFocus() {
	selectOverlayOccurrence(overlayCurrentIdx);
}

function onOverlayInput(e: Event | CustomEvent<{ value: string }>) {
	if (!overlayToken) return;
	const v = (e as CustomEvent<{
		value: string
	}>).detail?.value ?? (e.target as HTMLTextAreaElement | null)?.value ?? '';
	updateValue(overlayToken, v);
	if (isPreviewOpen) {
		const id = overlayOccurrences[overlayCurrentIdx];
		const newState = computeTokenState(overlayToken, v);
		appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
		lastPreviewSelection = { id, state: newState };
		lastPreviewToken = overlayToken;
		// Update unselected state coloring and replacement text
		emitStatusIds();
		emitValuesById();
	}
}

function computeTokenState(token: string, valueOverride?: string): 'draft' | 'saved' {
	const v = ((valueOverride ?? values[token]) ?? '').trim();
	const s = (savedValues[token] ?? '').trim();
	return v === s ? 'saved' : 'draft';
}

function focusOverlayOccurrenceButton() {
	try {
		if (!overlayContainerEl) return;
		const btn = overlayContainerEl.querySelector(
			`button[data-occurrence-index="${overlayCurrentIdx}"]`
		) as HTMLButtonElement | null;
		if (btn) {
			// Focus the selected button and ensure it's visible in the overlay scroll area
			(btn as any).focus?.({ preventScroll: true });
			btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
		}
	} catch {
	}
}

function selectOverlayOccurrence(idx: number) {
	if (!overlayToken || !isPreviewOpen) return;
	overlayCurrentIdx = Math.max(0, Math.min(idx, overlayOccurrences.length - 1));
	const id = overlayOccurrences[overlayCurrentIdx];
	const state = computeTokenState(overlayToken);
	appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state });
	lastPreviewSelection = { id, state };
	lastPreviewToken = overlayToken;
	// After DOM updates, focus and scroll the selected occurrence button into view
	setTimeout(() => focusOverlayOccurrenceButton(), 0);
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
	// Ensure the overlay immediately pins under the sticky header so its internal scroller can reach the end
	void pinOverlayIntoSticky();
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

// Sticky submit bar (bottom) height helper to ensure overlay scroll can reach the end
let submitBarEl: HTMLDivElement | null = null;
let submitBarHeight = 0;
let submitRO: ResizeObserver | null = null;
let submitResizeHandler: (() => void) | null = null;

// Track the visibility of SelectedDocumentSummary so we can show a secondary Preview button
let summaryEl: HTMLDivElement | null = null;
let isSummaryVisible = true;
let summaryRaf = 0;
let summaryScrollHandler: (() => void) | null = null;
let summaryIO: IntersectionObserver | null = null;

function setupSummaryObserver() {
	try {
		summaryIO?.disconnect();
	} catch {
	}
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
	} catch {
	}
}

function updateHeaderHeight() {
	headerHeight = headerEl?.offsetHeight ?? 0;
	// Recompute summary visibility when the header size changes
	scheduleSummaryVisibilityCheck();
	// Re-init intersection observer to respect new headerHeight offset
	setupSummaryObserver();
}

function updateSubmitBarHeight() {
	submitBarHeight = submitBarEl?.offsetHeight ?? 0;
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
	try {
		cancelAnimationFrame(summaryRaf);
	} catch {
	}
	summaryRaf = requestAnimationFrame(computeSummaryVisibility);
}

// Derived counts and stats
$: totalTokens = tokens.length;
// "Complete" should reflect saved values, not be reduced during edits
$: providedCount = tokens.reduce((acc, t) => (((savedValues[t] ?? '').trim().length > 0) ? acc + 1 : acc), 0);
$: savedCount = tokens.reduce((acc, t) => (((savedValues[t] ?? '').trim().length > 0) ? acc + 1 : acc), 0);
$: emptyCount = tokens.reduce((acc, t) => (((values[t] ?? '').trim().length === 0) ? acc + 1 : acc), 0);
$: draftCount = tokens.reduce((acc, t) => ((values[t] ?? '').trim() !== (savedValues[t] ?? '').trim() ? acc + 1 : acc), 0);
$: progressPercent = totalTokens > 0 ? Math.round((providedCount / totalTokens) * 100) : 0;

// Build confirmation message (markdown supported by ConfirmDialog)
$: currentProvidedCount = tokens.reduce((acc, t) => (((values[t] ?? '').trim().length > 0) ? acc + 1 : acc), 0);
$: confirmMessage = `${$i18n.t('You are about to submit all token/value pairs for the selected document.')}<br><br>` +
	`${$i18n.t('Tokens total')}: <b>${totalTokens}</b><br>` +
	`${$i18n.t('Replacement values provided')}: <b>${currentProvidedCount}</b><br>` +
	`${$i18n.t('Replacement values empty')}: <b>${emptyCount}</b><br><br>` +
	`${$i18n.t('All tokens will be submitted, including those not currently visible due to search filters.')}<br><br>` +
	`${$i18n.t('Do you want to continue?')}`;

// Load tokens and values from API
async function loadTokensAndValues(): Promise<{
	tokens: Token[];
	values: ReplacementValues;
	occurrences: Record<string, string[]>
}> {
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

// Small delay + retry wrapper to mitigate race conditions after new chat creation
const TOKENS_LOAD_MAX_RETRIES = 5;
const TOKENS_LOAD_INITIAL_DELAY_MS = 200;

function sleep(ms: number) {
	return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

async function loadTokensAndValuesWithRetry() {
	let lastError: any = null;
	for (let attempt = 0; attempt < TOKENS_LOAD_MAX_RETRIES; attempt++) {
		if (attempt > 0) {
			const delay = TOKENS_LOAD_INITIAL_DELAY_MS * Math.pow(2, attempt - 1);
			await sleep(delay);
		}
		try {
			const result = await loadTokensAndValues();
			// If tokens are present, return immediately. Otherwise, retry until max attempts.
			if (Array.isArray(result.tokens) && result.tokens.length > 0) {
				return result;
			}
			lastError = lastError ?? new Error('No tokens available yet');
		} catch (e) {
			lastError = e;
			// continue to retry unless this is the last attempt
		}
	}
	// Final attempt: do one more direct call to surface any concrete error message
	try {
		return await loadTokensAndValues();
	} catch (e) {
		throw (e ?? lastError ?? new Error('Failed to load tokens'));
	}
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
	let loadingToastId: string | number | undefined;
	try {
		loadingToastId = toast.loading($i18n.t('Generating document...'));
		closePreviewPanel();
		// TODO: This should really happen from within the pipeline so we dont rely on the lifecycle of this component.
		const result = (await generateTokenReplacerDocument(cId, mId)) as GenerateDocumentResult;
		if (!result || result.didReplace === false) {
			toast.error($i18n.t('No tokens were replaced.'));
			return;
		}
		toast.success($i18n.t('Document generated successfully.'));
		// Send an assistant-only directive message to the chat including the full result payload
		const directive = {
			_kind: 'openwebui.directive',
			version: 1,
			name: 'token_replacer.generate.result',
			assistant_only: true,
			payload: { result }
		};
		try {
			await appHooks.callHook('chat.submit', { prompt: JSON.stringify(directive) });
		} catch {
			// ignore hook issues; generation already succeeded
		}
	} catch (e) {
		console.error(e);
		toast.error($i18n.t('Failed to generate document.'));
	} finally {
		try {
			if (loadingToastId !== undefined) toast.dismiss(loadingToastId);
		} catch {
		}
	}
}

function onGenerateClick() {
	if (draftCount > 0) {
		showGenerateConfirm = true;
	} else {
		// Always ask for a final confirmation before generating
		showFinalGenerateConfirm = true;
	}
}

async function confirmSaveThenGenerate() {
	await handleSubmit();
	// Only proceed to final confirmation if the submission didn't error out
	if (!submitError) {
		showFinalGenerateConfirm = true;
	}
}

function proceedGenerateWithoutSaving() {
	showFinalGenerateConfirm = true;
}

// Derived filtered tokens with filter modes
type TokenFilter = 'all' | 'needing' | 'with' | 'drafts';
let tokenFilter: TokenFilter = 'all';
$: query = searchQuery.trim().toLowerCase();
$: filteredTokens = tokens
	.map((t) => DOMPurify.sanitize(t, { USE_PROFILES: { html: false } }))
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
	return (e: Event | CustomEvent<{ value: string }>) => {
		const vRaw = (e as CustomEvent<{
			value: string
		}>).detail?.value ?? (e.target as HTMLTextAreaElement | null)?.value ?? '';
		updateValue(token, vRaw);
		// If this token is currently selected in preview, update highlight state when it flips.
		if (isPreviewOpen && id && lastPreviewSelection?.id === id) {
			const v = (vRaw ?? '').trim();
			const s = (savedValues[token] ?? '').trim();
			const newState: 'draft' | 'saved' = v === s ? 'saved' : 'draft';
			if (lastPreviewSelection.state !== newState) {
				appHooks.callHook('private-ai.token-replacer.preview.select-token', { id, state: newState });
				lastPreviewSelection.state = newState;
			}
		}
		// Always sync values and statuses to the preview when open so +Values text updates live
		if (isPreviewOpen) {
			emitStatusIds();
			emitValuesById();
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
	// Also reflect cleared value in the preview's +Values mode immediately
	if (isPreviewOpen) {
		emitStatusIds();
		emitValuesById();
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
		// If a token is currently selected in preview, reload the preview and reselect/scroll to it when loaded
		if (isPreviewOpen && lastPreviewSelection) {
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
	// Also, respond to a direct preview-closed notification from the preview component
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
	// Listen for preview reload to re-sync status classes and replacement values
	try {
		const previewReloadedHandler = () => {
			try {
				emitStatusIds();
				emitValuesById();
			} catch {
			}
		};
		appHooks.hook('private-ai.token-replacer.preview.reloaded', previewReloadedHandler);
		removePreviewReloadedHook = () => {
			try {
				appHooks.removeHook('private-ai.token-replacer.preview.reloaded', previewReloadedHandler);
			} catch {
			}
		};
	} catch {
	}

	// Listen for clicks in the preview to focus corresponding input and handle occurrences overlay
	try {
		const previewTokenClickedHandler = (params: { id: string }) => {
			if (!params?.id) return;
			const clickedId = params.id;
			// Find token and occurrence index by id
			let foundToken: string | null = null;
			let occIdx = 0;
			for (const [tok, ids] of Object.entries(tokenOccurrences)) {
				const idx = (ids || []).indexOf(clickedId);
				if (idx !== -1) {
					foundToken = tok;
					occIdx = idx;
					break;
				}
			}
			if (!foundToken) {
				const m = clickedId.match(/^nh-token-(\d+)$/);
				if (m) {
					const n = parseInt(m[1], 10) - 1;
					if (!Number.isNaN(n) && n >= 0 && n < tokens.length) {
						foundToken = tokens[n];
						occIdx = 0;
					}
				}
			}
			if (!foundToken) return;

			// Focus the associated input and set cursor at end
			const inputEl = document.getElementById(getInputId(foundToken)) as HTMLTextAreaElement | null;
			if (inputEl) {
				// Scroll accounting for sticky header + filter bar so input isn't hidden at the top
				scrollTokenInputIntoView(inputEl);
				// Then focus without re-scrolling
				inputEl.focus({ preventScroll: true });
				const val = inputEl.value ?? '';
				// Place cursor at end
				try {
					inputEl.selectionStart = inputEl.selectionEnd = val.length;
				} catch {}
			}

			// If not the first occurrence, open the overlay and select the clicked occurrence
			if (occIdx > 0) {
				// Determine index for openTokenOverlay fallback semantics
				const tokenIndex = tokens.indexOf(foundToken);
				if (tokenIndex >= 0) {
					openTokenOverlay(tokenIndex, foundToken);
					selectOverlayOccurrence(occIdx);
				}
			} else {
				// Ensure overlay is closed when clicking the first occurrence
				isTokenOverlayOpen = false;
			}
		};
		appHooks.hook('private-ai.token-replacer.preview.token-clicked', previewTokenClickedHandler);
		removePreviewTokenClickedHook = () => {
			try {
				appHooks.removeHook('private-ai.token-replacer.preview.token-clicked', previewTokenClickedHandler);
			} catch {}
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

	// Measure the submit bar height and watch for changes
	updateSubmitBarHeight();
	try {
		submitRO = new ResizeObserver(() => updateSubmitBarHeight());
		if (submitBarEl) submitRO.observe(submitBarEl);
	} catch {
	}
	submitResizeHandler = () => updateSubmitBarHeight();
	window.addEventListener('resize', submitResizeHandler);

	// Track visibility of the SelectedDocumentSummary as the page scrolls/resizes
	summaryScrollHandler = () => scheduleSummaryVisibilityCheck();
	try {
		// passive listeners for performance
		window.addEventListener('scroll', summaryScrollHandler as EventListener, { passive: true } as any);
		window.addEventListener('resize', summaryScrollHandler as EventListener);
	} catch {
	}
	computeSummaryVisibility();
	// Initialize IntersectionObserver once DOM is ready and the header is measured
	setupSummaryObserver();

	isLoading = true;
	loadError = null;
	try {
		const { tokens: tk, values: vals, occurrences: occ } = await loadTokensAndValuesWithRetry();
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
	// Cleanup submit bar observers/listeners
	try {
		submitRO?.disconnect();
	} catch {
	}
	submitRO = null;
	if (submitResizeHandler) {
		window.removeEventListener('resize', submitResizeHandler);
		submitResizeHandler = null;
	}
	// Remove overlay hook listener
	try {
		removeOverlayHook && removeOverlayHook();
	} catch {
	}
	// Remove preview reloaded hook listener
	try {
		removePreviewReloadedHook && removePreviewReloadedHook();
	} catch {
	}
	// Remove preview token clicked hook listener
	try {
		removePreviewTokenClickedHook && removePreviewTokenClickedHook();
	} catch {
	}
	// Cleanup summary visibility listeners
	try {
		if (summaryScrollHandler) {
			window.removeEventListener('scroll', summaryScrollHandler as EventListener);
			window.removeEventListener('resize', summaryScrollHandler as EventListener);
			summaryScrollHandler = null;
		}
		try {
			cancelAnimationFrame(summaryRaf);
		} catch {
		}
		try {
			summaryIO?.disconnect();
		} catch {
		}
		summaryIO = null;
	} catch {
	}
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
							class="inline-flex items-center justify-center h-6 w-6 rounded border border-gray-300 dark:border-gray-700 text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed"
							on:click={openPreviewPanel}
							aria-label={$i18n.t('Preview')}
							title={$i18n.t('Preview')}
							disabled={isPreviewOpen}
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
			<span
				class="pointer-events-none absolute inset-0 pl-6 flex items-center text-[8px] leading-none text-gray-700 dark:text-gray-200 select-none">
				{progressPercent}% {$i18n.t('Complete')}
			</span>
		</div>
	</div>

	<!-- Content area container (page scroll) -->
	<div class="relative">
		<!-- Selected document summary (non-sticky) -->
		<div class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
				 bind:this={summaryEl}>
			<SelectedDocumentSummary on:preview={openPreviewPanel} disabled={isPreviewOpen} />
		</div>

		<!-- Overlay scope wrapper: covers from below SelectedDocumentSummary -->
		<div class="relative">
			<!-- Search and filtering (sticky within scroll container) -->

			<!-- Content area -->
			{#if isTokenOverlayOpen && overlayToken}
				<!-- Token occurrences overlay (scoped within EditValuesView search+content area) -->
				<div
					class="sticky z-30 bg-gray-50 dark:bg-gray-900 border-l border-r border-gray-200 dark:border-gray-800 overflow-y-auto"
					style={`top: ${headerHeight}px; height: calc(100vh - ${headerHeight}px); min-height: calc(100vh - ${headerHeight}px); padding-bottom: ${submitBarHeight}px;`}
					bind:this={overlayContainerEl}>
					<!-- Sticky overlay header: title, token label, input, and navigation (Prev/Next) -->
					<div class="sticky top-0 z-20 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
						<div class="p-3 sm:p-4 pb-2 sm:pb-3">
							<div class="flex items-start justify-between gap-3">
								<div class="text-lg font-medium self-center font-primary">
									{$i18n.t('Token Occurrences')}
									<span class="text-xs font-normal">({overlayOccurrences.length})</span>
								</div>
								<button type="button"
												class="inline-flex flex-shrink-0 items-center justify-center h-8 w-8 rounded text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
												aria-label={$i18n.t('Close')} on:click={closeTokenOverlay}>
									<span aria-hidden="true">✕</span>
								</button>
							</div>
							<div class="flex items-start justify-between gap-3 mb-3">
								<div class="space-y-1">
									<Tooltip content={overlayToken} placement="top" className="inline-flex max-w-full">
										<span class="token-text text-xs">{overlayToken}</span>
									</Tooltip>
								</div>
							</div>

							<!-- Synced input -->
							<div class="space-y-2 mb-3">
								<ExpandableTextarea
									fullscreenStrategy="container"
									id="overlay-input"
									ariaLabel={$i18n.t('Replacement value')}
									placeholder={$i18n.t('Replacement value')}
									value={overlayToken ? (values[overlayToken] ?? '') : ''}
									highlight={overlayState === 'draft'}
									badgeText={overlayState === 'draft' ? $i18n.t('Draft') : undefined}
									on:focus={onOverlayFocus}
									on:input={onOverlayInput}
								/>
							</div>

							<!-- Navigation (sticky header: only Prev/Next) -->
							<div class="flex flex-wrap items-center gap-2 mb-1">
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
							</div>
						</div>
					</div>

					<!-- Non-sticky content (occurrence previews/list) -->
					<div class="p-3 sm:p-4">
						<div class="flex flex-wrap items-center gap-1">
							{#each overlayOccurrences as occId, idx}
        <button type="button"
											class={`px-2 py-1 rounded border text-xs ${idx === overlayCurrentIdx ? 'bg-gray-200 dark:bg-gray-800 border-gray-400 dark:border-gray-600 text-gray-900 dark:text-gray-100' : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
											data-occurrence-index={idx}
											on:click={() => selectOverlayOccurrence(idx)}>
									{idx + 1}
								</button>
							{/each}
						</div>
					</div>
				</div>
			{/if}

   <div
				class="px-2 py-1 border-b border-gray-200 dark:border-gray-800 sticky bg-white dark:bg-gray-900 z-10 shadow"
				style={`top: ${headerHeight}px`}
				bind:this={filterBarEl}>
				<div class="flex items-center justify-between gap-2 mb-1">
					<div class="inline-flex self-stretch gap-2 text-xs text-gray-700 dark:text-gray-300">
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
					<ClearableInput
						id="token-search"
						type="search"
						bind:value={searchQuery}
						placeholder={$i18n.t('Type to filter tokens...')}
						autocomplete="off"
						spellcheck={false}
						ariaLabel={$i18n.t('Token search')}
					/>
				</div>
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
										<!-- 									<div class="flex items-start gap-1">-->
										<Tooltip content={token} placement="top" tippyOptions={{ delay: 1000 }}
														 className="inline-flex max-w-full">
											<span class="token-text">{token}</span>
										</Tooltip>
										<!-- 									</div>-->
									</div>
									<div class="lg:col-span-2">
										{#key token}
											<div class="flex flex-col gap-1">
												<div class="flex items-start gap-1">
													<div class="relative w-full">
														<ExpandableTextarea
															fullscreenStrategy="container"
															id={getInputId(token)}
															placeholder={$i18n.t('token will be removed from document')}
															ariaLabel={$i18n.t('Replacement value')}
															ariaDescribedby={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? `${getInputId(token)}-draft` : undefined}
															describedByText={$i18n.t('Value differs from the last saved value and is not yet saved.')}
															value={values[token] ?? ''}
															highlight={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim())}
															badgeText={((values[token] ?? '').trim() !== (savedValues[token] ?? '').trim()) ? $i18n.t('Draft') : undefined}
															on:focus={() => onPreviewTokenClick(i, token)}
															on:input={handleInput(token, getFirstOccurrenceId(token, i))}
														/>
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
		class="px-4 py-3 border-t border-gray-200 dark:border-gray-800 sticky bottom-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 supports-[backdrop-filter]:dark:bg-gray-900/60 z-20"
		bind:this={submitBarEl}>
		<div class="flex items-center justify-end gap-3">
			<div class="flex items-center gap-2">
				{#if savedCount > 0}
					<button
						class="px-4 py-2 rounded bg-green-700 text-white hover:bg-green-800 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-green-700 dark:hover:bg-green-800 text-nowrap"
						disabled={isLoading || isSubmitting || tokens.length === 0 || savedCount === 0}
						on:click={onGenerateClick}
					>
						{$i18n.t('Generate')}
					</button>
				{/if}
				<button
					class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-600 text-nowrap"
					disabled={isLoading || isSubmitting || tokens.length === 0 || draftCount === 0}
					on:click={() => (showConfirm = true)}
				>
					{$i18n.t('Save Drafts')}
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

<ConfirmDialog
	bind:show={showFinalGenerateConfirm}
	title={$i18n.t('Generate Document')}
	message={$i18n.t('Are you sure you want to generate the document?')}
	cancelLabel={$i18n.t('Cancel')}
	confirmLabel={$i18n.t('Generate')}
	on:confirm={() => void handleGenerate()}
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
