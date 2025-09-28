<script>
    import { tab } from '$lib/stores';  # Assume tab store or use Svelte tabs
    let n8nKey = '', langflowKey = '';
    let n8nStatus = '', langflowStatus = '';

    async function saveKey(service, key) {
        const response = await fetch('/agents/key', {
            method: 'POST',
            body: JSON.stringify({ service, key }),
            headers: {'Content-Type': 'application/json'}
        });
        if (response.ok) alert(`${service} key saved`);
    }

    async function testKey(service) {
        const response = await fetch(`/agents/test/${service}`);
        const data = await response.json();
        if (service === "n8n") n8nStatus = data.status;
        else langflowStatus = data.status;
    }
</script>

<div class="tabs">
    <button on:click={() => tab = 'n8n'}>n8n</button>
    <button on:click={() => tab = 'langflow'}>LangFlow</button>
</div>

{#if tab === 'n8n'}
    <input bind:value={n8nKey} placeholder="n8n API Key" />
    <button on:click={() => saveKey('n8n', n8nKey)}>Save</button>
    <button on:click={() => testKey('n8n')}>Test</button>
    <p>Status: {n8nStatus}</p>
{:else if tab === 'langflow'}
    <input bind:value={langflowKey} placeholder="LangFlow API Key" />
    <button on:click={() => saveKey('langflow', langflowKey)}>Save</button>
    <button on:click={() => testKey('langflow')}>Test</button>
    <p>Status: {langflowStatus}</p>
{/if}