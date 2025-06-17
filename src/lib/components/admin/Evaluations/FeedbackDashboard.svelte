<script lang="ts">
  import dayjs from 'dayjs';
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import CommentsModal from './CommentsModal.svelte';

  const i18n = getContext('i18n');

  export let feedbacks = [];

  $: feedbacks = feedbacks ?? [];

  // Modal state for comments
  let showComments = false;
  let commentsList = [];
  let commentsTitle = '';

  $: commentsList = commentsList ?? [];

  function openComments(title: string, feedbacksForPeriod) {
    commentsList = (feedbacksForPeriod ?? [])
      .filter(fb => fb.data?.comment && fb.data.comment.trim().length > 0);
    commentsTitle = title;
    showComments = true;
  }

  function openThread(chat_id: string) {
    goto(`/c/${chat_id}`);
    showComments = false;
  }

  function ratingColorClass(val) {
    if (typeof val !== 'number') val = +val;
    if (isNaN(val)) return '';
    if (val >= 6) return 'text-green-600 dark:text-green-400 font-semibold';
    if (val <= 4) return 'text-red-600 dark:text-red-400 font-semibold';
    return '';
  }

  function extractAllResults(feedbacks) {
    feedbacks = feedbacks ?? [];
    return feedbacks
      .map(fb => fb.data?.rating)
      .filter(r => typeof r === 'number' && [-1, 0, 1].includes(r));
  }

  function extractAllDetailedRatings(feedbacks) {
    feedbacks = feedbacks ?? [];
    return feedbacks
      .map(fb => fb.data?.details?.rating)
      .filter(r => typeof r === 'number' && r >= 1 && r <= 10 && !isNaN(r));
  }

  function extractAllComments(feedbacks) {
    feedbacks = feedbacks ?? [];
    return feedbacks
      .filter(fb => fb.data?.comment && fb.data.comment.trim().length > 0)
      .map(fb => ({
        comment: fb.data.comment,
        prompt: fb.data?.prompt,
        chat_id: fb.meta?.chat_id,
        message_id: fb.meta?.message_id
      }));
  }

  function groupByDate(feedbacks) {
    feedbacks = feedbacks ?? [];
    const today = dayjs();
    const days = [];
    for (let i = 0; i < 28; i++) {
      const day = today.subtract(i, 'day');
      const dateStr = day.format('YYYY-MM-DD');
      days.push({ date: dateStr, feedbacks: [] });
    }
    (feedbacks ?? []).forEach(fb => {
      const date = dayjs.unix(fb.updated_at ?? fb.created_at).format('YYYY-MM-DD');
      const day = days.find(d => d.date === date);
      if (day) day.feedbacks.push(fb);
    });
    return days.map(d => {
      const results = extractAllResults(d.feedbacks);
      const detailedRatings = extractAllDetailedRatings(d.feedbacks);
      const comments = extractAllComments(d.feedbacks);
      return {
        date: d.date,
        count: d.feedbacks.length,
        avg_result: results.length ? (results.reduce((a, b) => a + b, 0) / results.length).toFixed(2) : null,
        resultsCount: results.length,
        avg_detailed: detailedRatings.length ? (detailedRatings.reduce((a, b) => a + b, 0) / detailedRatings.length).toFixed(2) : null,
        detailedCount: detailedRatings.length,
        comments,
        feedbacks: d.feedbacks
      };
    });
  }

  $: stats = groupByDate(feedbacks);

  $: allResults = extractAllResults(feedbacks);
  $: totalResults = allResults.length;
  $: totalAvgResult = totalResults ? (allResults.reduce((a, b) => a + b, 0) / totalResults).toFixed(2) : null;

  $: allDetailed = extractAllDetailedRatings(feedbacks);
  $: totalDetailed = allDetailed.length;
  $: totalAvgDetailed = totalDetailed ? (allDetailed.reduce((a, b) => a + b, 0) / totalDetailed).toFixed(2) : null;

  $: allComments = extractAllComments(feedbacks);

  function formatDate(dateStr) {
    return dayjs(dateStr).format('ddd, MMM D, YYYY');
  }

  // Arrow icon for rating
  function ratingArrow(rating: number) {
    if (rating === 1) {
      // Green up arrow
      return `<svg class="w-5 h-5 inline-block text-green-600 dark:text-green-400 align-middle" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" d="M12 19V5M12 5l-7 7m7-7l7 7"/>
      </svg>`;
    }
    if (rating === -1) {
      // Red down arrow
      return `<svg class="w-5 h-5 inline-block text-red-600 dark:text-red-400 align-middle" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" d="M12 5v14M12 19l-7-7m7 7l7-7"/>
      </svg>`;
    }
    // Neutral or missing
    return `<span class="inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300 text-xs font-semibold">${rating ?? ''}</span>`;
  }
