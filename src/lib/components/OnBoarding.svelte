<script>
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_BASE_URL } from '$lib/constants';

	import Marquee from './common/Marquee.svelte';
	import SlideShow from './common/SlideShow.svelte';
	import ArrowRightCircle from './icons/ArrowRightCircle.svelte';

	export let show = true;
	export let getStartedHandler = () => {};

	function setLogoImage() {
		const logo = document.getElementById('logo');

		if (logo) {
			const isDarkMode = document.documentElement.classList.contains('dark');

			if (isDarkMode) {
				const darkImage = new Image();
				darkImage.src = '/static/favicon-dark.png';

				darkImage.onload = () => {
					logo.src = '/static/favicon-dark.png';
					logo.style.filter = ''; // Ensure no inversion is applied if splash-dark.png exists
				};

				darkImage.onerror = () => {
					logo.style.filter = 'invert(1)'; // Invert image if splash-dark.png is missing
				};
			}
		}
	}

	$: if (show) {
		setLogoImage();
	}
</script>

{#if show}
	<div class="w-full h-screen max-h-[100dvh] text-white relative">
		<div class="fixed m-10 z-50">
			<div class="flex space-x-2">
				<div class=" self-center">
					<img
						id="logo"
						crossorigin="anonymous"
						src="{WEBUI_BASE_URL}/static/favicon.png"
						class=" w-6 rounded-full"
						alt="logo"
					/>
				</div>
			</div>
		</div>

		<SlideShow duration={5000} />

		<div
			class="w-full h-full absolute top-0 left-0 bg-linear-to-t from-20% from-black to-transparent"
		></div>

		<div class="w-full h-full absolute top-0 left-0 backdrop-blur-xs bg-black/50"></div>

		<div class="relative bg-transparent w-full min-h-screen flex z-10">
			<div class="flex flex-col justify-center w-full items-center pb-10 text-center">
				<div class="text-5xl lg:text-7xl font-secondary">
					<Marquee
						duration={5000}
						words={[
              $i18n.t('Enterprise AI solutions'),
							$i18n.t('On-Premises AI deployment'),
							$i18n.t('Integrate AI with existing systems'),
							$i18n.t('Protect intellectual property'),
							$i18n.t('Customized AI solutions'),
							$i18n.t('AI productivity'),
							$i18n.t('Safeguard user data privacy'),
              $i18n.t('Small business AI solutions'),
							$i18n.t('Scalable cloud infrastructure'),
							$i18n.t('Experiment with AI models'),
						]}
					/>

					<div class="mt-0.5 text-4xl">{$i18n.t(`Your data. Private and secure.`)}</div>
				</div>

				<div class="flex justify-center mt-8">
					<div class="flex flex-col justify-center items-center">
						<button
							class="relative z-20 flex p-1 rounded-full bg-white/5 hover:bg-white/10 transition font-medium text-sm"
							on:click={() => {
								getStartedHandler();
							}}
						>
							<ArrowRightCircle className="size-10 text-green-500 animate-pulse" />
						</button>
						<div class="mt-1.5 font-primary text-base font-medium">{$i18n.t(`Get started`)}</div>
						<div class="mt-1 font-primary text-xs text-neutral-400">Nethopper Private AI</div>
					</div>
				</div>
			</div>

			<!-- <div class="absolute bottom-12 left-0 right-0 w-full"></div> -->
		</div>
	</div>
{/if}
