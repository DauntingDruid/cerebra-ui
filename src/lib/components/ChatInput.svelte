<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { user } from '$lib/stores/user';
  import { post } from '$lib/utils/api';

  const dispatch = createEventDispatcher();

  let inputValue = '';
  let fileInput;
  let fileInfo = null;

  async function handleSend() {
    if (!inputValue.trim() && !fileInfo) return;
    const token = get(user)?.token;
    let body = { messages: [{ role: 'user', content: inputValue }] };
    if (fileInfo) {
      body.file_info = fileInfo;
    }
    const response = await post('/api/chat/completions', body, token);
    dispatch('send', response);
    inputValue = '';
    fileInfo = null; // Reset after sending
  }

  async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    const token = get(user)?.token;
    try {
      const response = await post('/api/chat/upload', formData, token, { headers: { 'Content-Type': 'multipart/form-data' } });
      fileInfo = response.data; // Store {filename, content} from upload response
      console.log('File uploaded:', fileInfo);
    } catch (error) {
      console.error('Upload failed:', error);
    }
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }
</script>

<div class="chat-input">
  <input
    type="text"
    bind:value={inputValue}
    on:keydown={handleKeydown}
    placeholder="Type your message..."
    class="input-field"
  />
  <input type="file" bind:this={fileInput} on:change={handleFileUpload} class="file-input" />
  <button on:click={handleSend} class="send-button">Send</button>
</div>

<style>
  .chat-input {
    display: flex;
    gap: 10px;
    padding: 10px;
    background: var(--background-color);
    border-top: 1px solid var(--border-color);
  }
  .input-field {
    flex-grow: 1;
    padding: 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--input-background);
    color: var(--text-color);
  }
  .file-input {
    display: none; /* Hidden by default, triggered by label */
  }
  .send-button {
    padding: 8px 16px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  .send-button:hover {
    background: var(--primary-color-dark);
  }
</style>