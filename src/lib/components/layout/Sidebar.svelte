<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { v4 as uuidv4 } from 'uuid';

	import { goto } from '$app/navigation';
	import {
		user,
		chats,
		settings,
		showSettings,
		chatId,
		tags,
		showSidebar,
		mobile,
		showArchivedChats,
		pinnedChats,
		scrollPaginationEnabled,
		currentChatPage,
		temporaryChatEnabled,
		channels,
		socket,
		config,
		isApp
	} from '$lib/stores';
	import { onMount, getContext, tick, onDestroy } from 'svelte';

	const i18n: any = getContext('i18n');

	import {
		deleteChatById,
		getChatList,
		getAllTags,
		getChatListBySearchText,
		createNewChat,
		getPinnedChatList,
		toggleChatPinnedStatusById,
		getChatPinnedStatusById,
		getChatById,
		updateChatFolderIdById,
		importChat
	} from '$lib/apis/chats';
	import { createNewFolder, getFolders, updateFolderParentIdById } from '$lib/apis/folders';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import ArchivedChatsModal from './Sidebar/ArchivedChatsModal.svelte';
	import UserMenu from './Sidebar/UserMenu.svelte';
	import ChatItem from './Sidebar/ChatItem.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Loader from '../common/Loader.svelte';
	import AddFilesPlaceholder from '../AddFilesPlaceholder.svelte';
	import SearchInput from './Sidebar/SearchInput.svelte';
	import Folder from '../common/Folder.svelte';
	import Plus from '../icons/Plus.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import Folders from './Sidebar/Folders.svelte';
	import { getChannels, createNewChannel } from '$lib/apis/channels';
	import ChannelModal from './Sidebar/ChannelModal.svelte';
	import ChannelItem from './Sidebar/ChannelItem.svelte';
	import PencilSquare from '../icons/PencilSquare.svelte';
	import Home from '../icons/Home.svelte';
	
	// Icon components
	import CerebraLogo from '$lib/components/icons/CerebraLogo.svelte';
	import ModelsIcon from '$lib/components/icons/ModelsIcon.svelte';
	import PromptsIcon from '$lib/components/icons/PromptsIcon.svelte';
	import KnowledgeIcon from '$lib/components/icons/KnowledgeIcon.svelte';
	import ToolsIcon from '$lib/components/icons/ToolsIcon.svelte';
	import PlaygroundIcon from '$lib/components/icons/PlaygroundIcon.svelte';
	import WorkflowIcon from '$lib/components/icons/WorkflowIcon.svelte';
	import SearchIcon from '$lib/components/icons/SearchIcon.svelte';
	import UserIcon from '$lib/components/icons/UserIcon.svelte';

	const BREAKPOINT = 768;

	let navElement;
	let search = '';

	let shiftKey = false;
	let selectedChatId: string | null = null;
	let showDropdown = false;
	let showPinnedChat = true;
	let showCreateChannel = false;

	let chatListLoading = false;
	let allChatsLoaded = false;

	let folders: Record<string, any> = {};
	let newFolderId: string | null = null;

	const initFolders = async () => {
		const folderList = await getFolders(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return [] as any[];
		});

		folders = {};

		for (const folder of folderList) {
			folders[folder.id] = { ...(folders[folder.id] || {}), ...folder };

			if (newFolderId && folder.id === newFolderId) {
				folders[folder.id].new = true;
				newFolderId = null;
			}
		}

		for (const folder of folderList) {
			if (folder.parent_id) {
				if (!folders[folder.parent_id]) {
					folders[folder.parent_id] = {};
				}
				folders[folder.parent_id].childrenIds = folders[folder.parent_id].childrenIds
					? [...folders[folder.parent_id].childrenIds, folder.id]
					: [folder.id];

				folders[folder.parent_id].childrenIds.sort((a, b) => {
					return folders[b].updated_at - folders[a].updated_at;
				});
			}
		}
	};

	const createFolder = async (name = 'Untitled') => {
		if (name === '') {
			toast.error($i18n.t('Folder name cannot be empty.'));
			return;
		}

		const rootFolders = Object.values(folders).filter((folder: any) => folder.parent_id === null);
		if (rootFolders.find((f: any) => f.name.toLowerCase() === name.toLowerCase())) {
			let i = 1;
			while (rootFolders.find((f: any) => f.name.toLowerCase() === `${name} ${i}`.toLowerCase())) {
				i++;
			}
			name = `${name} ${i}`;
		}

		const tempId = uuidv4();
		folders = {
			...folders,
			tempId: {
				id: tempId,
				name,
				created_at: Date.now(),
				updated_at: Date.now()
			}
		};

		const res = await createNewFolder(localStorage.token, name).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			newFolderId = res.id;
			await initFolders();
		}
	};

	const initChannels = async () => {
		await channels.set(await getChannels(localStorage.token));
	};

	const initChatList = async () => {
		tags.set(await getAllTags(localStorage.token));
		pinnedChats.set(await getPinnedChatList(localStorage.token));
		initFolders();

		currentChatPage.set(1);
		allChatsLoaded = false;

		if (search) {
			await chats.set(await getChatListBySearchText(localStorage.token, search, $currentChatPage));
		} else {
			await chats.set(await getChatList(localStorage.token, $currentChatPage));
		}

		scrollPaginationEnabled.set(true);
	};

	const loadMoreChats = async () => {
		chatListLoading = true;
		currentChatPage.set($currentChatPage + 1);

		let newChatList: any[] = [];
		if (search) {
			newChatList = await getChatListBySearchText(localStorage.token, search, $currentChatPage);
		} else {
			newChatList = await getChatList(localStorage.token, $currentChatPage);
		}

		allChatsLoaded = newChatList.length === 0;
		await chats.set([...($chats ? $chats : []), ...newChatList]);
		chatListLoading = false;
	};

	let searchDebounceTimeout: any;
	const searchDebounceHandler = async () => {
		console.log('search', search);
		chats.set(null);

		if (searchDebounceTimeout) clearTimeout(searchDebounceTimeout);

		if (search === '') {
			await initChatList();
			return;
		} else {
			searchDebounceTimeout = setTimeout(async () => {
				allChatsLoaded = false;
				currentChatPage.set(1);
				await chats.set(await getChatListBySearchText(localStorage.token, search));

				if ($chats.length === 0) {
					tags.set(await getAllTags(localStorage.token));
				}
			}, 1000);
		}
	};

	const importChatHandler = async (items, pinned = false, folderId: string | null = null) => {
		console.log('importChatHandler', items, pinned, folderId);
		for (const item of items) {
			if (item.chat) {
				await importChat(localStorage.token, item.chat, item?.meta ?? {}, pinned, folderId);
			}
		}
		initChatList();
	};

	const inputFilesHandler = async (files: File[]) => {
		for (const file of files) {
			const reader = new FileReader();
			reader.onload = async (e) => {
				const content = (e.target as any).result;
				try {
					const chatItems = JSON.parse(content);
					importChatHandler(chatItems);
				} catch {
					toast.error($i18n.t(`Invalid file format.`));
				}
			};
			reader.readAsText(file);
		}
	};

	const tagEventHandler = async (type, tagName, chatId) => {
		if (type === 'delete' || type === 'add') {
			initChatList();
		}
	};

	let draggedOver = false;
	const onDragOver = (e: DragEvent) => {
		e.preventDefault();
		draggedOver = !!e.dataTransfer?.types?.includes('Files');
	};
	const onDragLeave = () => {
		draggedOver = false;
	};
	const onDrop = async (e: DragEvent) => {
		e.preventDefault();
		if (e.dataTransfer?.files) {
			const inputFiles = Array.from(e.dataTransfer.files);
			if (inputFiles.length > 0) inputFilesHandler(inputFiles);
		}
		draggedOver = false;
	};

	let touchstart: Touch; let touchend: Touch;
	function checkDirection() {
		const screenWidth = window.innerWidth;
		const swipeDistance = Math.abs(touchend.screenX - touchstart.screenX);
		if (touchstart.clientX < 40 && swipeDistance >= screenWidth / 8) {
			if (touchend.screenX < touchstart.screenX) showSidebar.set(false);
			if (touchend.screenX > touchstart.screenX) showSidebar.set(true);
		}
	}
	const onTouchStart = (e: TouchEvent) => { touchstart = e.changedTouches[0]; };
	const onTouchEnd = (e: TouchEvent) => { touchend = e.changedTouches[0]; checkDirection(); };

	const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Shift') shiftKey = true; };
	const onKeyUp = (e: KeyboardEvent) => { if (e.key === 'Shift') shiftKey = false; };
	const onFocus = () => {};
	const onBlur = () => { shiftKey = false; selectedChatId = null; };

	onMount(async () => {
		showPinnedChat = localStorage?.showPinnedChat ? localStorage.showPinnedChat === 'true' : true;

		mobile.subscribe((value) => {
			if ($showSidebar && value) {
				showSidebar.set(false);
			}
			if ($showSidebar && !value) {
				const navElement = document.getElementsByTagName('nav')[0];
				if (navElement) navElement.style['-webkit-app-region'] = 'drag';
			}
			if (!$showSidebar && !value) {
				showSidebar.set(true);
			}
		});

		showSidebar.set(!$mobile ? localStorage.sidebar === 'true' : false);
		showSidebar.subscribe((value) => {
			localStorage.sidebar = String(value);
			const navElement = document.getElementsByTagName('nav')[0];
			if (navElement) {
				if ($mobile) {
					navElement.style['-webkit-app-region'] = value ? 'no-drag' : 'drag';
				} else {
					navElement.style['-webkit-app-region'] = 'drag';
				}
			}
		});

		await initChannels();
		await initChatList();

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('touchstart', onTouchStart);
		window.addEventListener('touchend', onTouchEnd);
		window.addEventListener('focus', onFocus);
		window.addEventListener('blur-sm', onBlur);

		const dropZone = document.getElementById('sidebar');
		dropZone?.addEventListener('dragover', onDragOver);
		dropZone?.addEventListener('drop', onDrop);
		dropZone?.addEventListener('dragleave', onDragLeave);
	});

	onDestroy(() => {
		window.removeEventListener('keydown', onKeyDown);
		window.removeEventListener('keyup', onKeyUp);
		window.removeEventListener('touchstart', onTouchStart);
		window.removeEventListener('touchend', onTouchEnd);
		window.removeEventListener('focus', onFocus);
		window.removeEventListener('blur-sm', onBlur);
		const dropZone = document.getElementById('sidebar');
		dropZone?.removeEventListener('dragover', onDragOver);
		dropZone?.removeEventListener('drop', onDrop);
		dropZone?.removeEventListener('dragleave', onDragLeave);
	});
