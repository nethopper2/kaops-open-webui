<script lang="ts">
  import { onMount } from 'svelte';

  export let initialProgress = 1;

  // Simple loading states with realistic timing
  const loadingStates = [
    { text: "Processing your request...", duration: 1000 },
    { text: "Analyzing content...", duration: 1500 },
    { text: "Generating response...", duration: 2000 },
    { text: "Almost ready...", duration: 1000 },
  ];

  let currentStateIndex = 0;
  let currentText = loadingStates[0].text;
  let progress = initialProgress;
  let cancelled = false;

  // Animate progress smoothly
  function animateProgress(targetProgress: number, duration: number): Promise<void> {
    return new Promise((resolve) => {
      const startProgress = progress;
      const startTime = Date.now();
      
      function update() {
        if (cancelled) {
          resolve();
          return;
        }
        
        const elapsed = Date.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        
        // Ease out function for smooth animation
        const easeOut = 1 - Math.pow(1 - t, 3);
        progress = startProgress + (targetProgress - startProgress) * easeOut;
        
        if (t < 1) {
          requestAnimationFrame(update);
        } else {
          resolve();
        }
      }
      
      requestAnimationFrame(update);
    });
  }

  // Cycle through loading states
  async function runLoadingStates(): Promise<void> {
    for (let i = 0; i < loadingStates.length && !cancelled; i++) {
      const state = loadingStates[i];
      currentText = state.text;
      currentStateIndex = i;
      
      // Animate progress to next milestone
      const targetProgress = ((i + 1) / loadingStates.length) * 90; // Cap at 90% until done
      await animateProgress(targetProgress, state.duration);
    }
    
    // Final animation to 100%
    if (!cancelled) {
      currentText = "Complete!";
      await animateProgress(100, 500);
    }
  }

  onMount(() => {
    cancelled = false;
    runLoadingStates();
    
    return () => {
      cancelled = true;
    };
  });
</script>

<div class="flex flex-col items-center w-full px-6 py-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
  <div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 select-none">
    Preparing your response
  </div>
  <div class="text-xs text-gray-500 dark:text-gray-400 font-normal min-h-[1em] mb-3 transition-colors duration-300 select-none">
    {currentText}
  </div>
  <div class="w-full max-w-xs mx-auto h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
    <div
      class="h-1.5 bg-blue-500 dark:bg-blue-400 rounded-full transition-all duration-300 ease-out"
      style="width: {progress}%;"
    ></div>
  </div>
</div>
