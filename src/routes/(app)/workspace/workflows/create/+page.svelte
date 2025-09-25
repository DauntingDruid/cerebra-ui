<!-- 
<script lang="ts">
	import { onMount } from 'svelte';
	import WorkflowEditor from '$lib/components/workspace/Workflows/WorkflowEditor.svelte';

	let workflow = null;

	onMount(() => {
		// Check if we're cloning a workflow
		if (sessionStorage.workflow) {
			try {
				workflow = JSON.parse(sessionStorage.workflow);
				// Clear session storage
				sessionStorage.removeItem('workflow');
			} catch (error) {
				console.error('Error parsing workflow from session storage:', error);
			}
		}
	});
</script>

<WorkflowEditor {workflow} />
-->

<!-- Workflow创建页面已暂时注释掉 -->
<div class="flex items-center justify-center py-12">
	<div class="text-center">
		<h3 class="text-lg font-medium text-gray-900 dark:text-white mb-2">Workflow创建功能已暂时禁用</h3>
		<p class="text-gray-500 dark:text-gray-400">请联系管理员启用此功能</p>
	</div>
</div>
