<script lang="ts">
  import { onMount } from 'svelte';
  import { toast } from 'svelte-sonner';
  import Search from '$lib/components/icons/Search.svelte';
  import Plus from '$lib/components/icons/Plus.svelte';
  import Pencil from '$lib/components/icons/Pencil.svelte';
  import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
  import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
  import Tooltip from '$lib/components/common/Tooltip.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
  import { deleteCredential, updateCredential } from '$lib/apis/workflows';

  let workflows: any[] = [];
  let credentials: any[] = [];
  let showCreateModal: boolean = false;
  let showCredentialModal: boolean = false;
  let loading: boolean = false;
  let query = '';
  let shiftKey = false;
  let editingWorkflow: any = null;
  let isEditMode = false;
  let editingCredential: any = null;
  let isCredentialEditMode = false;
  let showDeleteConfirm = false;
  let selectedWorkflow: any = null;
  let showDeleteCredentialConfirm = false;
  let selectedCredential: any = null;

  // Filtered items
  let filteredWorkflows = [];
  let filteredCredentials = [];
  $: filteredWorkflows = workflows.filter(
    (w) =>
      // Hide deep_research workflows as they are managed in Settings
      w.workflow_type !== 'deep_research' &&
      (query === '' ||
      w.name.toLowerCase().includes(query.toLowerCase()) ||
      w.workflow_type.toLowerCase().includes(query.toLowerCase()) ||
      (w.description && w.description.toLowerCase().includes(query.toLowerCase())))
  );
  $: filteredCredentials = credentials.filter(
    (c) =>
      query === '' ||
      c.service_name.toLowerCase().includes(query.toLowerCase()) ||
      (c.endpoint_url && c.endpoint_url.toLowerCase().includes(query.toLowerCase()))
  );

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

  onMount(() => {
    loadWorkflows();
    loadCredentials();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Shift') {
        shiftKey = true;
      }
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === 'Shift') {
        shiftKey = false;
      }
    };

    const onBlur = () => {
      shiftKey = false;
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur-sm', onBlur);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur-sm', onBlur);
    };
  });

  async function loadWorkflows() {
    try {
      const res = await fetch('/api/v1/workflows/', { credentials: 'include' });
      if (res.ok) {
        workflows = await res.json();
      } else {
        toast.error('Failed to load workflows');
      }
    } catch (error) {
      toast.error('Failed to load workflows');
    }
  }

  async function loadCredentials() {
    try {
      const res = await fetch('/api/v1/workflows/credentials/list', {
        credentials: 'include'
      });
      if (res.ok) {
        credentials = await res.json();
      } else {
        toast.error('Failed to load credentials');
      }
    } catch {
      toast.error('Failed to load credentials');
    }
  }

  // ===== Minimal mapping so all types work =====
  async function createWorkflow() {
    loading = true;
    try {
      // Validate required fields
      if (!workflowForm.name || !workflowForm.name.trim()) {
        toast.error('Workflow name is required');
        loading = false;
        return;
      }

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

  async function updateCredentialHandler() {
    loading = true;
    try {
      const body: any = {
        service_name: (credentialForm.service_name || '').toLowerCase(),
        endpoint_url: (credentialForm.endpoint_url || '').replace(/\/+$/, ''),
        additional_config: credentialForm.additional_config || {}
      };
      
      // Only include api_key if it's not empty
      if (credentialForm.api_key && credentialForm.api_key.trim()) {
        body.api_key = credentialForm.api_key;
      }

      await updateCredential(editingCredential.id, body);
      toast.success('Credential updated successfully');
      showCredentialModal = false;
      await loadCredentials();
      resetCredentialForm();
    } catch (error: any) {
      console.error('Failed to update credential:', error);
      toast.error(error?.message || 'Failed to update credential');
    } finally {
      loading = false;
    }
  }

  function editCredential(credential: any) {
    editingCredential = credential;
    isCredentialEditMode = true;
    
    credentialForm = {
      service_name: credential.service_name,
      api_key: '',
      endpoint_url: credential.endpoint_url || '',
      additional_config: credential.additional_config || {}
    };
    showCredentialModal = true;
  }

  async function deleteCredentialHandler(credential: any) {
    try {
      const res = await deleteCredential(credential.id).catch((error) => {
        toast.error(`${error}`);
        return null;
      });

      if (res) {
        toast.success('Credential deleted successfully');
        await loadCredentials();
      }
    } catch {
      toast.error('Failed to delete credential');
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

  async function deleteWorkflow(workflow: any) {
    try {
      const res = await fetch(`/api/v1/workflows/${workflow.id}`, {
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

  function editWorkflow(workflow: any) {
    editingWorkflow = workflow;
    isEditMode = true;
    
    // Handle ID mapping for different workflow types
    let config = workflow.config || {
      endpoint_url: '',
      flow_id: '',
      timeout: 300
    };
    
    // For n8n, map workflow_id back to flow_id for the form
    if (workflow.workflow_type === 'n8n' && config.workflow_id && !config.flow_id) {
      config = { ...config, flow_id: config.workflow_id };
    }
    
    // Populate form with workflow data
    workflowForm = {
      name: workflow.name,
      description: workflow.description || '',
      workflow_type: workflow.workflow_type,
      config: config,
      is_active: workflow.is_active
    };
    showCreateModal = true;
  }

  async function updateWorkflow() {
    loading = true;
    try {
      // Validate required fields
      if (!workflowForm.name || !workflowForm.name.trim()) {
        toast.error('Workflow name is required');
        loading = false;
        return;
      }

      const endpoint = (workflowForm.config.endpoint_url || '').replace(/\/+$/, '');
      const cfg: any = { ...workflowForm.config, endpoint_url: endpoint };

      if (workflowForm.workflow_type === 'langflow') {
        delete cfg.workflow_id;
      } else if (workflowForm.workflow_type === 'n8n') {
        cfg.workflow_id = cfg.flow_id;
        delete cfg.flow_id;
      } else {
        delete cfg.flow_id;
        delete cfg.workflow_id;
      }

      const res = await fetch(`/api/v1/workflows/${editingWorkflow.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: workflowForm.name,
          description: workflowForm.description,
          workflow_type: workflowForm.workflow_type,
          config: cfg,
          is_active: workflowForm.is_active
        })
      });

      if (res.ok) {
        toast.success('Workflow updated successfully');
        showCreateModal = false;
        await loadWorkflows();
        resetWorkflowForm();
      } else {
        const error = await res.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to update workflow');
      }
    } catch {
      toast.error('Failed to update workflow');
    } finally {
      loading = false;
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
    editingWorkflow = null;
    isEditMode = false;
  }

  function resetCredentialForm() {
    credentialForm = {
      service_name: 'langflow',
      api_key: '',
      endpoint_url: '',
      additional_config: {}
    };
    editingCredential = null;
    isCredentialEditMode = false;
  }
</script>

<div class="flex flex-col gap-6 mt-1.5 mb-8">
  <div class="flex justify-between items-center">
    <div class="flex items-center md:self-center text-2xl font-semibold px-0.5">
      AI Agent Workflows
    </div>
  </div>

  <div class="flex items-center w-full space-x-5">
    <div class="flex items-center w-64 rounded-lg bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition">
      <div class="self-center ml-3 mr-2">
        <Search className="size-5" />
      </div>
      <input
        class="w-full text-sm px-3 py-3 rounded-lg outline-hidden bg-transparent"
        bind:value={query}
        placeholder="Search"
      />
    </div>

    <div class="flex items-center space-x-2">
      <button
        class="flex text-sm items-center space-x-1 px-3 py-3 rounded-lg bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition"
        on:click={() => (showCredentialModal = true)}
      >
        <div class="self-center mr-2 font-medium line-clamp-1">Add Credentials</div>
        <div class="self-center">
          <Plus className="size-5" />
        </div>
      </button>
      <button
        class="flex text-sm items-center space-x-1 px-3 py-3 rounded-lg bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition"
        on:click={() => (showCreateModal = true)}
      >
        <div class="self-center mr-2 font-medium line-clamp-1">Create Workflow</div>
        <div class="self-center">
          <Plus className="size-5" />
        </div>
      </button>
    </div>
  </div>
</div>

<!-- Credentials Section -->
<div class="mb-6">
  <h2 class="text-xl font-semibold mb-3 flex items-center gap-2">
    Configured Credentials
    <div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
    <span class="text-lg font-medium text-gray-500 dark:text-gray-300">{filteredCredentials.length}</span>
  </h2>
  {#if filteredCredentials.length === 0}
    <p class="text-gray-500">No credentials configured yet.</p>
  {:else}
    <div class="my-6 mb-5 gap-5 grid lg:grid-cols-2 xl:grid-cols-3">
      {#each filteredCredentials as cred}
        <div class="flex flex-col cursor-pointer w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 dark:hover:bg-gray-700 hover:bg-gray-100 transition">
          <div class="flex flex-col w-full overflow-hidden mt-0.5 mb-0.5">
            <div class="text-left w-full">
              <div class="flex flex-col w-full overflow-hidden">
                <div class="flex items-center gap-2 mb-1">
                  <div class="text-xs font-bold px-1 rounded-sm uppercase line-clamp-1 bg-gray-500/20 text-gray-700 dark:text-gray-200">
                    {cred.service_name}
                  </div>
                </div>
                
                <div class="flex items-center gap-2 mb-1">
                  <div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 flex-1">
                    {cred.endpoint_url || 'No endpoint'}
                  </div>
                </div>

                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">
                  API Key: ••••••••
                </div>
              </div>
            </div>

            <div class="flex justify-end items-center -mb-0.5 px-0.5 mt-1">
              <div class="flex flex-row gap-0.5 items-center">
                <Tooltip content="Edit">
                  <button
                    class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
                    type="button"
                    on:click|stopPropagation={() => editCredential(cred)}
                  >
                    <Pencil className="w-4 h-4" strokeWidth="1.5" />
                  </button>
                </Tooltip>
                <Tooltip content="Delete">
                  <button
                    class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
                    type="button"
                    on:click|stopPropagation={() => {
                      selectedCredential = cred;
                      showDeleteCredentialConfirm = true;
                    }}
                  >
                    <GarbageBin className="w-4 h-4" strokeWidth="1.5" />
                  </button>
                </Tooltip>
              </div>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Workflows Section -->
<div class="mb-5">
  <h2 class="text-xl font-semibold mb-3 flex items-center gap-2">
    Workflows
    <div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-50 dark:bg-gray-850" />
    <span class="text-lg font-medium text-gray-500 dark:text-gray-300">{filteredWorkflows.length}</span>
  </h2>
  {#if filteredWorkflows.length === 0}
    <p class="text-gray-500">No workflows created yet.</p>
  {:else}
    <div class="my-6 mb-5 gap-5 grid lg:grid-cols-2 xl:grid-cols-3">
      {#each filteredWorkflows as workflow}
        <div class="flex flex-col cursor-pointer w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 dark:hover:bg-gray-700 hover:bg-gray-100 transition">
          <div class="flex flex-col w-full overflow-hidden mt-0.5 mb-0.5">
            <div class="text-left w-full">
              <div class="flex flex-col w-full overflow-hidden">
                <div class="flex items-center gap-2 mb-1">
                  <div class="text-base font-medium line-clamp-1 text-gray-900 dark:text-gray-100">
                    {workflow.name}
                  </div>
                </div>
                
                <div class="flex items-center gap-2 mb-1">
                  <div class="text-xs font-bold px-1 rounded-sm uppercase line-clamp-1 bg-gray-500/20 text-gray-700 dark:text-gray-200">
                    {workflow.workflow_type}
                  </div>
                  <div class="text-xs text-gray-400 dark:text-gray-500 line-clamp-1 flex-1">
                    {workflow.description || 'No description'}
                  </div>
                </div>
              </div>
            </div>

            <div class="flex justify-end items-center -mb-0.5 px-0.5 mt-1">
              <div class="flex flex-row gap-0.5 items-center">
                {#if shiftKey}
                  <Tooltip content="Delete">
                    <button
                      class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
                      type="button"
                      on:click|stopPropagation={() => {
                        selectedWorkflow = workflow;
                        showDeleteConfirm = true;
                      }}
                    >
                      <GarbageBin className="w-4 h-4" strokeWidth="1.5" />
                    </button>
                  </Tooltip>
                {:else}
                  <Tooltip content="Edit">
                    <button
                      class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
                      type="button"
                      on:click|stopPropagation={() => editWorkflow(workflow)}
                    >
                      <Pencil className="w-4 h-4" strokeWidth="1.5" />
                    </button>
                  </Tooltip>
                  <Tooltip content="Delete">
                    <button
                      class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
                      type="button"
                      on:click|stopPropagation={() => {
                        selectedWorkflow = workflow;
                        showDeleteConfirm = true;
                      }}
                    >
                      <GarbageBin className="w-4 h-4" strokeWidth="1.5" />
                    </button>
                  </Tooltip>
                {/if}
              </div>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Create Workflow Modal -->
{#if showCreateModal}
  <div class="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
    <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
      <h2 class="text-xl font-bold mb-6">{isEditMode ? 'Edit Workflow' : 'Create New Workflow'}</h2>

      <form on:submit|preventDefault={isEditMode ? updateWorkflow : createWorkflow}>
        <div class="w-full flex flex-col gap-5">
        <div class="w-full grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="w-full">
            <div class="text-sm mb-2">Name</div>
            <div class="w-full mt-1">
              <input
                type="text"
                bind:value={workflowForm.name}
                class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
                placeholder="My Workflow"
                required
              />
            </div>
          </div>

          <div class="w-full">
            <div class="text-sm mb-2">Type</div>
            <div class="w-full mt-1">
              <select
                bind:value={workflowForm.workflow_type}
                class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
              >
                <option value="langflow">Langflow</option>
                <option value="n8n">n8n</option>
                <option value="langchain">LangChain</option>
                <option value="custom">Custom API</option>
              </select>
            </div>
          </div>
        </div>

        <div class="w-full">
          <div class="text-sm mb-2">Description</div>
          <div class="w-full mt-1">
            <textarea
              bind:value={workflowForm.description}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden resize-none"
              rows="2"
              placeholder="What does this workflow do?"
            />
          </div>
        </div>

        <div class="w-full">
          <div class="text-sm mb-2">Endpoint URL</div>
          <div class="w-full mt-1">
            <input
              type="text"
              bind:value={workflowForm.config.endpoint_url}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
              placeholder="https://api.example.com"
              required
            />
          </div>
        </div>

        <div class="w-full">
          <div class="text-sm mb-2">
            {workflowForm.workflow_type === 'n8n'
              ? 'Webhook ID (n8n)'
              : workflowForm.workflow_type === 'langflow'
              ? 'Flow ID (LangFlow)'
              : 'ID (optional)'}
          </div>
          <div class="w-full mt-1">
            <input
              type="text"
              bind:value={workflowForm.config.flow_id}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
              placeholder="flow-123"
            />
          </div>
        </div>

        <div class="w-full flex items-center mt-1">
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
        </div>

        <div class="flex justify-center mt-8">
          <div class="flex gap-2 w-full">
            <button
              type="button"
              class="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 font-medium text-sm"
              on:click={() => {
                showCreateModal = false;
                resetWorkflowForm();
              }}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              class="flex-1 px-4 py-3 bg-gray-800 dark:bg-gray-700 text-white rounded-lg font-medium text-sm hover:bg-gray-900 dark:hover:bg-gray-600 disabled:opacity-50"
              disabled={loading}
            >
              {loading ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update' : 'Create')}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Add Credential Modal -->
{#if showCredentialModal}
  <div class="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
    <div class="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
      <h2 class="text-xl font-bold mb-6">{isCredentialEditMode ? 'Edit Credential' : 'Add Credentials'}</h2>

      <div class="w-full flex flex-col gap-5">
        <div class="w-full">
          <div class="text-sm mb-2">Service Name</div>
          <div class="w-full mt-1">
            <select
              bind:value={credentialForm.service_name}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
            >
              <option value="langflow">Langflow</option>
              <option value="n8n">n8n</option>
              <option value="langchain">LangChain</option>
              <option value="custom">Custom</option>
            </select>
          </div>
        </div>

        <div class="w-full">
          <div class="text-sm mb-2">API Key</div>
          <div class="w-full mt-1">
            <input
              type="password"
              bind:value={credentialForm.api_key}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
              placeholder="sk-..."
            />
          </div>
        </div>

        <div class="w-full">
          <div class="text-sm mb-2">Endpoint URL</div>
          <div class="w-full mt-1">
            <input
              type="text"
              bind:value={credentialForm.endpoint_url}
              class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
              placeholder="https://api.example.com"
            />
          </div>
        </div>
      </div>

      <div class="flex justify-center mt-8">
        <div class="flex gap-2 w-full">
          <button
            class="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 font-medium text-sm"
            on:click={() => {
              showCredentialModal = false;
              resetCredentialForm();
            }}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            class="flex-1 px-4 py-3 bg-gray-800 dark:bg-gray-700 text-white rounded-lg font-medium text-sm hover:bg-gray-900 dark:hover:bg-gray-600 disabled:opacity-50"
            on:click={isCredentialEditMode ? updateCredentialHandler : createCredential}
            disabled={loading}
          >
            {loading ? (isCredentialEditMode ? 'Updating...' : 'Saving...') : (isCredentialEditMode ? 'Update' : 'Save')}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Delete Workflow Confirmation Dialog -->
<ConfirmDialog
  bind:show={showDeleteConfirm}
  title="Delete workflow?"
  on:confirm={() => {
    deleteWorkflow(selectedWorkflow);
  }}
>
  <div class="text-sm text-gray-500">
    This will delete <span class="font-semibold">{selectedWorkflow?.name}</span>.
  </div>
</ConfirmDialog>

<!-- Delete Credential Confirmation Dialog -->
<ConfirmDialog
  bind:show={showDeleteCredentialConfirm}
  title="Delete credential?"
  on:confirm={() => {
    deleteCredentialHandler(selectedCredential);
  }}
>
  <div class="text-sm text-gray-500">
    This will delete the credential for <span class="font-semibold">{selectedCredential?.service_name}</span>.
  </div>
</ConfirmDialog>
