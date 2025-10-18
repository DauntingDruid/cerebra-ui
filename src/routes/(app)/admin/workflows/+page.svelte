<script lang="ts">
  import { onMount } from 'svelte';
  import { toast } from 'svelte-sonner';

  let workflows: any[] = [];
  let credentials: any[] = [];
  let showCreateModal: boolean = false;
  let showCredentialModal: boolean = false;
  let loading: boolean = false;

  // Form data
  let workflowForm: {
    name: string;
    description: string;
    workflow_type: string; // 'langflow' | 'n8n' | 'langchain' | 'custom'
    config: {
      endpoint_url: string;
      flow_id: string; // used for langflow; remapped to workflow_id for n8n
      timeout: number;
    };
    is_active: boolean;
  } = {
    name: '',
    description: '',
    workflow_type: 'langflow',
    config: {
      endpoint_url: '',
      flow_id: '',
      timeout: 300
    },
    is_active: true
  };

  let credentialForm: {
    service_name: string; // 'langflow' | 'n8n' | 'langchain' | 'custom' | etc.
    api_key: string;
    endpoint_url: string;
    additional_config: any;
  } = {
    service_name: 'langflow',
    api_key: '',
    endpoint_url: '',
    additional_config: {}
  };

  onMount(async () => {
    await loadWorkflows();
    await loadCredentials();
  });

  async function loadWorkflows() {
    try {
      const res = await fetch('/api/v1/workflows/', { credentials: 'include' });
      workflows = await res.json();
    } catch (error) {
      toast.error('Failed to load workflows');
    }
  }

  async function loadCredentials() {
    try {
      const res = await fetch('/api/v1/workflows/credentials/list', {
        credentials: 'include'
      });
      credentials = await res.json();
    } catch {
      toast.error('Failed to load credentials');
    }
  }

  // ===== Minimal mapping so all types work =====
  async function createWorkflow() {
    loading = true;
    try {
      // normalize endpoint url (trim trailing slashes)
      const endpoint = (workflowForm.config.endpoint_url || '').replace(/\/+$/, '');
      const cfg: any = { ...workflowForm.config, endpoint_url: endpoint };

      if (workflowForm.workflow_type === 'langflow') {
        // uses flow_id; no workflow_id
        delete cfg.workflow_id;
      } else if (workflowForm.workflow_type === 'n8n') {
        // n8n expects workflow_id -> rename from flow_id
        cfg.workflow_id = cfg.flow_id;
        delete cfg.flow_id;
      } else {
        // langchain/custom: no id field required
        delete cfg.flow_id;
        delete cfg.workflow_id;
      }

      const res = await fetch('/api/v1/workflows/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...workflowForm,
          config: cfg
        })
      });

      if (res.ok) {
        toast.success('Workflow created successfully');
        showCreateModal = false;
        await loadWorkflows();
        resetWorkflowForm();
      } else {
        const error = await res.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to create workflow');
      }
    } catch {
      toast.error('Failed to create workflow');
    } finally {
      loading = false;
    }
  }
  // ============================================

  async function createCredential() {
    loading = true;
    try {
      const body = {
        ...credentialForm,
        service_name: (credentialForm.service_name || '').toLowerCase(),
        endpoint_url: (credentialForm.endpoint_url || '').replace(/\/+$/, '')
      };

      const res = await fetch('/api/v1/workflows/credentials', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (res.ok) {
        toast.success('Credential saved successfully');
        showCredentialModal = false;
        await loadCredentials();
        resetCredentialForm();
      } else {
        const error = await res.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to save credential');
      }
    } catch {
      toast.error('Failed to save credential');
    } finally {
      loading = false;
    }
  }

  async function executeWorkflow(workflowId: string) {
    try {
      const res = await fetch(`/api/v1/workflows/${workflowId}/execute`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_data: { message: 'Test execution' }
        })
      });

      if (res.ok) {
        const execution = await res.json();
        toast.success(`Workflow execution started: ${execution.id}`);
      } else {
        const error = await res.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to execute workflow');
      }
    } catch {
      toast.error('Failed to execute workflow');
    }
  }

  async function deleteWorkflow(workflowId: string) {
    if (!confirm('Are you sure you want to delete this workflow?')) return;

    try {
      const res = await fetch(`/api/v1/workflows/${workflowId}`, {
        method: 'DELETE',
        credentials: 'include'
      });

      if (res.ok) {
        toast.success('Workflow deleted');
        await loadWorkflows();
      } else {
        const error = await res.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to delete workflow');
      }
    } catch {
      toast.error('Failed to delete workflow');
    }
  }

  function resetWorkflowForm() {
    workflowForm = {
      name: '',
      description: '',
      workflow_type: 'langflow',
      config: {
        endpoint_url: '',
        flow_id: '',
        timeout: 300
      },
      is_active: true
    };
  }

  function resetCredentialForm() {
    credentialForm = {
      service_name: 'langflow',
      api_key: '',
      endpoint_url: '',
      additional_config: {}
    };
  }
</script>

