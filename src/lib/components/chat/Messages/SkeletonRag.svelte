<script lang="ts">
  import { onMount } from 'svelte';

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
  function randomDelayMs(min: number, max: number): number {
    return Math.floor(min * 1000 + Math.random() * (max - min) * 1000);
  }
  // Utility: random pause between animation segments (ms)
  function randomPauseMs(): number {
    return 250 + Math.random() * 500;
  }

  // Animate progress from current to next over given duration, with intermittent pauses
  async function animateTo(next: number, duration: number): Promise<void> {
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
  async function runStatuses(): Promise<void> {
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

  onMount(() => {
    cancelled = false;
    runStatuses();
    return () => {
      cancelled = true; // Stop animation if component unmounts
    };
  });
</script>

<div class="flex flex-col items-center w-full px-6 py-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
  <div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 select-none">
    Preparing your response
  </div>
  <div class="text-xs text-gray-500 dark:text-gray-400 font-normal min-h-[1em] mb-3 transition-colors duration-300 select-none">
    {statusText}
  </div>
  <div class="w-full max-w-xs mx-auto h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
    <div
      class="h-1.5 bg-blue-500 dark:bg-blue-400 rounded-full transition-all duration-100"
      style="width: {progress}%;"
    ></div>
  </div>
</div>
