<script lang="ts">
  import { onMount } from 'svelte';
  import { toast } from 'svelte-sonner';

  export let onWorkflowSelect: (workflowId: string, workflowName: string) => void;
  export let show: boolean = false;

  let workflows: any[] = [];
  let loading = false;

  onMount(async () => {
    await loadWorkflows();
  });

  async function loadWorkflows() {
    loading = true;
    try {
      const res = await fetch('/api/v1/workflows/', {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        workflows = data.filter((w: any) => w.is_active);
      } else {
        toast.error('Failed to load workflows');
      }
    } catch (error) {
      console.error('Failed to load workflows:', error);
      toast.error('Failed to load workflows');
    } finally {
      loading = false;
    }
  }

  function selectWorkflow(workflow: any) {
    onWorkflowSelect(workflow.id, workflow.name);
  }
</script>

{#if show}
  <div class="absolute bottom-full left-0 mb-2 w-full max-w-md z-50">
    <div
      class="bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div class="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Select AI Workflow
        </div>
      </div>

      {#if loading}
        <div class="p-6 text-center">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-sm text-gray-500">Loading workflows...</p>
        </div>
      {:else if workflows.length === 0}
        <div class="p-6 text-center text-gray-500">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-12 w-12 mx-auto mb-3 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p class="text-sm font-medium">No active workflows available</p>
          <p class="text-xs mt-1">Create a workflow in Admin → Workflows</p>
        </div>
      {:else}
        <div class="max-h-80 overflow-y-auto">
          {#each workflows as workflow}
            <button
              class="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-b-0"
              on:click={() => selectWorkflow(workflow)}
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                    {workflow.name}
                  </div>
                  {#if workflow.description}
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                      {workflow.description}
                    </div>
                  {/if}
                  <div class="flex gap-2 mt-2">
                    <span
                      class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200"
                    >
                      {workflow.workflow_type}
                    </span>
                    {#if workflow.is_active}
                      <span
                        class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                      >
                        Active
                      </span>
                    {/if}
                  </div>
                </div>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="h-5 w-5 text-gray-400 ml-2 flex-shrink-0"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fill-rule="evenodd"
                    d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                    clip-rule="evenodd"
                  />
                </svg>
              </div>
            </button>
          {/each}
        </div>
      {/if}

      <div class="px-4 py-3 bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
        <a
          href="/workspace/workflows"
          class="text-xs text-[#A855F7] hover:text-[#9333EA] dark:text-[#A855F7] dark:hover:text-[#9333EA] hover:underline"
        >
          Manage Workflows →
        </a>
      </div>
    </div>
  </div>
{/if}

<style>
  .line-clamp-2 {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
</style>