<div class="flex flex-col h-full p-6">
  <div class="mb-6 flex justify-between items-center">
    <div>
      <h1 class="text-2xl font-bold">AI Agent Workflows</h1>
      <p class="text-gray-600 dark:text-gray-400">Manage your AI workflow automations</p>
    </div>
    <div class="flex gap-2">
      <button
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        on:click={() => (showCredentialModal = true)}
      >
        Add Credentials
      </button>
      <button
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        on:click={() => (showCreateModal = true)}
      >
        Create Workflow
      </button>
    </div>
  </div>

  <!-- Credentials Section -->
  <div class="mb-6">
    <h2 class="text-xl font-semibold mb-3">Configured Credentials</h2>
    {#if credentials.length === 0}
      <p class="text-gray-500">No credentials configured yet.</p>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {#each credentials as cred}
          <div class="border dark:border-gray-700 rounded-lg p-4">
            <div class="font-semibold">{cred.service_name}</div>
            <div class="text-sm text-gray-600 dark:text-gray-400 truncate">
              {cred.endpoint_url || 'No endpoint'}
            </div>
            <div class="text-xs text-gray-500 mt-2">API Key: ••••••••</div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Workflows Section -->
  <div>
    <h2 class="text-xl font-semibold mb-3">Workflows</h2>
    {#if workflows.length === 0}
      <p class="text-gray-500">No workflows created yet.</p>
    {:else}
      <div class="space-y-4">
        {#each workflows as workflow}
          <div class="border dark:border-gray-700 rounded-lg p-4">
            <div class="flex justify-between items-start">
              <div class="flex-1">
                <h3 class="font-semibold text-lg">{workflow.name}</h3>
                <p class="text-sm text-gray-600 dark:text-gray-400">{workflow.description}</p>
                <div class="flex gap-2 mt-2">
                  <span class="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-xs rounded">
                    {workflow.workflow_type}
                  </span>
                  <span
                    class="px-2 py-1 text-xs rounded"
                    class:bg-green-100={workflow.is_active}
                    class:dark:bg-green-900={workflow.is_active}
                    class:text-green-800={workflow.is_active}
                    class:dark:text-green-200={workflow.is_active}
                    class:bg-gray-100={!workflow.is_active}
                    class:dark:bg-gray-800={!workflow.is_active}
                    class:text-gray-800={!workflow.is_active}
                    class:dark:text-gray-200={!workflow.is_active}
                  >
                    {workflow.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  class="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                  on:click={() => executeWorkflow(workflow.id)}
                >
                  Execute
                </button>
                <button
                  class="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
                  on:click={() => deleteWorkflow(workflow.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<!-- Create Workflow Modal -->
{#if showCreateModal}
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
      <h2 class="text-xl font-bold mb-4">Create New Workflow</h2>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">Name</label>
          <input
            type="text"
            bind:value={workflowForm.name}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            placeholder="My Workflow"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">Description</label>
          <textarea
            bind:value={workflowForm.description}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            rows="2"
            placeholder="What does this workflow do?"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">Type</label>
          <select
            bind:value={workflowForm.workflow_type}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
          >
            <option value="langflow">Langflow</option>
            <option value="n8n">n8n</option>
            <option value="langchain">LangChain</option>
            <option value="custom">Custom API</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">Endpoint URL</label>
          <input
            type="text"
            bind:value={workflowForm.config.endpoint_url}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            placeholder="https://api.example.com"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">
            {workflowForm.workflow_type === 'n8n'
              ? 'Webhook ID (n8n)'
              : workflowForm.workflow_type === 'langflow'
              ? 'Flow ID (LangFlow)'
              : 'ID (optional)'}
          </label>
          <input
            type="text"
            bind:value={workflowForm.config.flow_id}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            placeholder="flow-123"
          />
        </div>

        <div class="flex items-center">
          <input
            type="checkbox"
            bind:checked={workflowForm.is_active}
            class="mr-2"
            id="workflow-active"
          />
          <label for="workflow-active" class="text-sm">Active</label>
        </div>
      </div>

      <div class="flex gap-2 mt-6">
        <button
          class="flex-1 px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600"
          on:click={() => {
            showCreateModal = false;
            resetWorkflowForm();
          }}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          class="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          on:click={createWorkflow}
          disabled={loading}
        >
          {loading ? 'Creating...' : 'Create'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Add Credential Modal -->
{#if showCredentialModal}
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
      <h2 class="text-xl font-bold mb-4">Add Credentials</h2>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">Service Name</label>
          <select
            bind:value={credentialForm.service_name}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
          >
            <option value="langflow">Langflow</option>
            <option value="n8n">n8n</option>
            <option value="langchain">LangChain</option>
            <option value="custom">Custom</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">API Key</label>
          <input
            type="password"
            bind:value={credentialForm.api_key}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            placeholder="sk-..."
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1">Endpoint URL</label>
          <input
            type="text"
            bind:value={credentialForm.endpoint_url}
            class="w-full px-3 py-2 border dark:border-gray-700 rounded-lg dark:bg-gray-900"
            placeholder="https://api.example.com"
          />
        </div>
      </div>

      <div class="flex gap-2 mt-6">
        <button
          class="flex-1 px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600"
          on:click={() => {
            showCredentialModal = false;
            resetCredentialForm();
          }}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          on:click={createCredential}
          disabled={loading}
        >
          {loading ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  </div>
{/if}
