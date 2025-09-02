<script lang="ts">
	export let strokeWidth = '1.5';
	export let className = 'size-4';
</script>

<svg
	viewBox="0 0 512 512"
	xmlns="http://www.w3.org/2000/svg"
	stroke-width={strokeWidth}
	class={className}
>
	<defs xmlns="http://www.w3.org/2000/svg"
		><style>
			.cls-1 {
				fill: #253858;
			}
			.cls-2 {
				fill: url(#linear-gradient);
			}
			.cls-3 {
				fill: url(#linear-gradient-2);
			}
		</style><linearGradient
			id="linear-gradient"
			x1="59.68"
			y1="67.65"
			x2="20.35"
			y2="45.05"
			gradientUnits="userSpaceOnUse"
			><stop offset="0.18" stop-color="#0052cc" /><stop
				offset="1"
				stop-color="#2684ff"
			/></linearGradient
		><linearGradient
			id="linear-gradient-2"
			x1="279.76"
			y1="-1616.34"
			x2="240.42"
			y2="-1638.95"
			gradientTransform="translate(282.83 -1616.71) rotate(180)"
			xmlns:xlink="http://www.w3.org/1999/xlink"
			xlink:href="#linear-gradient"
		/></defs
	>
	<path
		class="cls-3"
		d="M2.3 412.2c-4.5 7.6-2.1 17.5 5.5 22.2l105.9 65.2c7.7 4.7 17.7 2.4 22.4-5.3 0-.1.1-.2.1-.2 67.1-112.2 80.5-95.9 280.9-.7 8.1 3.9 17.8.4 21.7-7.7.1-.1.1-.3.2-.4l50.4-114.1c3.6-8.1-.1-17.6-8.1-21.3-22.2-10.4-66.2-31.2-105.9-50.3C127.5 179 44.6 345.3 2.3 412.2zm507.4-312.1c4.5-7.6 2.1-17.5-5.5-22.2L398.4 12.8c-7.5-5-17.6-3.1-22.6 4.4-.2.3-.4.6-.6 1-67.3 112.6-81.1 95.6-280.6.9-8.1-3.9-17.8-.4-21.7 7.7-.1.1-.1.3-.2.4L22.2 141.3c-3.6 8.1.1 17.6 8.1 21.3 22.2 10.4 66.3 31.2 106 50.4 248 120 330.8-45.4 373.4-112.9z"
	/>
</svg>
