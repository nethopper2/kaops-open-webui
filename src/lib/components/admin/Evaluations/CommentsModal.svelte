<script lang="ts">
  import dayjs from 'dayjs';
  import ConversationView from './ConversationView.svelte';

  export let show = false;
  export let commentsList = [];
  export let commentsTitle = '';
  export let onClose: () => void = () => {};

  let fullscreen = false;
  let threadQuestions: Record<string, any[]> = {};

  // Group comments by chat_id or meta.chat_id
  $: groupedComments = commentsList.reduce((acc, comment, index) => {
    const chatId = comment.chat_id || comment.meta?.chat_id;
    if (chatId) {
      if (!acc[chatId]) {
        acc[chatId] = { comments: [], threadNumber: index + 1 };
      }
      acc[chatId].comments.push(comment);
    }
    return acc;
  }, {} as Record<string, { comments: any[]; threadNumber: number }>);

  function toggleFullscreen() {
    fullscreen = !fullscreen;
  }

  // Update questions for a specific thread
  function updateThreadQuestions(chatId: string, questions: any[]) {
    threadQuestions = { ...threadQuestions, [chatId]: questions };
  }

  // Export questions as JSON
  function exportQuestions() {
    const allQuestions = Object.entries(groupedComments).flatMap(([chatId, { threadNumber }]) => {
      const questions = threadQuestions[chatId] || [];
      return questions.map((q, index) => ({
        threadNumber,
        questionNumber: `${threadNumber}.${index + 1}`,
        content: q.content,
        timestamp: dayjs.unix(q.timestamp).format('YYYY-MM-DD HH:mm:ss'),
        chatId
      }));
    });

    const json = JSON.stringify(allQuestions, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `questions_export_${dayjs().format('YYYYMMDD_HHmmss')}.json`;
    a.click();
    URL.revokeObjectURL(url);
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

{#if show}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
    <div
      class={`bg-white dark:bg-gray-900 rounded-lg shadow-2xl border border-gray-100 dark:border-gray-800
        p-6 w-full ${fullscreen ? 'h-full max-w-full' : 'max-w-xl'}
        ${fullscreen ? 'max-h-full' : 'max-h-[80vh]'}
        flex flex-col resize-both overflow-auto`}
      style="min-width: 350px; min-height: 250px;"
    >
      <!-- Header -->
      <div class="flex items-center justify-between mb-3">
        <div class="font-bold text-lg flex items-center">
          <svg class="w-6 h-6 text-blue-500 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.77 9.77 0 01-4-.8L3 21l1.8-4A8.96 8.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          {commentsTitle}
        </div>
        <div class="flex gap-2">
          <button class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700" on:click={exportQuestions}>
            Export Questions
          </button>
          <button class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700" on:click={toggleFullscreen}>
            {fullscreen ? 'Windowed' : 'Full Screen'}
          </button>
          <button class="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700" on:click={onClose}>
            Close
          </button>
        </div>
      </div>

      <!-- Comments List -->
      {#if Object.keys(groupedComments).length === 0}
        <div class="text-gray-400 italic flex-1">No comments</div>
      {:else}
        <ul class="space-y-4 overflow-auto flex-1 pr-2">
          {#each Object.entries(groupedComments) as [chatId, { comments, threadNumber }], threadIndex}
            <li class="border-b border-gray-100 dark:border-gray-800 pb-4 last:border-b-0">
              <!-- Thread Header -->
              <div class="font-semibold text-sm text-gray-800 dark:text-gray-100 mb-2">
                Thread #{threadNumber}
                <a
                  class="text-blue-600 dark:text-blue-400 underline text-xs font-medium ml-2"
                  href={"/s/" + chatId}
                  target="_blank"
                  rel="noopener"
                  title="View message thread"
                >
                  View Thread
                </a>
              </div>

              <!-- Comments for this Thread -->
              {#each comments as c, commentIndex}
                <div class="ml-4 mb-2 last:mb-0">
                  <div class="flex items-center justify-between mb-1">
                    <span>
                      <span class="font-mono text-xs text-gray-400 mr-2">{threadNumber}.{commentIndex + 1}</span>
                      <span class="font-semibold text-gray-800 dark:text-gray-100">{c.user?.name}</span>
                      <span class="text-xs text-gray-400 ml-2">{c.user?.email}</span>
                    </span>
                    <span class="text-xs text-gray-400">{c.created_at ? dayjs.unix(c.created_at).fromNow() : ''}</span>
                  </div>

                  <!-- Rating Info -->
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-3">
                    <span class="font-semibold">Rating:</span>
                    <span class="ml-1" use:html={getRatingArrow(c.data?.rating)}></span>
                    {#if c.data?.details?.rating !== undefined}
                      <span class="font-semibold ml-3">Detailed Rating:</span>
                      <span class="{c.data.details.rating >= 6 ? 'text-green-600 dark:text-green-400' : c.data.details.rating <= 4 ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}">
                        {c.data.details.rating}
                      </span>
                      {#if c.data?.model_id}
                        <span class="ml-3 px-1 bg-gray-200 dark:bg-gray-700 rounded">{c.data.model_id}</span>
                      {/if}
                    {/if}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    <span class="font-semibold">Reason:</span>
                    {c.data?.reason ?? '[No reason]'}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    <span class="font-semibold">Feedback:</span>
                    {c.data?.comment ?? '[No comment]'}
                  </div>
                </div>
              {/each}

              <!-- Conversation View for this Thread -->
              <ConversationView 
                chatId={chatId}
                threadNumber={threadNumber}
                on:questions={e => updateThreadQuestions(chatId, e.detail)}
              />
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>
{/if}