</script>

<ArchivedChatsModal
	bind:show={$showArchivedChats}
	on:change={async () => {
		await initChatList();
	}}
/>

<ChannelModal
	bind:show={showCreateChannel}
	onSubmit={async ({ name, access_control }) => {
		const res = await createNewChannel(localStorage.token, {
			name: name,
			access_control: access_control
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			$socket.emit('join-channels', { auth: { token: $user?.token } });
			await initChannels();
			showCreateChannel = false;
		}
	}}
/>

<!-- svelte-ignore a11y-no-static-element-interactions -->

{#if $showSidebar}
	<div
		class=" {$isApp
			? ' ml-[4.5rem] md:ml-0'
			: ''} fixed md:hidden z-40 top-0 right-0 left-0 bottom-0 bg-black/60 w-full min-h-screen h-screen flex justify-center overflow-hidden overscroll-contain"
		on:mousedown={() => {
			showSidebar.set(!$showSidebar);
		}}
	/>
{/if}

<div
	bind:this={navElement}
	id="sidebar"
	class="h-screen max-h-[100dvh] min-h-screen select-none {$showSidebar
		? 'md:relative w-[260px] max-w-[260px]'
		: '-translate-x-[260px] w-[0px]'} {$isApp
		? `ml-[4.5rem] md:ml-0 `
		: 'transition-width duration-200 ease-in-out'}  shrink-0 bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-200 text-sm fixed z-50 top-0 left-0 overflow-x-hidden
        "
	data-state={$showSidebar}
