<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext, onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

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
	let loading = false;

	onMount(() => {
		init();
	});

	$: if (show) {
		init();
	};

	const init = async () => {
		loading = true;
		
		try {
			// Fetch workflows from your backend
			const response = await fetch('/api/v1/workflows/', {
				credentials: 'include'
			});

			if (response.ok) {
				const backendWorkflows = await response.json();
				
				// Filter only active workflows
				const activeWorkflows = backendWorkflows.filter((w: any) => w.is_active);

				// Add Deep Research as a special workflow
				const deepResearchWorkflow = {
					id: 'deep-research',
					name: 'Deep Research',
					description: 'Comprehensive research with multiple sources',
					workflow_type: 'deep-research'
				};

				// Combine Deep Research with backend workflows
				const allWorkflows = [deepResearchWorkflow, ...activeWorkflows];

				workflows = allWorkflows.reduce((a: Record<string, any>, workflow: any) => {
					a[workflow.id] = {
						name: workflow.name,
						description: workflow.description || '',
						workflow_type: workflow.workflow_type,
						enabled: workflow.id === 'deep-research' 
							? deepResearchEnabled 
							: selectedWorkflowIds.includes(workflow.id)
					};
					return a;
				}, {});
			} else {
				console.error('Failed to fetch workflows:', response.statusText);
				toast.error('Failed to load workflows');
			}
		} catch (error) {
			console.error('Error fetching workflows:', error);
			toast.error('Error loading workflows');
		} finally {
			loading = false;
		}
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
			class="w-full max-w-[320px] rounded-xl px-1 py-1.5 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg"
			sideOffset={10}
			alignOffset={-8}
			side="top"
		>
			{#if loading}
				<div class="flex items-center justify-center py-4">
					<div class="animate-spin rounded-full h-6 w-6 border-b-2 border-gray-900 dark:border-gray-100"></div>
				</div>
			{:else if Object.keys(workflows).length > 0}
				<div class="max-h-80 overflow-y-auto scrollbar-hidden">
					<div class="px-2 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
						Available Workflows
					</div>
					{#each Object.keys(workflows) as workflowId}
						<button
							class="flex w-full justify-between gap-2 items-center px-3 py-2.5 text-sm font-medium cursor-pointer rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
							on:click={() => {
								selectWorkflow(workflowId);
							}}
						>
							<div class="flex-1 truncate">
								<Tooltip
									content={workflows[workflowId]?.description ?? ''}
									placement="top-start"
									className="flex flex-1 gap-2.5 items-center"
								>
									<div class="shrink-0">
										{#if workflowId === 'deep-research'}
											<DeepResearchIcon className="size-4" strokeWidth="1.75" />
										{:else}
											<WorkflowIcon className="size-4" strokeWidth="1.75" />
										{/if}
									</div>

									<div class="flex flex-col items-start gap-0.5">
										<div class="truncate font-medium">{workflows[workflowId].name}</div>
										{#if workflows[workflowId].workflow_type && workflowId !== 'deep-research'}
											<div class="text-xs text-gray-500 dark:text-gray-400 capitalize">
												{workflows[workflowId].workflow_type}
											</div>
										{/if}
									</div>
								</Tooltip>
							</div>

							<div class="shrink-0">
								<Switch
									state={workflows[workflowId].enabled}
									on:change={async (e) => {
										const state = e.detail;
										
										if (workflowId === 'deep-research') {
											deepResearchEnabled = state;
										} else {
											await tick();
											if (state) {
												selectedWorkflowIds = [...selectedWorkflowIds, workflowId];
											} else {
												selectedWorkflowIds = selectedWorkflowIds.filter((id) => id !== workflowId);
											}
										}
									}}
								/>
							</div>
						</button>
					{/each}
				</div>
			{:else}
				<div class="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
					<WorkflowIcon className="size-8 mx-auto mb-2 opacity-50" />
					<p>No workflows available</p>
					<a href="/admin/workflows" class="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1 inline-block">
						Create one →
					</a>
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>