</script>

<!-- Comments Modal -->
<CommentsModal
  show={showComments}
  commentsList={commentsList}
  commentsTitle={commentsTitle}
  onClose={() => showComments = false}
/>

<div class="mt-0.5 mb-2 gap-1 flex flex-row justify-between">
  <div class="flex md:self-center text-lg font-medium px-0.5">
    {$i18n.t('Feedback Dashboard')}
    <div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
    <span class="text-lg font-medium text-gray-500 dark:text-gray-300">{feedbacks.length}</span>
  </div>
</div>

<!-- Totals Table with Grouped Headers and Comments -->
<div class="mb-4">
  <table class="w-auto text-sm text-left text-gray-500 dark:text-gray-400 table-auto rounded-sm border border-gray-100 dark:border-gray-800">
    <thead>
      <tr class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-850 dark:text-gray-400">
        <th class="px-3 py-1.5 text-center border-r dark:border-gray-700" colspan="2">{ $i18n.t('Results') }</th>
        <th class="px-3 py-1.5 text-center border-r dark:border-gray-700" colspan="2">{ $i18n.t('Detailed Results') }</th>
        <th class="px-3 py-1.5 text-center">{ $i18n.t('Actions') }</th>
      </tr>
      <tr class="text-xs text-gray-700 bg-gray-50 dark:bg-gray-850 dark:text-gray-400">
        <th class="px-3 py-1.5 text-right">{ $i18n.t('Total') }</th>
        <th class="px-3 py-1.5 text-right border-r dark:border-gray-700">{ $i18n.t('Average') }</th>
        <th class="px-3 py-1.5 text-right">{ $i18n.t('Total') }</th>
        <th class="px-3 py-1.5 text-right border-r dark:border-gray-700">{ $i18n.t('Average') }</th>
        <th class="px-3 py-1.5 text-center">{ $i18n.t('Comments') }</th>
      </tr>
    </thead>
    <tbody>
      <tr class="bg-white dark:bg-gray-900 dark:border-gray-850 text-xs">
        <td class="px-3 py-1.5 text-right">{totalResults}</td>
        <td class="px-3 py-1.5 text-right border-r dark:border-gray-700">
          {#if totalResults}
            <span class={ratingColorClass(+totalAvgResult)}>{totalAvgResult}</span>
          {:else}
            <span class="text-gray-400 italic">{ $i18n.t('No results') }</span>
          {/if}
        </td>
        <td class="px-3 py-1.5 text-right">{totalDetailed}</td>
        <td class="px-3 py-1.5 text-right border-r dark:border-gray-700">
          {#if totalDetailed}
            <span class={ratingColorClass(+totalAvgDetailed)}>{totalAvgDetailed}</span>
          {:else}
            <span class="text-gray-400 italic">{ $i18n.t('No detailed ratings') }</span>
          {/if}
        </td>
        <td class="px-3 py-1.5 text-center">
          <button on:click={() => openComments($i18n.t('All Comments'), feedbacks)} title="Show all comments">
            <!-- Standard chat bubble icon -->
            <svg xmlns="http://www.w3.org/2000/svg" class="inline w-5 h-5 text-blue-500 hover:text-blue-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.77 9.77 0 01-4-.8L3 21l1.8-4A8.96 8.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </button>
        </td>
      </tr>
    </tbody>
  </table>
</div>

<!-- Note about 28 days -->
<div class="mb-2 text-xs text-gray-500 dark:text-gray-400 italic">
  Showing the past 28 days of comments and feedback.
</div>

<!-- Daily Breakdown Table -->
<div class="scrollbar-hidden relative whitespace-nowrap overflow-x-auto max-w-full rounded-sm pt-0.5">
  {#if (feedbacks || []).length === 0}
    <div class="text-center text-xs text-gray-500 dark:text-gray-400 py-1">
      {$i18n.t('No feedbacks found')}
    </div>
  {:else}
    <table class="w-full pr-5 text-sm text-left text-gray-500 dark:text-gray-400 table-auto max-w-full rounded-sm border border-gray-100 dark:border-gray-800">
      <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-850 dark:text-gray-400 -translate-y-0.5">
        <tr class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-850 dark:text-gray-400">
          <th class="px-3 py-1.5 border-r dark:border-gray-700"></th>
          <th class="px-3 py-1.5 text-center border-r dark:border-gray-700" colspan="2">{ $i18n.t('Results') }</th>
          <th class="px-3 py-1.5 text-center border-r dark:border-gray-700" colspan="2">{ $i18n.t('Detailed Ratings') }</th>
          <th class="px-3 py-1.5 text-center">{ $i18n.t('Actions') }</th>
        </tr>
        <tr class="text-xs text-gray-700 bg-gray-50 dark:bg-gray-850 dark:text-gray-400">
          <th class="px-3 py-1.5 border-r dark:border-gray-700">{ $i18n.t('Date') }</th>
          <th class="px-3 py-1.5 text-center">{ $i18n.t('Count') }</th>
          <th class="px-3 py-1.5 text-center border-r dark:border-gray-700">{ $i18n.t('Average') }</th>
          <th class="px-3 py-1.5 text-center">{ $i18n.t('Count') }</th>
          <th class="px-3 py-1.5 text-center border-r dark:border-gray-700">{ $i18n.t('Average (1–10)') }</th>
          <th class="px-3 py-1.5 text-center"></th>
        </tr>
      </thead>
      <tbody>
        {#each stats || [] as stat}
          <tr class="bg-white dark:bg-gray-900 dark:border-gray-850 text-xs">
            <td class="px-3 py-1.5 border-r dark:border-gray-700">{formatDate(stat.date)}</td>
            <td class="px-3 py-1.5 text-right">{stat.resultsCount}</td>
            <td class="px-3 py-1.5 text-right border-r dark:border-gray-700">
              {#if stat.resultsCount}
                <span class={ratingColorClass(+stat.avg_result)}>{stat.avg_result}</span>
              {:else}
                <span class="text-gray-400 italic">{ $i18n.t('No results') }</span>
              {/if}
            </td>
            <td class="px-3 py-1.5 text-right">{stat.detailedCount}</td>
            <td class="px-3 py-1.5 text-right border-r dark:border-gray-700">
              {#if stat.detailedCount}
                <span class={ratingColorClass(+stat.avg_detailed)}>{stat.avg_detailed}</span>
              {:else}
                <span class="text-gray-400 italic">{ $i18n.t('No detailed ratings') }</span>
              {/if}
            </td>
            <td class="px-3 py-1.5 text-center">
              <button on:click={() => openComments(formatDate(stat.date), stat.feedbacks)} title="Show comments for this day">
                <!-- Standard chat bubble icon -->
                <svg xmlns="http://www.w3.org/2000/svg" class="inline w-5 h-5 text-blue-500 hover:text-blue-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.77 9.77 0 01-4-.8L3 21l1.8-4A8.96 8.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
