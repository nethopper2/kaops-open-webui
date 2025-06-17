<script lang="ts">
  import { onMount } from 'svelte';
	import { config } from '$lib/stores';

  export let initialProgress = 1;

  // Each status milestone: text, progress %, and random duration range (seconds)
  const statuses = [
    { text: "Analyzing your question...", progress: 1, min: 0.8, max: 1.5 },
    { text: "Searching knowledge sources...", progress: 30, min: 2.5, max: 5.5 },
    { text: "Reviewing relevant information...", progress: 60, min: 2.5, max: 5.5 },
    { text: "Formulating a detailed response...", progress: 80, min: 1.0, max: 2.0 },
    { text: "Refining for clarity and accuracy...", progress: 88, min: 0.7, max: 1.3 },
    { text: "Almost ready...", progress: 94, min: 0.5, max: 1.0 },
    { text: "Wait for it...", progress: 99, min: 1.0, max: 2.0 },
  ];

  let statusText = statuses[0].text;
  let progress = initialProgress;
  let cancelled = false; // For cleanup if component unmounts

  // Utility: get a random duration in ms between min and max (seconds)
  function randomDelayMs(min, max) {
    return Math.floor(min * 1000 + Math.random() * (max - min) * 1000);
  }
  // Utility: random pause between animation segments (ms)
  function randomPauseMs() {
    return 250 + Math.random() * 500;
  }

  // Animate progress from current to next over given duration, with intermittent pauses
  async function animateTo(next, duration) {
    const start = progress;
    const distance = next - start;
    const startTime = Date.now();
    let elapsed = 0;

    while (elapsed < duration && !cancelled) {
      // Move for a random short duration
      const moveDuration = Math.min(120 + Math.random() * 200, duration - elapsed);
      const pauseDuration = Math.min(randomPauseMs(), duration - elapsed - moveDuration);

      // Animate progress for moveDuration
      const moveStart = Date.now();
      const moveStartValue = progress;
      const targetValue = start + distance * ((elapsed + moveDuration) / duration);

      while ((Date.now() - moveStart < moveDuration) && !cancelled) {
        const t = (Date.now() - moveStart) / moveDuration;
        progress = moveStartValue + (targetValue - moveStartValue) * t;
        await new Promise(r => setTimeout(r, 16));
      }
      progress = targetValue;
      elapsed = Date.now() - startTime;

      // Pause if time remains
      if (elapsed < duration && pauseDuration > 0 && !cancelled) {
        await new Promise(r => setTimeout(r, pauseDuration));
        elapsed = Date.now() - startTime;
      }
    }
    progress = next;
  }

  // Main status/progress loop
  async function runStatuses() {
    progress = initialProgress;
    statusText = statuses[0].text;
    for (let i = 0; i < statuses.length && !cancelled; i++) {
      const { text, progress: next, min, max } = statuses[i];
      const duration = randomDelayMs(min, max);
      await animateTo(next, duration);
      statusText = text;
    }
    // Optional: show a final message after all milestones
    // statusText = "Done!";
  }

  let bgImageAuth = $config?.private_ai?.webui_custom ? JSON.parse($config?.private_ai?.webui_custom)?.bgImageAuth : '';

  onMount(() => {
    cancelled = false;
    runStatuses();
    return () => {
      cancelled = true; // Stop animation if component unmounts
    };
  });
</script>

<div class="relative min-h-[200px] flex items-center justify-center overflow-hidden rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 mt-0">
  <!-- Background Image Layer -->
  <div
    class="absolute inset-0 w-full h-full object-cover opacity-20 dark:opacity-30 pointer-events-none !mt-0"
    style="background-image: url('{bgImageAuth}'); background-size: cover; background-position: center;"
    aria-hidden="true"
  ></div>

  <!-- Overlay for content -->
  <div class="relative z-10 flex flex-col items-center w-full px-8 py-6 bg-white/70 dark:bg-gray-900/70 backdrop-blur rounded-xl">
    <div class="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2 tracking-wide select-none">
      Preparing your response
    </div>
    <div class="text-sm text-gray-600 dark:text-gray-400 font-normal min-h-[1.5em] mb-5 transition-colors duration-300 select-none">
      {statusText}
    </div>
    <div class="w-full max-w-xs mx-auto h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
      <div
        class="h-2 bg-green-500 dark:bg-green-400 rounded-full transition-all duration-100"
        style="width: {progress}%;"
      ></div>
    </div>
    <!-- <div class="text-xs mt-2 text-gray-400 select-none">Progress: {Math.round(progress)}%</div> -->
  </div>
</div>

<style>
  .backdrop-blur {
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
  }
</style>
