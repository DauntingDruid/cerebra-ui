<script>
    import Svelvet from 'svelvet';
    let graph = { nodes: [], edges: [] };

    async function fetchFlows(service) {
        const response = await fetch(`/agents/test/${service}`);
        return (await response.json()).data;  # Flows/workflows list
    }

    async function saveGraph() {
        await fetch('/agents/save-agent', {
            method: 'POST',
            body: JSON.stringify(graph),
            headers: {'Content-Type': 'application/json'}
        });
        alert("Graph saved");
    }
</script>

<Svelvet bind:graph>  # Add nodes dynamically, e.g., "n8n Node" with flow_id dropdown from fetchFlows('n8n')
</Svelvet>
<button on:click={saveGraph}>Save Workflow</button>