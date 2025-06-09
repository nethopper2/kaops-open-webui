<script lang="ts">
  import dayjs from 'dayjs';
  import { getChatByShareId } from '$lib/apis/chats/index';
  import { createEventDispatcher, onMount } from 'svelte';

  export let chatId: string;
  export let threadNumber: number;

  const dispatch = createEventDispatcher();

  let expandedChatId: string | null = null;
  let chatMessagesMap: Record<string, any[]> = {};
  let loadingChatMessages = false;
  let chatMessagesError = '';
  let expandedResponses: Record<string, boolean> = {};

  $: questionCount = chatMessagesMap[chatId]?.length || 0;
  $: {
    dispatch('questions', chatMessagesMap[chatId] || []);
  }

  // Build a structure with user questions at root level
  function buildMessageStructure(messages: any[]) {
    const messageMap: Record<string, any> = {};
    const userQuestions: any[] = [];

    // Create a map for quick lookup
    messages.forEach(msg => {
      messageMap[msg.id] = { ...msg, children: [] };
    });

    // Link children to parents
    messages.forEach(msg => {
      if (msg.parentId && messageMap[msg.parentId]) {
        messageMap[msg.parentId].children.push(messageMap[msg.id]);
      }
    });

    // Collect user questions and their immediate assistant responses
    messages.forEach(msg => {
      if (msg.role === 'user') {
        const question = { ...msg, responses: [] };
        // Find immediate assistant responses (children)
        msg.childrenIds?.forEach(childId => {
          const child = messageMap[childId];
          if (child && child.role === 'assistant') {
            question.responses.push(child);
          }
        });
        userQuestions.push(question);
      }
    });

    return userQuestions;
  }

  // Fetch all messages for a chat and build the structure
  async function fetchChatMessages(chatId: string) {
    if (chatMessagesMap[chatId]) return; // Avoid re-fetching
    loadingChatMessages = true;
    chatMessagesError = '';
    try {
      const token = localStorage.token || '';
      const data = await getChatByShareId(token, chatId);
      const messages = data?.chat?.messages;
      if (!messages || !Array.isArray(messages)) {
        chatMessagesError = 'No messages found in chat';
        chatMessagesMap[chatId] = [];
      } else {
        chatMessagesMap[chatId] = buildMessageStructure(messages);
      }
    } catch (e) {
      chatMessagesError = 'Failed to load chat messages';
    } finally {
      loadingChatMessages = false;
    }
  }

  // Fetch messages on mount to ensure questions are available for export
  onMount(() => {
    fetchChatMessages(chatId);
  });

  function handleShowMessages(chatId: string) {
    if (expandedChatId !== chatId) {
      expandedChatId = chatId;
      expandedResponses = {}; // Reset response visibility
      if (!chatMessagesMap[chatId]) {
        fetchChatMessages(chatId);
      }
    } else {
      expandedChatId = null;
      expandedResponses = {};
    }
  }

  function toggleResponse(messageId: string) {
    expandedResponses = { ...expandedResponses, [messageId]: !expandedResponses[messageId] };
  }

  // Svelte action for innerHTML (for SVG arrows)
  function html(node, html) {
    node.innerHTML = html;
    return {
      update(newHtml) {
        node.innerHTML = newHtml;
      }
    };
  }

  function getRatingArrow(rating) {
    if (typeof rating !== 'number') return '';
    if (rating > 0) {
      return `<svg class="inline w-4 h-4 text-green-600" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7"/></svg>`;
    } else if (rating < 0) {
      return `<svg class="inline w-4 h-4 text-red-600" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14m0 0l-7-7m7 7l7-7"/></svg>`;
    }
    return '';
  }
</script>

<div>
  <button
    class="text-xs text-blue-600 underline mt-1"
    on:click={() => handleShowMessages(chatId)}
  >
    {expandedChatId === chatId ? 'Hide Conversation' : 'Show Full Conversation'}
  </button>
  {#if expandedChatId === chatId}
    <div class="mt-2 ml-2 p-2 bg-gray-100 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-800">
      {#if loadingChatMessages}
        <div class="text-gray-400 italic">Loading conversation...</div>
      {:else if chatMessagesError}
        <div class="text-red-500 italic">{chatMessagesError}</div>
      {:else if chatMessagesMap[chatId]?.length}
        <div class="text-xs text-gray-600 dark:text-gray-300 mb-2">
          Total Questions: {questionCount}
        </div>
        <ul class="space-y-2 text-xs text-gray-600 dark:text-gray-300">
          {#each chatMessagesMap[chatId] as msg, index}
            <li>
              <div>
                <span class="font-mono text-xs text-gray-400 mr-2">{threadNumber}.{index + 1}</span>
                <span class="font-semibold">User:</span>
                {msg.content}
                <span class="text-gray-400 ml-2">({dayjs.unix(msg.timestamp).fromNow()})</span>
                {#if msg.responses?.length}
                  <button
                    class="text-blue-600 underline ml-2"
                    on:click={() => toggleResponse(msg.id)}
                  >
                    {expandedResponses[msg.id] ? 'Hide Response' : 'Show Response'}
                  </button>
                {/if}
              </div>
              {#if expandedResponses[msg.id] && msg.responses?.length}
                {#each msg.responses as response}
                  <div class="ml-4 mt-1 p-2 bg-gray-200 dark:bg-gray-700 rounded">
                    <div class="text-xs text-gray-600 dark:text-gray-300">
                      <span class="font-semibold">Assistant:</span>
                      {response.content}
                      <span class="text-gray-400 ml-2">({dayjs.unix(response.timestamp).fromNow()})</span>
                    </div>
                    {#if response.annotation}
                      <div class="ml-4 mt-1 text-xs text-gray-500 dark:text-gray-400">
                        <div class="flex items-center gap-3">
                          <span class="font-semibold">Comment:</span>
                          <span class="ml-1" use:html={getRatingArrow(response.annotation.rating)}></span>
                          {#if response.annotation.details?.rating !== undefined}
                            <span class="font-semibold ml-3">Detailed Rating:</span>
                            <span>{response.annotation.details.rating}</span>
                          {/if}
                        </div>
                        <div>
                          <span class="font-semibold">Reason:</span>
                          {response.annotation.reason ?? '[No reason]'}
                        </div>
                        <div>
                          <span class="font-semibold">Feedback:</span>
                          {response.annotation.comment ?? '[No comment]'}
                        </div>
                      </div>
                    {/if}
                  </div>
                {/each}
              {/if}
            </li>
          {/each}
        </ul>
      {:else}
        <div class="text-gray-400 italic">No user questions found.</div>
      {/if}
    </div>
  {/if}
</div>