>
	<div
		class="py-2 my-auto flex flex-col justify-between h-screen max-h-[100dvh] w-[260px] overflow-x-hidden z-50 {$showSidebar
			? ''
			: 'invisible'}"
	>
		<div class="px-1.5 flex items-center justify-between space-x-1 text-gray-600 dark:text-gray-400 sticky top-0 z-10 bg-gray-50/80 dark:bg-gray-950/80 backdrop-blur-xl">
			<button
				class=" flex items-center rounded-xl px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-900 transition"
				on:click={() => {

					showSidebar.set(!$showSidebar);
				}}
				aria-label="Toggle Sidebar"
			>
                <!-- Cerebra Logo (PNG with theme switching) -->
                <CerebraLogo className=" size-10 mr-2" />
				<span class=" font-semibold text-xl">CerebraUI</span>
			</button>

			<a
				id="sidebar-new-chat-button"
				class="flex items-center rounded-lg px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-900 transition no-drag-region"
				href="/"
				draggable="false"
				on:click={async () => {
					selectedChatId = null;
					await goto('/');
					const newChatButton = document.getElementById('new-chat-button');
					setTimeout(() => {
						newChatButton?.click();
						if ($mobile) {
							showSidebar.set(false);
						}
					}, 0);
				}}
				aria-label="New Chat"
			>
				<PencilSquare className=" size-5 text-gray-900 dark:text-white" strokeWidth="2" />
			</a>
		</div>

		<!-- {#if $user?.role === 'admin'}
			<div class="px-1.5 flex justify-center text-gray-800 dark:text-gray-200">
				<a
					class="grow flex items-center space-x-3 rounded-lg px-2 py-[7px] hover:bg-gray-100 dark:hover:bg-gray-900 transition"
					href="/home"
					on:click={() => {
						selectedChatId = null;
						chatId.set('');

						if ($mobile) {
							showSidebar.set(false);
						}
					}}
					draggable="false"
				>
					<div class="self-center">
						<Home strokeWidth="2" className="size-[1.1rem]" />
					</div>

					<div class="flex self-center translate-y-[0.5px]">
						<div class=" self-center font-medium text-sm font-primary">{$i18n.t('Home')}</div>
					</div>
				</a>
			</div>
		{/if} -->


		<div class="relative mt-4{$temporaryChatEnabled ? 'opacity-20' : ''}">
			{#if $temporaryChatEnabled}
				<div class="absolute z-40 w-full h-full flex justify-center"></div>
			{/if}

			<SearchInput
				bind:value={search}
				on:input={searchDebounceHandler}
				placeholder={$i18n.t('Search')}
				showClearButton={true}
			/>
		</div>

		<div
			class="relative flex flex-col flex-1 overflow-y-auto overflow-x-hidden {$temporaryChatEnabled
				? 'opacity-20'
				: ''}"
		>
			<!-- Features Section (collapsible like Chats) -->
			<Folder
				collapsible={!search}
				className="px-2 mt-4"
				name={$i18n.t('Features')}
				dragAndDrop={false}
			>
				<div class="flex flex-col gap-1 pb-1">
					{#if $user?.role === 'admin' || $user?.permissions?.workspace?.models}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/workspace/models" draggable="false">
							<ModelsIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Models')}</span>
						</a>
					{/if}

					{#if $user?.role === 'admin' || $user?.permissions?.workspace?.prompts}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/workspace/prompts" draggable="false">
							<PromptsIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Prompts')}</span>
						</a>
					{/if}

					{#if $user?.role === 'admin' || $user?.permissions?.workspace?.knowledge}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/workspace/knowledge" draggable="false">
							<KnowledgeIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Knowledge')}</span>
						</a>
					{/if}

					{#if $user?.role === 'admin' || $user?.permissions?.workspace?.tools}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/workspace/tools" draggable="false">
							<ToolsIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Tools')}</span>
						</a>
					{/if}

					{#if $user?.role === 'admin' || $user?.permissions?.workspace?.workflows}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/workspace/workflows" draggable="false">
							<WorkflowIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Workflows')}</span>
						</a>
					{/if}

					{#if $user?.role === 'admin'}
						<a class="flex items-center gap-2 rounded-lg px-2 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-900 transition" href="/playground" draggable="false">
							<PlaygroundIcon className=" size-5 text-gray-900 dark:text-white" strokeWidth="1.8" />
							<span class=" text-sm">{$i18n.t('Playground')}</span>
						</a>
					{/if}
				</div>
			</Folder>
			{#if $config?.features?.enable_channels && ($user?.role === 'admin' || $channels.length > 0) && !search}
				<Folder
					className="px-2 mt-0.5"
					name={$i18n.t('Channels')}
					dragAndDrop={false}
					onAdd={async () => {
						if ($user?.role === 'admin') {
							await tick();

							setTimeout(() => {
								showCreateChannel = true;
							}, 0);
						}
					}}
					onAddLabel={$i18n.t('Create Channel')}
				>
					{#each $channels as channel}
						<ChannelItem
							{channel}
							onUpdate={async () => {
								await initChannels();
							}}
						/>
					{/each}
				</Folder>
			{/if}

			<Folder
				collapsible={!search}
				className="px-2 mt-4"
				name={$i18n.t('Chats')}
				onAdd={() => {
					createFolder();
				}}
				onAddLabel={$i18n.t('New Folder')}
				on:import={(e) => {
					importChatHandler(e.detail);
				}}
				on:drop={async (e) => {
					const { type, id, item } = e.detail;

					if (type === 'chat') {
						let chat = await getChatById(localStorage.token, id).catch((error) => {
							return null;
						});
						if (!chat && item) {
							chat = await importChat(localStorage.token, item.chat, item?.meta ?? {});
						}

						if (chat) {
							console.log(chat);
							if (chat.folder_id) {
								const res = await updateChatFolderIdById(localStorage.token, chat.id, null).catch(
									(error) => {
										toast.error(`${error}`);
										return null;
									}
								);
							}

							if (chat.pinned) {
								const res = await toggleChatPinnedStatusById(localStorage.token, chat.id);
							}

							initChatList();
						}
					} else if (type === 'folder') {
						if (folders[id].parent_id === null) {
							return;
						}

						const res = await updateFolderParentIdById(localStorage.token, id, null).catch(
							(error) => {
								toast.error(`${error}`);
								return null;
							}
						);

						if (res) {
							await initFolders();
						}
					}
				}}
			>
				{#if $temporaryChatEnabled}
					<div class="absolute z-40 w-full h-full flex justify-center"></div>
				{/if}

				{#if !search && $pinnedChats.length > 0}
					<div class="flex flex-col space-y-1 rounded-xl">
						<Folder
							className=""
							bind:open={showPinnedChat}
							on:change={(e) => {
								localStorage.setItem('showPinnedChat', e.detail);
								console.log(e.detail);
							}}
							on:import={(e) => {
								importChatHandler(e.detail, true);
							}}
							on:drop={async (e) => {
								const { type, id, item } = e.detail;

								if (type === 'chat') {
									let chat = await getChatById(localStorage.token, id).catch((error) => {
										return null;
									});
									if (!chat && item) {
										chat = await importChat(localStorage.token, item.chat, item?.meta ?? {});
									}

									if (chat) {
										console.log(chat);
										if (chat.folder_id) {
											const res = await updateChatFolderIdById(
												localStorage.token,
												chat.id,
												null
											).catch((error) => {
												toast.error(`${error}`);
												return null;
											});
										}

										if (!chat.pinned) {
											const res = await toggleChatPinnedStatusById(localStorage.token, chat.id);
										}

										initChatList();
									}
								}
							}}
							name={$i18n.t('Pinned')}
						>
							<div
								class="ml-3 pl-1 mt-[1px] flex flex-col overflow-y-auto scrollbar-hidden border-s border-gray-100 dark:border-gray-900"
							>
								{#each $pinnedChats as chat, idx}
									<ChatItem
										className=""
										id={chat.id}
										title={chat.title}
										{shiftKey}
										selected={selectedChatId === chat.id}
										on:select={() => {
											selectedChatId = chat.id;
										}}
										on:unselect={() => {
											selectedChatId = null;
										}}
										on:change={async () => {
											initChatList();
										}}
										on:tag={(e) => {
											const { type, name } = e.detail;
											tagEventHandler(type, name, chat.id);
										}}
									/>
								{/each}
							</div>
						</Folder>
					</div>
				{/if}

				{#if !search && folders}
					<Folders
						{folders}
						on:import={(e) => {
							const { folderId, items } = e.detail;
							importChatHandler(items, false, folderId);
						}}
						on:update={async (e) => {
							initChatList();
						}}
						on:change={async () => {
							initChatList();
						}}
					/>
				{/if}

				<div class=" flex-1 flex flex-col overflow-y-auto scrollbar-hidden">
					<div class="pt-1.5">
						{#if $chats}
							{#each $chats as chat, idx}
								{#if idx === 0 || (idx > 0 && chat.time_range !== $chats[idx - 1].time_range)}
									<div
										class="w-full pl-2.5 text-xs text-gray-500 dark:text-gray-500 font-medium {idx ===
										0
											? ''
											: 'pt-5'} pb-1.5"
									>
										{$i18n.t(chat.time_range)}
										<!-- localisation keys for time_range to be recognized from the i18next parser (so they don't get automatically removed):
							{$i18n.t('Today')}
							{$i18n.t('Yesterday')}
							{$i18n.t('Previous 7 days')}
							{$i18n.t('Previous 30 days')}
							{$i18n.t('January')}
							{$i18n.t('February')}
							{$i18n.t('March')}
							{$i18n.t('April')}
							{$i18n.t('May')}
							{$i18n.t('June')}
							{$i18n.t('July')}
							{$i18n.t('August')}
							{$i18n.t('September')}
							{$i18n.t('October')}
							{$i18n.t('November')}
							{$i18n.t('December')}
							-->
									</div>
								{/if}

								<ChatItem
									className=""
									id={chat.id}
									title={chat.title}
									{shiftKey}
									selected={selectedChatId === chat.id}
									on:select={() => {
										selectedChatId = chat.id;
									}}
									on:unselect={() => {
										selectedChatId = null;
									}}
									on:change={async () => {
										initChatList();
									}}
									on:tag={(e) => {
										const { type, name } = e.detail;
										tagEventHandler(type, name, chat.id);
									}}
								/>
							{/each}

							{#if $scrollPaginationEnabled && !allChatsLoaded}
								<Loader
									on:visible={(e) => {
										if (!chatListLoading) {
											loadMoreChats();
										}
									}}
								>
									<div
										class="w-full flex justify-center py-1 text-xs animate-pulse items-center gap-2"
									>
										<Spinner className=" size-4" />
										<div class=" ">Loading...</div>
									</div>
								</Loader>
							{/if}
						{:else}
							<div class="w-full flex justify-center py-1 text-xs animate-pulse items-center gap-2">
								<Spinner className=" size-4" />
								<div class=" ">Loading...</div>
							</div>
						{/if}
					</div>
				</div>
			</Folder>
		</div>

		<!-- Separator line above Settings -->
		<hr class="border-gray-200 dark:border-gray-700 mx-2 my-4" />

		<div class="px-2">
			<!-- Bottom Settings button: open Settings modal -->
			<button
				class="flex items-center rounded-xl py-2.5 px-2.5 w-full hover:bg-gray-100 dark:hover:bg-gray-900 transition mb-1"
				on:click={async () => {
					await showSettings.set(true);
					if ($mobile) {
						showSidebar.set(false);
					}
				}}
			>
				<div class=" self-center mr-2">
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" class="size-5"><path stroke-linecap="round" stroke-linejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.893.149c-.425.07-.765.383-.93.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.397.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.273-.806.108-1.204-.165-.397-.505-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.107-1.204l-.527-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
				</div>
				<div class=" self-center font-medium text-sm">{$i18n.t('Settings')}</div>
			</button>
			<div class="flex flex-col font-primary">
				{#if $user !== undefined && $user !== null}
					<UserMenu
						role={$user?.role}
						on:show={(e) => {
							if (e.detail === 'archived-chat') {
								showArchivedChats.set(true);
							}
						}}
					>
						<button
							class=" flex items-center rounded-xl py-2.5 px-2.5 w-full hover:bg-gray-100 dark:hover:bg-gray-900 transition"
							on:click={() => {
								showDropdown = !showDropdown;
							}}
						>
							<div class=" self-center mr-2">
								{#if $user?.profile_image_url}
									<img
										src={$user?.profile_image_url}
										class="size-5 object-cover rounded-full bg-white"
										alt="User profile"
										onerror="this.style.display='none'; this.nextElementSibling.style.display='block'"
									/>
									<div class="size-5 bg-white rounded-full flex items-center justify-center" style="display: none;">
										<UserIcon className="size-5 text-gray-700" strokeWidth="1.8" />
									</div>
								{:else}
									<div class="size-5 bg-white rounded-full flex items-center justify-center">
										<UserIcon className="size-5 text-gray-700" strokeWidth="1.8" />
									</div>
								{/if}
							</div>
							<div class=" self-center font-medium text-sm">{$user?.name}</div>
						</button>
					</UserMenu>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.scrollbar-hidden:active::-webkit-scrollbar-thumb,
	.scrollbar-hidden:focus::-webkit-scrollbar-thumb,
	.scrollbar-hidden:hover::-webkit-scrollbar-thumb { visibility: visible; }
	.scrollbar-hidden::-webkit-scrollbar-thumb { visibility: hidden; }
</style>
