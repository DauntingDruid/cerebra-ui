<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext, onMount, tick } from 'svelte';
	import { get } from 'svelte/store';

	import { config, user } from '$lib/stores';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import WorkflowIcon from '$lib/components/icons/WorkflowIcon.svelte';
	import DeepResearchIcon from '$lib/components/icons/DeepResearchIcon.svelte';

	const i18n = getContext('i18n');

	export let selectedWorkflowIds: string[] = [];
	export let deepResearchEnabled: boolean = false;
	export let onClose: Function;

	let workflows: Record<string, any> = {};
	let show = false;

	// Initialize workflows immediately when component loads, not just when dropdown opens
	onMount(() => {
		init();
	});

	$: if (show) {
		init(); // Also re-init when dropdown opens to ensure state is current
	}

	// Mock workflow data - only Deep Research for now, others will come from backend
	const mockWorkflows = [
		{
			id: 'deep-research',
			name: 'Deep Research',
			description: 'Comprehensive research with multiple sources'
		}
	];

	const init = async () => {
		// TODO: Get workflows from backend when API is available
		// For now, show Deep Research by default (until backend config is ready)
		// TODO: Uncomment backend config check when ready:
		// const showDeepResearch = $config?.features?.enable_deep_research && 
		// 	($user?.role === 'admin' || $user?.permissions?.features?.deep_research);
		// const workflowsToShow = showDeepResearch ? mockWorkflows : [];
		
		const workflowsToShow = mockWorkflows;

		workflows = workflowsToShow.reduce((a: Record<string, any>, workflow: any) => {
			a[workflow.id] = {
				name: workflow.name,
				description: workflow.description,
				enabled: workflow.id === 'deep-research' ? deepResearchEnabled : selectedWorkflowIds.includes(workflow.id)
			};
			return a;
		}, {});
	};

	const selectWorkflow = (workflowId: string) => {
		workflows[workflowId].enabled = !workflows[workflowId].enabled;
	};
</script>

<Dropdown
	bind:show
	on:show={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
		<Tooltip content="Select Workflow">
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[280px] rounded-xl px-1 py-1 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={10}
			alignOffset={-8}
			side="top"
		>
			{#if Object.keys(workflows).length > 0}
				<div class="max-h-28 overflow-y-auto scrollbar-hidden">
					{#each Object.keys(workflows) as workflowId}
						<button
							class="flex w-full justify-between gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer rounded-xl"
							on:click={() => {
								selectWorkflow(workflowId);
							}}
						>
							<div class="flex-1 truncate">
								<Tooltip
									content={workflows[workflowId]?.description ?? ''}
									placement="top-start"
									className="flex flex-1 gap-2 items-center"
								>
									<div class="shrink-0">
										{#if workflowId === 'deep-research'}
											<DeepResearchIcon className="size-4" strokeWidth="1.75" />
										{:else}
											<WorkflowIcon className="size-4" strokeWidth="1.75" />
										{/if}
									</div>

									<div class="truncate">{workflows[workflowId].name}</div>
								</Tooltip>
							</div>

							<div class="shrink-0">
								<Switch
									state={workflows[workflowId].enabled}
									on:change={async (e) => {
										const state = e.detail;
										console.log('Switch changed:', { workflowId, state, currentIds: selectedWorkflowIds });
										
										if (workflowId === 'deep-research') {
											// Direct update for Deep Research to avoid timing issues
											deepResearchEnabled = state;
											console.log('Deep Research directly updated:', deepResearchEnabled);
										} else {
											// Keep existing logic for other workflows
											await tick();
											if (state) {
												selectedWorkflowIds = [...selectedWorkflowIds, workflowId];
											} else {
												selectedWorkflowIds = selectedWorkflowIds.filter((id) => id !== workflowId);
											}
											console.log('Updated selectedWorkflowIds:', selectedWorkflowIds);
										}
									}}
								/>
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
