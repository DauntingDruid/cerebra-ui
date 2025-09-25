<script lang="ts">
	import Switch from '$lib/components/common/Switch.svelte';
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	const i18n = getContext('i18n');

	export let saveSettings: Function;

	// 静态配置，不依赖后端
	let deepResearchConfig = {
		ENABLE_DEEP_RESEARCH: true, // 默认开启
		DEEP_RESEARCH_ENDPOINT: 'https://api.example.com/deep-research'
	};

	const submitHandler = async () => {
		// 保存到localStorage，不调用后端
		localStorage.setItem('deepResearchConfig', JSON.stringify(deepResearchConfig));
		toast.success($i18n.t('Settings saved successfully!'));
	};

	onMount(() => {
		// 从localStorage加载配置
		const saved = localStorage.getItem('deepResearchConfig');
		if (saved) {
			try {
				deepResearchConfig = { ...deepResearchConfig, ...JSON.parse(saved) };
			} catch (error) {
				console.error('Error loading saved config:', error);
			}
		}
	});
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
					<div class=" self-center text-base font-medium">
						{$i18n.t('Deep Research')}
					</div>
					<div class="flex items-center relative">
						<Switch bind:state={deepResearchConfig.ENABLE_DEEP_RESEARCH} />
					</div>
				</div>

				{#if deepResearchConfig.ENABLE_DEEP_RESEARCH}
					<div class="mb-2.5 flex w-full flex-col">
						<div>
							<div class=" self-center text-base font-medium mb-1">
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
									/>
								</div>
							</div>
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
	<div class="flex justify-end pt-3 text-base font-medium">
		<button
			class="px-3.5 py-1.5 text-base font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
