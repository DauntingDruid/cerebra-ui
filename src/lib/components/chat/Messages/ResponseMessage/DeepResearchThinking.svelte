<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import DeepResearchIcon from '$lib/components/icons/DeepResearchIcon.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const dispatch = createEventDispatcher();

	export let isThinking = false;
	export let isCollapsed = false;

	let displayedText = '';
	let currentIndex = 0;
	let thinkingInterval: ReturnType<typeof setInterval>;

	// Mock thinking process data
	const mockThinkingSteps = [
		"Analyzing the user's question and breaking it down into key components...",
		"Searching through relevant knowledge bases and documentation...",
		"Cross-referencing multiple sources to ensure accuracy...",
		"Evaluating different approaches and methodologies...",
		"Synthesizing information from various perspectives...",
		"Formulating a comprehensive response based on findings...",
		"Reviewing the answer for clarity and completeness..."
	];

	// Start the thinking animation
	const startThinking = () => {
		if (thinkingInterval) {
			clearInterval(thinkingInterval);
		}
		
		displayedText = '';
		currentIndex = 0;
		
		thinkingInterval = setInterval(() => {
			if (currentIndex < mockThinkingSteps.length) {
				displayedText += mockThinkingSteps[currentIndex] + '\n\n';
				currentIndex++;
			} else {
				clearInterval(thinkingInterval);
				// Dispatch event when thinking is complete
				dispatch('thinking-complete');
			}
		}, 800); // Show each step every 800ms
	};

	// Stop the thinking animation
	const stopThinking = () => {
		if (thinkingInterval) {
			clearInterval(thinkingInterval);
		}
	};

	// Toggle collapse state
	const toggleCollapse = () => {
		isCollapsed = !isCollapsed;
	};

	onMount(() => {
		if (isThinking) {
			startThinking();
		}
		
		return () => {
			if (thinkingInterval) {
				clearInterval(thinkingInterval);
			}
		};
	});

	// Watch for changes in isThinking
	$: if (isThinking) {
		startThinking();
	} else {
		stopThinking();
	}
</script>

<div class="deep-research-thinking">
	<!-- Thinking Header -->
	<div class="flex items-center gap-2 mb-2">
		<div class="flex items-center gap-2 text-gray-600 dark:text-gray-400">
			{#if isThinking}
				<Spinner className="size-4" />
			{:else}
				<DeepResearchIcon className="size-4" />
			{/if}
			<span class="text-sm font-medium">
				{$i18n.t('Deep Research')} - {$i18n.t('Thinking Process')}
			</span>
		</div>
		
		<!-- Collapse/Expand Button -->
		{#if !isThinking}
			<button
				on:click={toggleCollapse}
				class="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
			>
				{isCollapsed ? $i18n.t('Show') : $i18n.t('Hide')}
			</button>
		{/if}
	</div>

	<!-- Thinking Content -->
	{#if !isCollapsed}
		<div class="thinking-content bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
			{#if isThinking}
				<!-- Animated thinking process -->
				<div class="thinking-steps">
					{#each displayedText.split('\n\n') as step, index}
						{#if step.trim()}
							<div class="thinking-step mb-3 last:mb-0">
								<p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
									{step.trim()}
								</p>
							</div>
						{/if}
					{/each}
					
					{#if isThinking}
						<div class="thinking-step mb-3">
							<p class="text-sm text-gray-500 dark:text-gray-500 italic">
								{$i18n.t('Processing...')}
							</p>
						</div>
					{/if}
				</div>
			{:else}
				<!-- Static thinking process -->
				<div class="thinking-steps">
					{#each mockThinkingSteps as step, index}
						<div class="thinking-step mb-3 last:mb-0">
							<p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
								{step}
							</p>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.deep-research-thinking {
		margin: 8px 0;
	}
	
	.thinking-content {
		transition: all 0.3s ease;
	}
	
	.thinking-step {
		animation: fadeInUp 0.5s ease-out;
	}
	
	@keyframes fadeInUp {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
