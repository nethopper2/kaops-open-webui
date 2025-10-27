<script lang="ts">
	import { onMount, getContext, onDestroy } from 'svelte';
	import { WEBUI_NAME, socket, config, user } from '$lib/stores';
	import Search from '../icons/Search.svelte';
	import PulsingDots from '../common/PulsingDots.svelte';
	import ConfirmDialog from '../common/ConfirmDialog.svelte';
	import Microsoft from '../icons/Microsoft.svelte';
	import Slack from '../icons/Slack.svelte';
	import GoogleDrive from '../icons/GoogleDrive.svelte';
	import Gmail from '../icons/Gmail.svelte';
	import type { DataSource } from '$lib/types';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import {
		getDataSources,
		initializeDataSync,
		manualDataSync,
		markDataSourceIncomplete,
		disconnectDataSync,
		resetEmbedding,
		updateSyncStatus
	} from '$lib/apis/data';
	import Atlassian from '../icons/Atlassian.svelte';
	import Outlook from '../icons/Outlook.svelte';
	import OneDrive from '../icons/OneDrive.svelte';
	import Sharepoint from '../icons/Sharepoint.svelte';
	import OneNote from '../icons/OneNote.svelte';
	import Jira from '../icons/Jira.svelte';
	import Confluence from '../icons/Confluence.svelte';
	import Mineral from '../icons/Mineral.svelte';
	import JiraProjectSelector from './JiraProjectSelector.svelte';
	import JiraSelfHostedAuth from './JiraSelfHostedAuth.svelte';
	import DataSyncProgressBar from './DataSyncProgressBar.svelte';
	import DataSyncResultsSummary from './DataSyncResultsSummary.svelte';
	import DataSyncEmbeddingStatus from './DataSyncEmbeddingStatus.svelte';

	const i18n: any = getContext('i18n');

	let loaded = false;
	let query = '';

	let dataSources: Array<DataSource> = [];
	let processingActions = new Set<string>();
	let authCheckInProgress = new Set<string>(); // Track auth checks separately
	
	// Progress tracking
	let syncProgress: Record<string, any> = {};
	
	// Socket inactivity tracking for INCOMPLETE state
	let lastSocketActivity: number = 0; // Single timestamp for all sources
	let incompleteMarked: Set<string> = new Set(); // Track which sources we've already marked as incomplete
	const SOCKET_TIMEOUT_MS = 4 * 60 * 1000; // 4 minutes for production
	let timeoutCheckInterval: ReturnType<typeof setInterval> | null = null;

	// Shared embedding status polling
	let embeddingStatus: any = null;
	let embeddingPollingTimer: ReturnType<typeof setInterval> | null = null;
	let embeddingPollingAttempts = 0;
	let isFetchingEmbeddingStatus = false;
	let consecutiveEmptyResponses = 0; // Track consecutive empty embedding responses
	
	// Toggle state for each data source (sync vs embedding view)
	let activeView: Record<string, 'sync' | 'embedding'> = {};
	let forceUpdate = 0; // Force re-render
	
	// Helper functions for sync error display
	const hasSyncErrors = (dataSource: DataSource) => {
		const isActive = dataSource.sync_status === 'syncing' || dataSource.sync_status === 'embedding';
		const syncResults = dataSource.sync_results as any;
		const hasErrors = isActive && (syncResults?.error_ingesting || syncResults?.error_embedding);
		
		
		return hasErrors;
	};
	
	const getSyncError = (dataSource: DataSource, type: 'ingesting' | 'embedding') => {
		const syncResults = dataSource.sync_results as any;
		return syncResults?.[`error_${type}`];
	};
	
	const formatErrorTimestamp = (timestamp: number) => {
		return new Date(timestamp * 1000).toLocaleString();
	};
	
	// Save embedding service errors to database
	async function saveEmbeddingServiceError(errorResponse: any) {
		try {
			// Find all embedding data sources and update them with the error
			const embeddingSources = dataSources.filter(ds => ds.sync_status === 'embedding');
			
			for (const dataSource of embeddingSources) {
				const currentSyncResults = dataSource.sync_results || {};
				const updatedSyncResults = {
					...currentSyncResults,
					error_embedding: {
						timestamp: Math.floor(Date.now() / 1000),
						message: errorResponse.message || 'Embedding service error'
					}
				};
				
				await updateSyncStatus(localStorage.token, dataSource.id, {
					sync_status: dataSource.sync_status,
					sync_results: updatedSyncResults
				});
				
				// Update local data source
				dataSource.sync_results = updatedSyncResults as any;
				
				console.log(`💾 Saved embedding service error for ${dataSource.name}`);
			}
		} catch (error) {
			console.error('Error saving embedding service error:', error);
		}
	}

	// Project selector state
	let showProjectSelector = false;
	let projectSelectorDataSource: DataSource | null = null;
	let showSelfHostedAuth = false;
	let selfHostedAuthDataSource: DataSource | null = null;

	// Delete confirmation dialog state
	let showDeleteConfirm = false;
	let selectedDataSource: DataSource | null = null;

    // Stable sort: by action, then by layer, then by name/id (no status)
    $: sortedDataSources = [...dataSources].sort((a, b) => {
        const actionCmp = (a.action || '').localeCompare(b.action || '');
        if (actionCmp !== 0) return actionCmp;
        const layerCmp = (a.layer || '').localeCompare(b.layer || '');
        if (layerCmp !== 0) return layerCmp;
        return (a.name || a.id).localeCompare(b.name || b.id);
    });

	$: filteredItems = sortedDataSources.filter(
		(ds) =>
			query === '' ||
			ds.context.toLowerCase().includes(query.toLowerCase()) ||
			ds.id.toLowerCase().includes(query.toLowerCase())
	);

	// Check for socket inactivity and mark as INCOMPLETE
	const checkSocketTimeout = async () => {
		const now = Date.now();
		const syncingSources = dataSources.filter(ds => ds.sync_status === 'syncing');
		
		if (syncingSources.length === 0) {
			return; // No sources syncing
		}
		
		// Only check timeout if we have actual socket activity
		if (lastSocketActivity === 0) {
			return; // No socket activity yet, don't check timeout
		}
		
		const timeSinceActivity = now - lastSocketActivity;
		console.log(`🕐 socket: ${Math.round(timeSinceActivity/1000)}s old, ${syncingSources.length} sources syncing`);
		
		if (timeSinceActivity > SOCKET_TIMEOUT_MS) {
			console.log(`🚨 TIMEOUT! Marking ${syncingSources.length} sources as INCOMPLETE`);
			
			// Mark ALL syncing sources as incomplete
			for (const dataSource of syncingSources) {
				const sourceId = dataSource.id;
				
				// Skip if we've already marked this source as incomplete
				if (incompleteMarked.has(sourceId)) {
					continue;
				}
				
				// Mark as incomplete in UI immediately
				dataSource.sync_status = 'incomplete';
				incompleteMarked.add(sourceId);
				
				// Persist to backend
				try {
					await markDataSourceIncomplete(localStorage.token, dataSource.id);
					console.log(`📡 ${dataSource.name} incomplete. Data socket down.`);
				} catch (error) {
					console.error(`Failed to persist incomplete status for ${dataSource.name}:`, error);
				}
			}
		}
		
		// Clean up tracking for non-syncing sources
		dataSources.forEach(dataSource => {
			if (dataSource.sync_status !== 'syncing') {
				incompleteMarked.delete(dataSource.id);
			}
		});
	};

	// Shared embedding status polling functions
	async function fetchEmbeddingStatus() {
		// Prevent concurrent calls
		if (isFetchingEmbeddingStatus) {
			console.log('🧠 Embedding status fetch already in progress, skipping');
			return;
		}
		
		isFetchingEmbeddingStatus = true;
		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/data/embedding/embeddingStatus`, {
				method: 'GET',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include'
			});

			if (!response.ok) {
				console.error('Error fetching embedding status:', response.status);
				return;
			}

			const newEmbeddingStatus = await response.json();
			embeddingStatus = newEmbeddingStatus;
			
			// Log embedding status update
			console.log('🧠 received data:', embeddingStatus);
			
			// Check for consecutive empty responses to transition to synced state
			// Only care about empty responses when we have data sources in embedding state
			const hasEmbeddingSources = dataSources.some(ds => ds.sync_status === 'embedding');
			const isEmptyResponse = newEmbeddingStatus && 
				Array.isArray(newEmbeddingStatus) && 
				newEmbeddingStatus.length === 0;
			
			if (hasEmbeddingSources && isEmptyResponse) {
				consecutiveEmptyResponses++;
				console.log(`🧠 Empty embedding response ${consecutiveEmptyResponses}/4 (${dataSources.filter(ds => ds.sync_status === 'embedding').length} sources embedding)`);
				
				// Transition to synced state after 4 consecutive empty responses
				if (consecutiveEmptyResponses >= 4) {
					console.log('🧠 4 consecutive empty responses - transitioning to synced state');
					
					// Update all embedding sources to synced state
					const embeddingSources = dataSources.filter(ds => ds.sync_status === 'embedding');
					for (const dataSource of embeddingSources) {
						console.log(`🧠 Transitioning ${dataSource.name} from embedding to synced`);
						await updateSyncStatus(localStorage.token, dataSource.id, {
							sync_status: 'synced',
							last_sync: Math.floor(Date.now() / 1000)
						});
					}
					
					// Refresh data sources to get latest state
					dataSources = await getDataSources(localStorage.token);
					consecutiveEmptyResponses = 0; // Reset counter
				}
			} else if (!hasEmbeddingSources) {
				// Reset counter when no sources are in embedding state
				consecutiveEmptyResponses = 0;
			} else {
				// Reset counter on non-empty response
				consecutiveEmptyResponses = 0;
			}
			
			// Handle service errors by refreshing data sources to get updated sync_results
			// REMOVED: Don't call getDataSources() on service_error - let backend handle error logging
			
			embeddingStatus = embeddingStatus; // Trigger reactivity
			
			// Save embedding status to database for persistence
			await saveEmbeddingStatusToDatabase(newEmbeddingStatus);
		} catch (error) {
			console.error('Error fetching embedding status:', error);
		} finally {
			isFetchingEmbeddingStatus = false;
		}
	}

	async function saveEmbeddingStatusToDatabase(embeddingData: any) {
		try {
			// Find all data sources that have embedding data
			if (embeddingData?.[0]?.sources) {
				for (const source of embeddingData[0].sources) {
					// Find matching data source by action/layer
					const dataSource = dataSources.find(ds => {
						const expectedDataSource = `${ds.action}/${ds.layer}`;
						return source.data_source.toLowerCase() === expectedDataSource.toLowerCase();
					});
					
					if (dataSource) {
						// Check if embedding is complete
						const counts = source.counts || {};
						const isEmbeddingComplete = (
							(counts.waiting || 0) === 0 &&
							(counts.active || 0) === 0 &&
							(counts.delayed || 0) === 0 &&
							(counts.prioritized || 0) === 0 &&
							(counts.paused || 0) === 0 &&
							(counts['waiting-children'] || 0) === 0 &&
							((counts.completed || 0) >= 1 || (counts.failed || 0) >= 1)
						);
						
						// Update the data source in the database via API
						try {
							// Prepare sync_results with embedding status
							const currentSyncResults = dataSource.sync_results || {};
							const updatedSyncResults = {
								...currentSyncResults,
								embedding_status: {
									last_updated: Date.now(),
									sources: embeddingData[0].sources,
									status: embeddingData[0].status || 'active'
								}
							};
							
							// Determine new sync status
							const newSyncStatus = isEmbeddingComplete ? 'synced' : dataSource.sync_status;
							
							await updateSyncStatus(localStorage.token, dataSource.id, {
								sync_status: newSyncStatus,
								sync_results: updatedSyncResults
							});
							
							// Update local data source with embedding status and new sync status
							dataSource.sync_results = updatedSyncResults as any;
							dataSource.sync_status = newSyncStatus;
							
							// Log completion if embedding finished
							if (isEmbeddingComplete) {
								console.log(`✅ Embedding completed for ${dataSource.name} - transitioning to synced`);
							}
							
							// Auto-switch to embedding view when embedding data becomes available during sync
							if (dataSource && (dataSource.sync_status === 'syncing' || dataSource.sync_status === 'embedding') && getActiveView(dataSource) === 'sync') {
								setActiveView(dataSource, 'embedding');
							}
						} catch (apiError) {
							console.error(`Failed to update embedding status for ${dataSource.name}:`, apiError);
						}
					}
				}
			}
		} catch (error) {
			console.error('Error saving embedding status to database:', error);
		}
	}

	function startEmbeddingPolling() {
		// Don't start if already running
		if (embeddingPollingTimer) {
			console.log('🧠 Embedding polling already active');
			return;
		}

		console.log('🧠 Starting continuous embedding polling');
		
		// Use config value or default to 60 seconds
		const pollingRate = ($config as any)?.private_ai?.rag_embedding_status_polling_rate || 60;
		const POLLING_INTERVAL_MS = pollingRate * 1000;

		embeddingPollingTimer = setInterval(async () => {
			console.log('🧠 Polling embedding status...');
			embeddingPollingAttempts++;
			await fetchEmbeddingStatus();
		}, POLLING_INTERVAL_MS);

		// Fetch immediately
		fetchEmbeddingStatus();
	}

	// Track previous sync status to detect state transitions
	let previousSyncStatus: Record<string, string> = {};
	
	// Auto-switch to embedding view when data source transitions to embedding state
	$: {
		dataSources.forEach(dataSource => {
			const key = getDataSourceKey(dataSource);
			const currentStatus = dataSource.sync_status;
			const previousStatus = previousSyncStatus[key];
			
			// Auto-switch on transition from syncing to embedding (one-time)
			if (previousStatus === 'syncing' && currentStatus === 'embedding' && getActiveView(dataSource) === 'sync') {
				setActiveView(dataSource, 'embedding');
			}
			
			// Auto-switch back to sync view when embedding completes and transitions to synced
			if (previousStatus === 'embedding' && currentStatus === 'synced' && getActiveView(dataSource) === 'embedding') {
				setActiveView(dataSource, 'sync');
			}
			
			// Update previous status
			previousSyncStatus[key] = currentStatus;
		});
	}

	function stopEmbeddingPolling() {
		if (embeddingPollingTimer) {
			console.log('🧠 Stopping embedding polling');
			clearInterval(embeddingPollingTimer);
			embeddingPollingTimer = null;
		}
		embeddingPollingAttempts = 0;
	}


	// Start timeout checking timer
	onMount(() => {
		timeoutCheckInterval = setInterval(checkSocketTimeout, 15000); // Check every 15 seconds
		// startEmbeddingPolling();
	});

	const formatDate = (dateString: string) => {
		const dateInMilliseconds = parseInt(dateString) * 1000;
		const date = new Date(dateInMilliseconds);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / (1000 * 60));
		const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
		const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

		if (diffMins < 1) return 'Just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;

		return date.toLocaleDateString();
	};

	const formatDuration = (milliseconds: number) => {
		const totalSeconds = Math.floor(milliseconds / 1000);
		const hours = Math.floor(totalSeconds / 3600);
		const minutes = Math.floor((totalSeconds % 3600) / 60);
		const seconds = totalSeconds % 60;
		
		return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
	};


	const getSyncStatusColor = (status: string) => {
		switch (status) {
			case 'synced':
				return 'text-green-700 dark:text-green-200';
			case 'embedded':
				return 'text-green-700 dark:text-green-200';
			case 'syncing':
				return 'text-blue-700 dark:text-blue-200';
			case 'embedding':
				return 'text-blue-700 dark:text-blue-300';
			case 'deleting':
				return 'text-orange-600 dark:text-orange-400';
			case 'deleted':
				return 'text-red-700 dark:text-red-300';
			case 'error':
				return 'text-red-700 dark:text-red-200';
			case 'incomplete':
				return 'text-orange-600 dark:text-orange-400';
			case 'unsynced':
				return 'text-yellow-700 dark:text-yellow-200';
			default:
				return 'text-gray-700 dark:text-gray-200';
		}
	};

	const getIconComponent = (iconName: string) => {
		const iconMap = {
			Microsoft: Microsoft,
			Slack: Slack,
			Atlassian: Atlassian,
			GoogleDrive: GoogleDrive,
			Gmail: Gmail,
			Outlook: Outlook,
			OneDrive: OneDrive,
			Sharepoint: Sharepoint,
			OneNote: OneNote,
			JIRA: Jira,
			Confluence: Confluence,
			Mineral: Mineral
		} as const;
		return iconMap[iconName as keyof typeof iconMap];
	};

	const getActionKey = (dataSource: DataSource) => {
		return `${dataSource.action}-${dataSource.layer || 'default'}`;
	};

	// Helper functions for toggle management
	const getDataSourceKey = (dataSource: DataSource) => {
		return `${dataSource.action}-${dataSource.layer}`;
	};

	// Make this reactive to activeView changes
	$: getActiveView = (dataSource: DataSource) => {
		const key = getDataSourceKey(dataSource);
		const explicitView = activeView[key];
		const defaultView = dataSource.sync_status === 'embedding' ? 'embedding' : 'sync';
		const finalView = explicitView || defaultView;
		
		return finalView;
	};

	const setActiveView = (dataSource: DataSource, view: 'sync' | 'embedding') => {
		const key = getDataSourceKey(dataSource);
		activeView[key] = view;
		forceUpdate++; // Force re-render
	};



	const handleSync = async (dataSource: DataSource) => {
		const actionKey = getActionKey(dataSource);

		if (processingActions.has(actionKey)) {
			return;
		}

		processingActions.add(actionKey);
		processingActions = processingActions;

		try {
		// Call embedding reset endpoint before starting sync (non-blocking)
		if ($user?.id) {
			// Proper capitalization for dataSource names
			const formatDataSourceName = (action: string, layer: string) => {
				// Action capitalization
				const actionMap: Record<string, string> = {
					'google': 'Google',
					'microsoft': 'Microsoft',
					'slack': 'Slack',
					'atlassian': 'Atlassian',
					'mineral': 'Mineral'
				};

				// Layer capitalization with special cases
				const layerMap: Record<string, string> = {
					'google_drive': 'Google Drive',
					'gmail': 'Gmail',
					'onedrive': 'OneDrive',
					'sharepoint': 'SharePoint',
					'onenote': 'OneNote',
					'outlook': 'Outlook',
					'direct_messages': 'Direct Messages',
					'channels': 'Channels',
					'group_chats': 'Group Messages',
					'files': 'Files',
					'jira': 'Jira',
					'confluence': 'Confluence',
					'handbooks': 'Handbooks'
				};

				const formattedAction = actionMap[action] || action.charAt(0).toUpperCase() + action.slice(1);
				const formattedLayer = layerMap[layer] || layer.charAt(0).toUpperCase() + layer.slice(1);

				return `${formattedAction}/${formattedLayer}`;
			};

			const dataSourceName = formatDataSourceName(dataSource.action ?? '', dataSource.layer ?? '');
			// Fire-and-forget: don't await to avoid blocking the sync flow
			// resetEmbedding(localStorage.token, $user.id, dataSourceName).catch(error => {
			// 	console.warn('Failed to reset embedding (non-blocking):', error);
			// });

			// Auto-switch to sync view when sync starts
			setActiveView(dataSource, 'sync');
		}

			// Special handling for Mineral
			if (dataSource.action === 'mineral') {
				await handleMineralSync(dataSource);
				return;
			}

			// Special handling for Jira when unsynced - show project selector
			if (
				dataSource.action === 'atlassian' &&
				dataSource.layer === 'jira' &&
				dataSource.sync_status === 'unsynced'
			) {
				await initializeJiraSync(dataSource);
				return;
			}

			switch ((dataSource.sync_status as string).toLowerCase()) {
				case 'synced':
					await updateSync(dataSource.action as string, dataSource.layer as string);
					break;
				case 'error':
					await updateSync(dataSource.action as string, dataSource.layer as string);
					break;
				case 'incomplete':
					await updateSync(dataSource.action as string, dataSource.layer as string);
					break;
				case 'unsynced':
					await initializeSync(dataSource.action as string, dataSource.layer as string);
					// Clear processing state immediately for auth flows
					processingActions.delete(actionKey);
					processingActions = processingActions;
					return; // Skip finally block
				case 'deleted':
					await initializeSync(dataSource.action as string, dataSource.layer as string);
					// Clear processing state immediately for auth flows
					processingActions.delete(actionKey);
					processingActions = processingActions;
					return; // Skip finally block
				case 'embedding':
					await updateSync(dataSource.action as string, dataSource.layer as string);
					break;
			}
		} finally {
			processingActions.delete(actionKey);
			processingActions = processingActions;
		}
	};

	const initializeJiraSync = async (dataSource: DataSource) => {
		// Check if self-hosted is enabled
		const isSelfHosted = $config?.features.atlassian_self_hosted_enabled;

		if (isSelfHosted) {
			// Show self-hosted auth modal
			selfHostedAuthDataSource = dataSource;
			showSelfHostedAuth = true;
		} else {
			// Existing cloud OAuth flow
			let syncDetails = await initializeDataSync(
				localStorage.token,
				dataSource.action as string,
				dataSource.layer as string
			);

			if (syncDetails.url) {
				const authWindow = window.open(syncDetails.url, '_blank', 'width=600,height=700');

				// Check if popup was blocked
				if (!authWindow || authWindow.closed || typeof authWindow.closed === 'undefined') {
					console.warn('Popup blocked for Jira auth - showing fallback message');
					alert(
						'Please allow popups for this site to authorize Jira.\n\n' +
						'Click OK, then click the Sync button again.\n\n' +
						`Or manually open this URL:\n${syncDetails.url}`
					);
					return;
				}

				const messageHandler = async (event: MessageEvent) => {
					if (event.data?.type === 'atlassian_connected' && event.data?.layer === 'jira') {
						window.removeEventListener('message', messageHandler);
						dataSources = await getDataSources(localStorage.token);
						projectSelectorDataSource = dataSource;
						showProjectSelector = true;
					}
				};

				window.addEventListener('message', messageHandler);

				const checkWindowClosed = setInterval(() => {
					if (authWindow && authWindow.closed) {
						window.removeEventListener('message', messageHandler);
						clearInterval(checkWindowClosed);
					}
				}, 500);
			}
		}
	};

	const handleSelfHostedAuthSuccess = async (event: CustomEvent) => {
		// Refresh data sources
		dataSources = await getDataSources(localStorage.token);

		// Show project selector
		projectSelectorDataSource = event.detail.dataSource;
		showProjectSelector = true;

		// Reset self-hosted auth state
		showSelfHostedAuth = false;
		selfHostedAuthDataSource = null;
	};

	const handleSelfHostedAuthClose = () => {
		showSelfHostedAuth = false;
		selfHostedAuthDataSource = null;
	};

	const handleMineralSync = async (dataSource: DataSource) => {
		if (dataSource.sync_status === 'unsynced') {
			showMineralAuthPopup();
		} else {
			await updateSync(dataSource.action as string, dataSource.layer as string);
		}
	};

	const showMineralAuthPopup = () => {
		const popup = window.open(
			'',
			'MineralAuth',
			'width=400,height=500,resizable=no,scrollbars=yes'
		);

		if (popup) {
			popup.document.open();
			popup.document.write(
				'<!DOCTYPE html><html><head><title>Private AI | Mineral Authentication</title>'
			);
			popup.document.write(
				'<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:2rem;margin:0;background:#f8f9fa}.form-container{background:white;padding:2rem;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}h2{color:#333;margin-bottom:1.5rem;text-align:center}.form-group{margin-bottom:1rem}label{display:block;margin-bottom:0.5rem;color:#555;font-weight:500}input{width:100%;padding:0.75rem;border:1px solid #ddd;border-radius:4px;font-size:1rem;box-sizing:border-box}input:focus{outline:none;border-color:#007bff;box-shadow:0 0 0 2px rgba(0,123,255,0.25)}button{width:100%;padding:0.75rem;background:#007bff;color:white;border:none;border-radius:4px;font-size:1rem;cursor:pointer;margin-top:1rem}button:hover{background:#0056b3}button:disabled{background:#6c757d;cursor:not-allowed}.error{color:#dc3545;font-size:0.875rem;margin-top:0.5rem}.loading{text-align:center;margin-top:1rem}</style>'
			);
			popup.document.write(
				'</head><body><div class="form-container"><h2>Connect to Mineral HR</h2>'
			);
			popup.document.write(
				'<form id="mineralForm"><div class="form-group"><label for="username">Username</label>'
			);
			popup.document.write('<input type="text" id="username" name="username" required></div>');
			popup.document.write('<div class="form-group"><label for="password">Password</label>');
			popup.document.write('<input type="password" id="password" name="password" required></div>');
			popup.document.write('<button type="submit" id="submitBtn">Connect</button>');
			popup.document.write('<div id="error" class="error" style="display:none;"></div>');
			popup.document.write(
				'<div id="loading" class="loading" style="display:none;">Connecting to Mineral...</div>'
			);
			popup.document.write('</form></div></body></html>');
			popup.document.close();

			popup.addEventListener('load', () => {
				const form = popup.document.getElementById('mineralForm');
				form?.addEventListener('submit', async (e) => {
					e.preventDefault();

					const submitBtn = popup.document.getElementById('submitBtn') as HTMLButtonElement;
					const errorDiv = popup.document.getElementById('error') as HTMLDivElement;
					const loadingDiv = popup.document.getElementById('loading') as HTMLDivElement;
					const username = (popup.document.getElementById('username') as HTMLInputElement)?.value;
					const password = (popup.document.getElementById('password') as HTMLInputElement)?.value;

					if (errorDiv && loadingDiv && submitBtn) {
						errorDiv.style.display = 'none';
						loadingDiv.style.display = 'block';
						submitBtn.disabled = true;
					}

					try {
						const response = await fetch(WEBUI_BASE_URL + '/api/v1/data/mineral/auth', {
							method: 'POST',
							headers: {
								'Content-Type': 'application/json',
								Authorization: 'Bearer ' + localStorage.getItem('token')
							},
							body: JSON.stringify({
								username: username,
								password: password
							})
						});

						if (response.ok) {
							window.location.reload();
							popup.close();
						} else {
							const error = await response.json();
							throw new Error(error.detail || 'Authentication failed');
						}
					} catch (error) {
						const errorMessage = error instanceof Error ? error.message : 'An error occurred';
						errorDiv.textContent = errorMessage;
						errorDiv.style.display = 'block';
						loadingDiv.style.display = 'none';
						submitBtn.disabled = false;
					}
				});
			});
		}
	};

	const updateDataSourceSyncStatus = (sourceData: {
		source: string;
		status: 'synced' | 'syncing' | 'error' | 'unsynced' | 'deleting' | 'deleted' | 'embedding';
		message: string;
		timestamp: string;
		sync_results?: any;
		files_total?: number;
		mb_total?: number;
	}) => {
		dataSources = dataSources.map((ds) => {
			if (ds.name === sourceData.source) {
				return { 
					...ds, 
					sync_status: sourceData.status, 
					last_sync: sourceData.timestamp,
					sync_results: sourceData.sync_results || ds.sync_results,
					files_total: sourceData.files_total !== undefined ? sourceData.files_total : ds.files_total,
					mb_total: sourceData.mb_total !== undefined ? sourceData.mb_total : ds.mb_total
				};
			}
			return ds;
		});
	};

	const initializeSync = async (action: string, layer: string) => {
		console.log(`🔐 Requesting authorization URL for ${action}/${layer}...`);

		let syncDetails = await initializeDataSync(localStorage.token, action, layer);

		console.log(`🔐 Authorization URL received:`, syncDetails?.url ? 'Yes' : 'No');

		if (syncDetails.url) {
			console.log(`🪟 Opening auth window for ${action}/${layer}`);
			const authWindow = window.open(syncDetails.url, '_blank', 'width=600,height=700');

			// Check if popup was blocked
			if (!authWindow || authWindow.closed || typeof authWindow.closed === 'undefined') {
				console.warn('Popup blocked - showing fallback message');
				alert(
					`Please allow popups for this site to authorize ${action}.\n\n` +
					`Click OK, then click the Sync button again.\n\n` +
					`Or manually open this URL:\n${syncDetails.url}`
				);
			} else {
				console.log(`✅ Auth window opened successfully for ${action}/${layer}`);
			}
		} else {
			console.error('No authorization URL returned from backend');
			alert(`Failed to get authorization URL for ${action}. Please try again.`);
		}

		// Refresh and force reactivity update
		const newDataSources = await getDataSources(localStorage.token);
		dataSources = [...newDataSources]; // Force new array reference for reactivity
	};

	const updateSync = async (action: string, layer: string) => {
		// Clear any stale progress data for this action/layer
		const key = `${action}-${layer}`;
		delete syncProgress[key];
		syncProgress = syncProgress; // Trigger reactivity

		// Mark auth check as in progress
		authCheckInProgress.add(key);
		authCheckInProgress = authCheckInProgress;

		try {
			// Use the manual sync endpoint that actually triggers the sync process
			let syncDetails = await manualDataSync(localStorage.token, action, layer);

			// Handle case where syncDetails is null (error occurred)
			if (!syncDetails) {
				console.error('Sync failed - no details returned. This usually means the sync is already in progress or there was an authentication error.');
				return;
			}

			// Handle case where backend returns a message instead of sync details (e.g., "sync already in progress")
			if (syncDetails.message && !syncDetails.url) {
				console.warn('Sync not started:', syncDetails.message);
				return;
			}

			if (syncDetails.detail?.reauth_url) {
				if (action === 'mineral') {
					await showMineralAuthPopup();
					return;
				}

				const authWindow = window.open(syncDetails.detail.reauth_url, '_blank', 'width=600,height=700');

				// Check if popup was blocked
				if (!authWindow || authWindow.closed || typeof authWindow.closed === 'undefined') {
					console.warn('Popup blocked for reauth - showing fallback message');
					alert(
						`Please allow popups for this site to re-authorize ${action}.\n\n` +
						`Click OK, then click the Sync button again.\n\n` +
						`Or manually open this URL:\n${syncDetails.detail.reauth_url}`
					);
				}

				return;
			}

			dataSources = await getDataSources(localStorage.token);
		} finally {
			// Clear auth check state
			authCheckInProgress.delete(key);
			authCheckInProgress = authCheckInProgress;
		}
	};

	const handleDelete = async (dataSource: DataSource) => {
		const actionKey = getActionKey(dataSource);

		if (processingActions.has(actionKey)) {
			return;
		}

		processingActions.add(actionKey);
		processingActions = processingActions;

		try {
			const action = dataSource.action;
			const layer = dataSource.layer;

			await disconnectDataSync(localStorage.token, action as string, layer as string);
			// Add a small delay to allow backend to update status
			await new Promise(resolve => setTimeout(resolve, 500));
			dataSources = await getDataSources(localStorage.token);
		} catch (error) {
			console.error('Error in handleDelete:', error);
		} finally {
			processingActions.delete(actionKey);
			processingActions = processingActions;
		}
	};

	const getPhaseDisplayText = (phaseName: string) => {
		// Map backend phase names to user-friendly display text
		const phaseMap: Record<string, string> = {
			'Phase 1: Starting': 'Initializing',
			'Phase 2: Discovery': 'Analyzing',
			'Phase 3: Processing': 'Processing',
			'Phase 4: Summarizing': 'Finalizing'
		};
		return phaseMap[phaseName] || phaseName;
	};


	const getSyncStatusText = (status: string, dataSource?: DataSource) => {
		// If syncing and we have phase data, show the mapped phase name
		if (status === 'syncing' && dataSource) {
			const key = `${dataSource.action}-${dataSource.layer}`;
			if (syncProgress[key] && syncProgress[key].phase_name) {
				return getPhaseDisplayText(syncProgress[key].phase_name);
			}
		}
		
		switch (status) {
			case 'synced':
				return 'Synced';
			case 'embedded':
				return 'Synced';
			case 'syncing':
				return 'Syncing...';
			case 'embedding':
				return 'Embedding';
			case 'deleting':
				return 'Deleting';
			case 'deleted':
				return 'Deleted';
			case 'error':
				return 'Error';
			case 'unsynced':
				return 'Unsynced';
			case 'incomplete':
				return 'Incomplete';
			default:
				return 'Unknown';
		}
	};

	const isProcessing = (dataSource: DataSource) => {
		const actionKey = getActionKey(dataSource);
		return processingActions.has(actionKey) || authCheckInProgress.has(actionKey) || dataSource.sync_status === 'syncing' || dataSource.sync_status === 'deleting';
	};

	$: getProgressData = (dataSource: DataSource) => {
		const key = `${dataSource.action}-${dataSource.layer}`;
		// If we have real-time progress data, use it
		if (syncProgress[key]) {
			return {
				files_processed: syncProgress[key].files_processed || 0,
				files_total: syncProgress[key].files_total || 0,
				mb_processed: syncProgress[key].mb_processed || 0,
				mb_total: syncProgress[key].mb_total || 0,
				sync_start_time: syncProgress[key].sync_start_time || 0,
				folders_found: syncProgress[key].folders_found || 0,
				files_found: syncProgress[key].files_found || 0,
				total_size: syncProgress[key].total_size || 0,
				phase: syncProgress[key].phase || 'processing'
			};
		}
		// For syncing state, start with 0 progress, not final values
		if (dataSource.sync_status === 'syncing') {
			return {
				files_processed: 0,
				files_total: dataSource.files_total || 0,
				mb_processed: 0,
				mb_total: dataSource.mb_total || 0,
				sync_start_time: Date.now(), // Always use current time for new sync
				folders_found: 0,
				files_found: 0,
				total_size: 0,
				phase: 'processing' // Default to processing if no real-time data
			};
		}
		// For other states, use the stored values
		return {
			files_processed: dataSource.files_processed || 0,
			files_total: dataSource.files_total || 0,
			mb_processed: dataSource.mb_processed || 0,
			mb_total: dataSource.mb_total || 0,
			sync_start_time: dataSource.sync_start_time || 0,
			folders_found: 0,
			files_found: 0,
			total_size: 0,
			phase: 'processing'
		};
	};


	const handleProjectSyncStarted = async (event: CustomEvent) => {
		showProjectSelector = false;
		projectSelectorDataSource = null;

		// Refresh data sources
		dataSources = await getDataSources(localStorage.token);
	};

	const handleProjectSelectorClose = () => {
		showProjectSelector = false;
		projectSelectorDataSource = null;
	};

	export const getBackendConfig = async () => {
		let error = null;

		const res = await fetch(`${WEBUI_BASE_URL}/api/config`, {
			method: 'GET',
			credentials: 'include',
			headers: { 'Content-Type': 'application/json' }
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				error = err;
				return null;
			});

		if (error) {
			throw error;
		}

		return res;
	};

	onMount(async () => {
		dataSources = await getDataSources(localStorage.token);
		
		// Log syncing sources on page load/refresh
		const syncingSources = dataSources.filter(ds => ds.sync_status === 'syncing');
		console.log(`💾 ${syncingSources.length} sources syncing`);
		
		// If there are syncing sources but no socket activity, start monitoring immediately
		if (syncingSources.length > 0 && lastSocketActivity === 0) {
			console.log('🚨 Found syncing sources with no socket activity - starting timeout monitoring');
			lastSocketActivity = Date.now(); // Start the timer
		}
		
		$socket?.on('data-source-updated', async (data) => {
			updateDataSourceSyncStatus(data);
		});
		$socket?.on('sync_progress', (data) => {
			const key = `${data.provider}-${data.layer}`;
			syncProgress[key] = data;
			lastSocketActivity = Date.now(); // Record socket activity
			syncProgress = syncProgress; // Trigger reactivity
		});
		loaded = true;
	});

	onDestroy(() => {
		if ($socket) {
			$socket.off('data-source-updated');
			$socket.off('sync_progress');
		}
		if (timeoutCheckInterval) {
			clearInterval(timeoutCheckInterval);
		}
		if (embeddingPollingTimer) {
			console.log('🧠 Cleaning up embedding polling timer');
			clearInterval(embeddingPollingTimer);
		}
	});
</script>

<style>
	/* Data Sources Table Column Configuration */
	.data-sources-table {
		/* Column 1: Name/Description - adjust as needed */
		--col-name-width: 16rem;       /* Wide enough to prevent text wrapping */
		
		/* Column 2: Status - adjust as needed */
		--col-status-width: 12rem;      /* Try: 6rem, 8rem, 10rem, 12rem, etc. */
		
		/* Column 3: Actions - fixed width */
		--col-actions-width: 20rem;    /* Fixed width to prevent floating */
	}

	.data-sources-table .col-name {
		width: var(--col-name-width);
		white-space: nowrap;  /* Prevent text wrapping for main content */
	}
	
	/* Allow caption text to wrap */
	.data-sources-table .col-name .text-xs {
		white-space: normal;  /* Allow caption text to wrap */
	}

	.data-sources-table .col-status {
		width: var(--col-status-width);
		white-space: nowrap;  /* Prevent text wrapping for main status text */
	}
	
	/* Allow only the phase description text to wrap, not the status badge */
	.data-sources-table .col-status .text-gray-500 {
		white-space: normal;  /* Allow only caption text to wrap */
	}

	.data-sources-table .col-actions {
		width: var(--col-actions-width);
	}
</style>

<svelte:head>
	<title>
		{$i18n.t('Data Sources')} | {$WEBUI_NAME}
	</title>
</svelte:head>

<JiraSelfHostedAuth
	bind:show={showSelfHostedAuth}
	bind:dataSource={selfHostedAuthDataSource}
	on:authSuccess={handleSelfHostedAuthSuccess}
	on:close={handleSelfHostedAuthClose}
/>

<!-- Project Selector Modal -->
<JiraProjectSelector
	bind:show={showProjectSelector}
	on:syncStarted={handleProjectSyncStarted}
	on:close={handleProjectSelectorClose}
/>

<!-- Delete Confirmation Dialog -->
<ConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete data source?')}
	on:confirm={() => {
		if (selectedDataSource) {
			handleDelete(selectedDataSource);
		}
		showDeleteConfirm = false;
	}}
>
	<div class="text-sm text-gray-500">
		{$i18n.t('This will delete the')} <span class="font-semibold">{selectedDataSource?.name}</span> {$i18n.t('files from the AI system. You may resync the data source anytime after the delete process completes.')}
	</div>
</ConfirmDialog>

{#if loaded}
	<div class="flex flex-col gap-1 my-1.5">
		<div class="flex justify-between items-center">
			<div class="flex md:self-center text-xl font-medium px-0.5 items-center">
				{$i18n.t('Data Sources')}
				<div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
				<span class="text-lg font-medium text-gray-500 dark:text-gray-300">
					{filteredItems.length}
				</span>
			</div>
		</div>

		<div class="flex w-full space-x-2">
			<div class="flex flex-1">
				<div class="self-center ml-1 mr-3">
					<Search className="size-3.5" />
				</div>
				<input
					class="w-full text-sm pr-4 py-1 rounded-r-xl outline-none bg-transparent"
					bind:value={query}
					placeholder={$i18n.t('Search Data Sources')}
				/>
			</div>
		</div>
	</div>

	<div class="mb-5">
		{#if filteredItems.length > 0}
			<!-- Desktop Table View -->
			<div class="hidden lg:block overflow-x-auto">
				<table class="w-full table-fixed data-sources-table">
					<thead>
						<tr>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300 col-name"> </th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300 col-status">
								<!-- Status column - no header text -->
							</th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300 col-actions">
								<!-- Actions column - fixed width -->
							</th>
							<th class="text-left py-3 px-4 font-medium text-gray-700 dark:text-gray-300">
								<!-- Empty column - takes remaining space -->
							</th>
						</tr>
					</thead>
					<tbody>
						{#each filteredItems as dataSource}
							<tr
								class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
							>
								<td class="py-3 px-4 col-name">
									<div class="flex items-center gap-3">
										<div
											class="flex-shrink-0 w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center"
										>
											<svelte:component
												this={getIconComponent(dataSource.icon)}
												className="size-5"
											/>
										</div>
										<div class="flex flex-col">
											<div class="font-semibold text-gray-900 dark:text-gray-100">
												{dataSource.name}
											</div>
											<div class="text-xs text-gray-500 dark:text-gray-400">
												{dataSource.context}
											</div>
											<!-- Small duplicate actions under caption -->
											<div class="flex items-center gap-1 mt-1">
												<button
													class="px-1.5 py-0.5 text-xs font-medium rounded bg-blue-50 hover:bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:hover:bg-blue-900/30 dark:text-blue-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
													disabled={isProcessing(dataSource)}
													on:click={() => handleSync(dataSource)}
												>
													Sync
												</button>
												<button
													class="px-1.5 py-0.5 text-xs font-medium rounded bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-900/20 dark:hover:bg-red-900/30 dark:text-red-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
													disabled={isProcessing(dataSource) || (dataSource.sync_status !== 'synced' && dataSource.sync_status !== 'error' && dataSource.sync_status !== 'incomplete' && dataSource.sync_status !== 'ingesting' && dataSource.sync_status !== 'embedding' && dataSource.sync_status !== 'deleted')}
													on:click={() => {
														selectedDataSource = dataSource;
														showDeleteConfirm = true;
													}}
												>
													Delete
												</button>
											</div>
										</div>
									</div>
								</td>
								<td class="py-3 px-4 col-status h-20">
									<div class="space-y-2">
										<!-- Status Badge -->
										<div class="flex items-center gap-2">
											<span
												class="text-xs font-medium uppercase {getSyncStatusColor(
													dataSource.sync_status
												)}"
											>
												{#if dataSource.sync_status === 'syncing'}
													{@const key = `${dataSource.action}-${dataSource.layer}`}
													{@const progressData = syncProgress[key]}
													{#if progressData && progressData.phase_name}
														{getPhaseDisplayText(progressData.phase_name)}
													{:else}
														{getSyncStatusText(dataSource.sync_status)}
													{/if}
												{:else}
													{getSyncStatusText(dataSource.sync_status)}
												{/if}
											</span>
											{#if dataSource.sync_status === 'syncing' || dataSource.sync_status === 'embedding'}
												<PulsingDots />
											{/if}
											
											<!-- Delete info icon for DELETED and SYNCED states -->
											{#if (dataSource.sync_status === 'deleted' || dataSource.sync_status === 'synced') && dataSource.sync_results?.delete_results}
												{@const deleteResults = dataSource.sync_results.delete_results}
												{@const hasDeleteErrors = deleteResults.failed_deletes > 0}
												<div class="relative group ml-1">
													<svg class="w-3 h-3 {hasDeleteErrors ? 'text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300' : 'text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300'} cursor-help" fill="currentColor" viewBox="0 0 20 20">
														<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
													</svg>
													<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
														<div class="font-medium mb-1">Delete Results</div>
														<div class="space-y-1">
															<div>📁 {deleteResults.total_files_to_delete} files attempted</div>
															<div>✅ {deleteResults.successful_deletes} files deleted</div>
															{#if deleteResults.failed_deletes > 0}
																<div>❌ {deleteResults.failed_deletes} files failed</div>
																<div class="mt-2 pt-2 border-t border-gray-600">
																	<div class="font-medium">Error:</div>
																	<div class="text-red-300">{deleteResults.error_message}</div>
																</div>
															{:else if deleteResults.error_message === "success - no files to delete"}
																<div class="mt-2 pt-2 border-t border-gray-600">
																	<div class="font-medium">Status:</div>
																	<div class="text-green-300">{deleteResults.error_message}</div>
																</div>
															{/if}
														</div>
														<div class="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
													</div>
												</div>
											{/if}
											
											<!-- Warning icon for sync/embedding errors -->
											{#if hasSyncErrors(dataSource)}
												<div class="relative group">
													<svg class="w-4 h-4 text-yellow-500 dark:text-yellow-400 cursor-help" fill="currentColor" viewBox="0 0 20 20">
														<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
													</svg>
													<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-10">
														{#if getSyncError(dataSource, 'ingesting')}
															<div class="text-xs font-medium mb-1 text-yellow-300">Ingestion Issues:</div>
															{@const ingestingError = getSyncError(dataSource, 'ingesting')}
															<div class="text-xs text-gray-300 mb-1">{ingestingError.message}</div>
															<div class="text-xs text-gray-400">{formatErrorTimestamp(ingestingError.timestamp)}</div>
														{/if}
														{#if getSyncError(dataSource, 'embedding')}
															{#if getSyncError(dataSource, 'ingesting')}
																<div class="border-t border-gray-600 my-2"></div>
															{/if}
															<div class="text-xs font-medium mb-1 text-yellow-300">Embedding Issues:</div>
															{@const embeddingError = getSyncError(dataSource, 'embedding')}
															<div class="text-xs text-gray-300 mb-1">{embeddingError.message}</div>
															<div class="text-xs text-gray-400">{formatErrorTimestamp(embeddingError.timestamp)}</div>
														{/if}
													</div>
												</div>
											{/if}
										</div>
										
										<!-- Phase Description for syncing -->
										{#if dataSource.sync_status === 'syncing'}
											{@const key = `${dataSource.action}-${dataSource.layer}`}
											{@const progressData = syncProgress[key]}
											<!-- Phase Description for syncing -->
											<div class="text-xs text-gray-500 dark:text-gray-400">
												{#if progressData && progressData.phase_description}
													{syncProgress[key].phase_description}
												{/if}
											</div>
										{:else if dataSource.sync_status === 'embedding'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												vectorizing data
											</div>
										{:else if dataSource.sync_status === 'incomplete'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												Process interrupted. Please try again to sync data.
											</div>
										{/if}
										
										<!-- State-specific information -->
										{#if dataSource.sync_status === 'deleting'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												deleting data...
											</div>
										{:else if dataSource.sync_status === 'synced'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												{dataSource.last_sync ? formatDate(dataSource.last_sync) : 'Never'}
											</div>
										{:else if dataSource.sync_status === 'deleted'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												{dataSource.last_sync ? formatDate(dataSource.last_sync) : 'Unknown'}
											</div>
										{:else if dataSource.sync_status === 'error'}
											<div class="text-xs text-red-500 dark:text-red-400">
												{#if dataSource.sync_results?.delete_results}
													delete phase
												{:else if dataSource.sync_results?.latest_sync}
													embedding phase
												{:else}
													sync phase
												{/if}
											</div>
											<div class="text-xs text-red-500 dark:text-red-400">
												{dataSource.last_sync ? formatDate(dataSource.last_sync) : 'Unknown'}
											</div>
										{:else if dataSource.sync_status === 'unsynced'}
											<div class="text-xs text-gray-500 dark:text-gray-400">
												never synced
											</div>
										{/if}
									</div>
								</td>
								{#if dataSource.sync_status === 'syncing' || dataSource.sync_status === 'embedding'}
									<td class="py-3 px-4 h-20" colspan="2">
										<div class="flex items-center gap-3">
											<!-- Content based on active view -->
											<div class="flex items-center gap-8">
												{#if getActiveView(dataSource) === 'sync'}
													<DataSyncProgressBar {...getProgressData(dataSource)} />
												{:else}
													<DataSyncEmbeddingStatus {dataSource} {embeddingStatus} {syncProgress} />
												{/if}
												
												<!-- TEMPORARILY HIDDEN: Toggle button for embedding phase -->
												<!-- TODO: May restore embedding phase in future - keep all state management intact -->
												<button
													class="px-3 py-1 text-xs rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 whitespace-nowrap"
													style="display: none;"
													on:click={() => {
														const currentView = getActiveView(dataSource);
														const newView = currentView === 'sync' ? 'embedding' : 'sync';
														setActiveView(dataSource, newView);
													}}
												>
													{getActiveView(dataSource) === 'sync' ? 'Show Embedding' : 'Show Ingestion'}
												</button>
											</div>
										</div>
									</td>
								{:else}
									<td class="py-3 px-4 col-actions h-20">
										{#if dataSource.sync_status === 'synced'}
											<DataSyncResultsSummary {dataSource} />
										{:else if dataSource.sync_status === 'deleting'}
											<!-- No content during deleting state -->
										{:else if dataSource.sync_status === 'deleted'}
											<DataSyncResultsSummary {dataSource} />
										{:else if dataSource.sync_status === 'incomplete'}
											<DataSyncResultsSummary {dataSource} />
										{:else if dataSource.sync_status === 'error'}
											<DataSyncResultsSummary {dataSource} isError={true} />
										{/if}
									</td>
									<td class="py-3 px-4">
										<!-- Empty cell - takes remaining space -->
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- Mobile Card View -->
			<div class="lg:hidden space-y-4">
				{#each filteredItems as dataSource}
					<div
						class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
					>
						<div class="flex items-center gap-3 mb-3">
							<div
								class="flex-shrink-0 w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center"
							>
								<svelte:component this={getIconComponent(dataSource.icon)} className="size-5" />
							</div>
							<div class="flex flex-col min-w-0 flex-1">
								<div class="font-semibold text-gray-900 dark:text-gray-100 truncate">
									{dataSource.name}
								</div>
								<div class="text-xs text-gray-500 dark:text-gray-400 truncate">
									{dataSource.context}
								</div>
								<!-- Small duplicate actions under caption -->
								<div class="flex items-center gap-1 mt-1">
									<button
										class="px-1.5 py-0.5 text-xs font-medium rounded bg-blue-50 hover:bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:hover:bg-blue-900/30 dark:text-blue-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
										disabled={isProcessing(dataSource)}
										on:click={() => handleSync(dataSource)}
									>
										Sync
									</button>
									<button
										class="px-1.5 py-0.5 text-xs font-medium rounded bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-900/20 dark:hover:bg-red-900/30 dark:text-red-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
										disabled={isProcessing(dataSource) || (dataSource.sync_status !== 'synced' && dataSource.sync_status !== 'error' && dataSource.sync_status !== 'incomplete' && dataSource.sync_status !== 'ingesting' && dataSource.sync_status !== 'embedding' && dataSource.sync_status !== 'deleted')}
										on:click={() => {
											selectedDataSource = dataSource;
											showDeleteConfirm = true;
										}}
									>
										Delete
									</button>
								</div>
							</div>
						</div>

						<div class="space-y-2">
							<!-- Status Badge -->
							<div class="flex items-center gap-2">
								<span
									class="text-xs font-medium uppercase {getSyncStatusColor(
										dataSource.sync_status
									)}"
								>
									{#if dataSource.sync_status === 'syncing'}
										{@const key = `${dataSource.action}-${dataSource.layer}`}
										{@const progressData = syncProgress[key]}
										{#if progressData && progressData.phase_name}
											{getPhaseDisplayText(progressData.phase_name)}
										{:else}
											{getSyncStatusText(dataSource.sync_status)}
										{/if}
									{:else}
										{getSyncStatusText(dataSource.sync_status)}
									{/if}
								</span>
								{#if dataSource.sync_status === 'syncing'}
									<PulsingDots />
								{/if}
								
								<!-- Delete info icon for DELETED and SYNCED states (mobile) -->
								{#if (dataSource.sync_status === 'deleted' || dataSource.sync_status === 'synced') && dataSource.sync_results?.delete_results}
									{@const deleteResults = dataSource.sync_results.delete_results}
									{@const hasDeleteErrors = deleteResults.failed_deletes > 0}
									<div class="relative group ml-1">
										<svg class="w-3 h-3 {hasDeleteErrors ? 'text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300' : 'text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300'} cursor-help" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
										</svg>
										<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
											<div class="font-medium mb-1">Delete Results</div>
											<div class="space-y-1">
												<div>📁 {deleteResults.total_files_to_delete} files attempted</div>
												<div>✅ {deleteResults.successful_deletes} files deleted</div>
												{#if deleteResults.failed_deletes > 0}
													<div>❌ {deleteResults.failed_deletes} files failed</div>
													<div class="mt-2 pt-2 border-t border-gray-600">
														<div class="font-medium">Error:</div>
														<div class="text-red-300">{deleteResults.error_message}</div>
													</div>
												{:else if deleteResults.error_message === "success - no files to delete"}
													<div class="mt-2 pt-2 border-t border-gray-600">
														<div class="font-medium">Status:</div>
														<div class="text-green-300">{deleteResults.error_message}</div>
													</div>
												{/if}
											</div>
											<div class="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
										</div>
									</div>
								{/if}
								
								<!-- Warning icon for sync/embedding errors -->
								{#if hasSyncErrors(dataSource)}
									<div class="relative group">
										<svg class="w-4 h-4 text-yellow-500 dark:text-yellow-400 cursor-help" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
										</svg>
										<div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-10">
											{#if getSyncError(dataSource, 'ingesting')}
												<div class="text-xs font-medium mb-1 text-yellow-300">Ingestion Issues:</div>
												{@const ingestingError = getSyncError(dataSource, 'ingesting')}
												<div class="text-xs text-gray-300 mb-1">{ingestingError.message}</div>
												<div class="text-xs text-gray-400">{formatErrorTimestamp(ingestingError.timestamp)}</div>
											{/if}
											{#if getSyncError(dataSource, 'embedding')}
												{#if getSyncError(dataSource, 'ingesting')}
													<div class="border-t border-gray-600 my-2"></div>
												{/if}
												<div class="text-xs font-medium mb-1 text-yellow-300">Embedding Issues:</div>
												{@const embeddingError = getSyncError(dataSource, 'embedding')}
												<div class="text-xs text-gray-300 mb-1">{embeddingError.message}</div>
												<div class="text-xs text-gray-400">{formatErrorTimestamp(embeddingError.timestamp)}</div>
											{/if}
										</div>
									</div>
								{/if}
							</div>
							

							<!-- State-specific information -->
							{#if dataSource.sync_status === 'syncing' || dataSource.sync_status === 'embedding'}
								<div class="space-y-2">
									<!-- Content based on active view -->
									{#if getActiveView(dataSource) === 'sync'}
										<DataSyncProgressBar {...getProgressData(dataSource)} />
									{:else}
										<DataSyncEmbeddingStatus {dataSource} {embeddingStatus} {syncProgress} />
									{/if}
									
									<!-- TEMPORARILY HIDDEN: Toggle button for embedding phase (mobile) -->
									<!-- TODO: May restore embedding phase in future - keep all state management intact -->
									<button
										class="px-3 py-1 text-xs rounded whitespace-nowrap {getActiveView(dataSource) === 'embedding' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'}"
										style="display: none;"
										on:click={() => setActiveView(dataSource, getActiveView(dataSource) === 'sync' ? 'embedding' : 'sync')}
									>
										{getActiveView(dataSource) === 'sync' ? 'Show Embedding' : 'Show Ingestion'}
									</button>
								</div>
							{:else if dataSource.sync_status === 'deleting'}
								<!-- No content during deleting state -->
							{:else if dataSource.sync_status === 'synced'}
								<DataSyncResultsSummary {dataSource} />
							{:else if dataSource.sync_status === 'deleted'}
								<DataSyncResultsSummary {dataSource} />
							{:else if dataSource.sync_status === 'incomplete'}
								<DataSyncResultsSummary {dataSource} />
							{:else if dataSource.sync_status === 'error'}
								<DataSyncResultsSummary {dataSource} isError={true} />
							{/if}
						</div>

						<div class="flex gap-2 mt-3">
							<button
								class="flex-1 px-3 py-2 text-xs font-medium rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:hover:bg-blue-900/30 dark:text-blue-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
								disabled={isProcessing(dataSource)}
								on:click={() => handleSync(dataSource)}
							>
								{isProcessing(dataSource) ? 'Processing...' : 'Sync'}
							</button>
							<button
								class="flex-1 px-3 py-2 text-xs font-medium rounded-lg bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-900/20 dark:hover:bg-red-900/30 dark:text-red-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
								disabled={isProcessing(dataSource) || (dataSource.sync_status !== 'synced' && dataSource.sync_status !== 'error' && dataSource.sync_status !== 'incomplete' && dataSource.sync_status !== 'ingesting' && dataSource.sync_status !== 'embedding' && dataSource.sync_status !== 'deleted')}
								on:click={() => {
									selectedDataSource = dataSource;
									showDeleteConfirm = true;
								}}
							>
								{isProcessing(dataSource) ? 'Processing...' : 'Delete'}
							</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="text-center py-8 text-gray-500 dark:text-gray-400">
				{query
					? $i18n.t('No data sources found matching your search.')
					: $i18n.t('No data sources available.')}
			</div>
		{/if}
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<PulsingDots />
	</div>
{/if}
