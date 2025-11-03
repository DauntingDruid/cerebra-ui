<script lang="ts">
	import Switch from '$lib/components/common/Switch.svelte';
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { getWorkflows, createNewWorkflow, updateWorkflowById, type Workflow } from '$lib/apis/workflows';

	const i18n = getContext('i18n');

	export let saveSettings: Function;

	let deepResearchConfig = {
		ENABLE_DEEP_RESEARCH: false,
		DEEP_RESEARCH_ENDPOINT: ''
	};

	let deepResearchWorkflow: Workflow | null = null;
	let loading = false;

	const findDeepResearchWorkflow = async (): Promise<Workflow | null> => {
		try {
			const workflows = await getWorkflows(localStorage.token || '');
			// First try to find by workflow_type
			let workflow = workflows.find(w => w.workflow_type === 'deep_research');
			// If not found by type, try to find by name (in case user changed type to custom)
			if (!workflow) {
				workflow = workflows.find(w => w.name === 'Deep Research');
			}
			return workflow || null;
		} catch (error) {
			console.error('Error fetching workflows:', error);
			return null;
		}
	};

	const loadConfig = async () => {
		loading = true;
		try {
			deepResearchWorkflow = await findDeepResearchWorkflow();

			if (deepResearchWorkflow) {
				deepResearchConfig.DEEP_RESEARCH_ENDPOINT = deepResearchWorkflow.config?.endpoint_url || '';
				deepResearchConfig.ENABLE_DEEP_RESEARCH = deepResearchWorkflow.is_active;
			} else {
				deepResearchConfig.ENABLE_DEEP_RESEARCH = false;
				deepResearchConfig.DEEP_RESEARCH_ENDPOINT = '';
			}
		} catch (error) {
			console.error('Error loading Deep Research config:', error);
			toast.error('Failed to load Deep Research configuration');
		} finally {
			loading = false;
		}
	};

	const submitHandler = async () => {
		loading = true;
		try {
			const endpoint = deepResearchConfig.DEEP_RESEARCH_ENDPOINT.trim();
			const shouldBeActive = deepResearchConfig.ENABLE_DEEP_RESEARCH && endpoint !== '';

			console.log('[DeepResearch Settings] Saving config:', {
				ENABLE_DEEP_RESEARCH: deepResearchConfig.ENABLE_DEEP_RESEARCH,
				endpoint,
				shouldBeActive,
				existingWorkflow: deepResearchWorkflow?.id
			});

			if (!endpoint && deepResearchConfig.ENABLE_DEEP_RESEARCH) {
				toast.error('Please enter an endpoint URL to enable Deep Research');
				deepResearchConfig.ENABLE_DEEP_RESEARCH = false;
				loading = false;
				return;
			}

			if (deepResearchWorkflow) {
				const updateData: Partial<Workflow> = {
					name: 'Deep Research',
					workflow_type: 'deep_research' as const,
					config: {
						endpoint_url: endpoint,
						timeout: 300
					},
					is_active: shouldBeActive
				};
				console.log('[DeepResearch Settings] Updating workflow:', updateData);
				
				const updated = await updateWorkflowById(localStorage.token || '', deepResearchWorkflow.id, updateData);
				console.log('[DeepResearch Settings] Update response:', updated);

				deepResearchWorkflow = await findDeepResearchWorkflow();
				console.log('[DeepResearch Settings] Workflow after update:', deepResearchWorkflow);
			} else {
				if (!endpoint) {
					toast.error('Please enter an endpoint URL to create Deep Research workflow');
					deepResearchConfig.ENABLE_DEEP_RESEARCH = false;
					loading = false;
					return;
				}

				deepResearchWorkflow = await createNewWorkflow(localStorage.token || '', {
					name: 'Deep Research',
					description: 'Comprehensive research with multiple sources',
					workflow_type: 'deep_research',
					config: {
						endpoint_url: endpoint,
						timeout: 300
					},
					is_active: shouldBeActive
				});
			}

			if (shouldBeActive) {
				deepResearchConfig.ENABLE_DEEP_RESEARCH = true;
			} else {
				deepResearchConfig.ENABLE_DEEP_RESEARCH = false;
			}

			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error: any) {
			console.error('Error saving Deep Research config:', error);
			toast.error(error?.message || 'Failed to save Deep Research configuration');
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		loadConfig();
	});

	$: if (deepResearchConfig.ENABLE_DEEP_RESEARCH && !deepResearchConfig.DEEP_RESEARCH_ENDPOINT.trim()) {
		deepResearchConfig.ENABLE_DEEP_RESEARCH = false;
	}
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		await submitHandler();
		saveSettings();
	}}
>
	<div class=" space-y-3 overflow-y-scroll scrollbar-hidden h-full">
		<div class="">
			<div class="mb-3">
				<div class=" mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

				<hr class=" border-gray-100 dark:border-gray-850 my-2" />

				<div class="  mb-2.5 flex w-full justify-between">
					<div class=" self-center text-sm font-medium">
						{$i18n.t('Deep Research')}
					</div>
					<div class="flex items-center relative">
						<Switch bind:state={deepResearchConfig.ENABLE_DEEP_RESEARCH} />
					</div>
				</div>

				<div class="mb-2.5 flex w-full flex-col">
					<div>
						<div class=" self-center text-sm font-medium mb-1">
							{$i18n.t('Deep Research Endpoint')}
						</div>

							<div class="flex w-full">
								<div class="flex-1">
									<input
										class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
										type="text"
										placeholder={$i18n.t('Enter Deep Research Endpoint URL')}
										bind:value={deepResearchConfig.DEEP_RESEARCH_ENDPOINT}
										autocomplete="off"
										on:input={() => {
											// Auto-enable when user types endpoint URL
											if (deepResearchConfig.DEEP_RESEARCH_ENDPOINT.trim()) {
												deepResearchConfig.ENABLE_DEEP_RESEARCH = true;
											}
										}}
									/>
								</div>
							</div>
					</div>
				</div>
			</div>
		</div>
	</div>
	<div class="flex justify-end pt-3 text-base font-medium">
		<button
			class="px-3.5 py-1.5 text-base font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg disabled:opacity-50"
			type="submit"
			disabled={loading}
		>
			{loading ? $i18n.t('Saving...') : $i18n.t('Save')}
		</button>
	</div>
</form>
