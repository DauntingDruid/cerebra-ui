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
	let hasInitialized = false;

	// Update workflows enabled state when selectedWorkflowIds or deepResearchEnabled changes
	$: if (Object.keys(workflows).length > 0) {
		workflows = Object.entries(workflows).reduce((acc, [id, workflow]) => {
			if (workflow.workflow_type === 'deep_research') {
				acc[id] = { ...workflow, enabled: deepResearchEnabled };
			} else {
				acc[id] = { ...workflow, enabled: selectedWorkflowIds.includes(id) };
			}
			return acc;
		}, {} as Record<string, any>);
	}

	// Watch for dropdown opening to reload workflows
	$: if (show === true && !hasInitialized) {
		console.log('[WorkflowMenu] Dropdown opened for the first time, initializing...');
		hasInitialized = true;
		init();
	}
	
	// Also watch for show changes via event handler
	const handleShowChange = (isOpen: boolean) => {
		console.log('[WorkflowMenu] Dropdown show changed via event:', isOpen);
		if (isOpen) {
			// Always reload when opening
			init();
		} else {
			hasInitialized = false; // Reset so it can initialize again next time
			onClose();
		}
	};

	const init = async () => {
		console.log('[WorkflowMenu] init() called at:', new Date().toISOString());
		// Immediately clear workflows to prevent stale data
		workflows = {};
		loading = true;
		
		try {
			const response = await fetch('/api/v1/workflows/', {
				credentials: 'include'
			});

			if (response.ok) {
				const backendWorkflows = await response.json();
				
				console.log('[WorkflowMenu] All workflows from backend:', backendWorkflows);
				
				const activeWorkflows = backendWorkflows.filter((w: any) => w.is_active === true);
				console.log('[WorkflowMenu] Active workflows:', activeWorkflows);

				const deepResearchWorkflow = activeWorkflows.find((w: any) => 
					w.workflow_type === 'deep_research'
				);
				console.log('[WorkflowMenu] Deep Research workflow found:', deepResearchWorkflow);

				const otherWorkflows = activeWorkflows.filter((w: any) => {
					const isDeepResearch = w.name === 'Deep Research' || w.workflow_type === 'deep_research';
					return !isDeepResearch;
				});
				console.log('[WorkflowMenu] Other workflows (after filtering):', otherWorkflows);

				// Create a new object to force Svelte reactivity
				const newWorkflows: Record<string, any> = {};

				if (deepResearchWorkflow) {
					newWorkflows[deepResearchWorkflow.id] = {
						name: deepResearchWorkflow.name,
						description: deepResearchWorkflow.description || '',
						workflow_type: deepResearchWorkflow.workflow_type,
						enabled: deepResearchEnabled
					};
				}

				otherWorkflows.forEach((workflow: any) => {
					newWorkflows[workflow.id] = {
						name: workflow.name,
						description: workflow.description || '',
						workflow_type: workflow.workflow_type,
						enabled: selectedWorkflowIds.includes(workflow.id)
					};
				});
				
				// Force update by assigning a new object reference
				workflows = newWorkflows;
				
				// Force a reactive update
				await tick();
				
				console.log('[WorkflowMenu] Final workflows to display:', Object.keys(workflows).map(id => ({
					id,
					name: workflows[id].name,
					workflow_type: workflows[id].workflow_type,
					is_active: 'N/A (frontend)'
				})));
				console.log('[WorkflowMenu] workflows object keys count:', Object.keys(workflows).length);
				
				// Verify Deep Research is not in the list if it should be hidden
				const deepResearchInList = Object.values(workflows).some((w: any) => 
					w.workflow_type === 'deep_research'
				);
				if (deepResearchInList) {
					console.warn('[WorkflowMenu] WARNING: Deep Research is still in workflows list!');
				} else {
					console.log('[WorkflowMenu] ✓ Deep Research correctly excluded from list');
				}
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
	on:change={(e) => {
		handleShowChange(e.detail);
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
										{#if workflows[workflowId].workflow_type === 'deep_research'}
											<DeepResearchIcon className="size-4" strokeWidth="1.75" />
										{:else}
											<WorkflowIcon className="size-4" strokeWidth="1.75" />
										{/if}
									</div>

									<div class="flex flex-col items-start gap-0.5">
										<div class="truncate font-medium">{workflows[workflowId].name}</div>
										{#if workflows[workflowId].workflow_type && workflows[workflowId].workflow_type !== 'deep_research'}
											<div class="text-xs text-gray-500 dark:text-gray-400 capitalize">
												{workflows[workflowId].workflow_type.replace('_', ' ')}
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
										
										if (workflows[workflowId].workflow_type === 'deep_research') {
											// Only allow one workflow at a time
											if (state) {
												selectedWorkflowIds = [];
											}
											deepResearchEnabled = state;
										} else {
											await tick();
											if (state) {
												// Only allow one workflow at a time
												selectedWorkflowIds = [workflowId];
												deepResearchEnabled = false;
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
					<a href="/workspace/workflows" class="text-xs text-[#A855F7] hover:text-[#9333EA] dark:text-[#A855F7] dark:hover:text-[#9333EA] hover:underline mt-1 inline-block">
						Create one →
					</a>
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>