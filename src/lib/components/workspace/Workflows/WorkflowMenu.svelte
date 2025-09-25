<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext } from 'svelte';
	import { goto } from '$app/navigation';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import ArrowDownTray from '../../icons/ArrowDownTray.svelte';
	import Pencil from '../../icons/Pencil.svelte';
	import GarbageBin from '../../icons/GarbageBin.svelte';
	import Heart from '../../icons/Heart.svelte';
	import ChevronRight from '../../icons/ChevronRight.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let workflow: any;
	export let onShare: (workflow: any) => void;
	export let onClone: (workflow: any) => void;
	export let onExport: (workflow: any) => void;
	export let onDelete: (workflow: any) => void;
	export let onClose: Function = () => {};

	let show = false;

	const handleShare = () => {
		onShare(workflow);
		show = false;
	};

	const handleClone = () => {
		onClone(workflow);
		show = false;
	};

	const handleExport = () => {
		onExport(workflow);
		show = false;
	};

	const handleDelete = () => {
		onDelete(workflow);
		show = false;
	};

	const handleEdit = () => {
		goto(`/workspace/workflows/edit?id=${workflow.id}`);
		show = false;
	};
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[160px] rounded-xl px-1 py-1.5 border border-gray-300/30 dark:border-gray-700/50 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={-2}
			side="bottom"
			align="start"
			transition={flyAndScale}
		>
			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={handleEdit}
			>
				<Pencil className="size-4" />
				<div class="flex items-center">{$i18n.t('Edit')}</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={handleClone}
			>
				<ChevronRight className="size-4" />
				<div class="flex items-center">{$i18n.t('Clone')}</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={handleExport}
			>
				<ArrowDownTray className="size-4" />
				<div class="flex items-center">{$i18n.t('Export')}</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={handleShare}
			>
				<Heart className="size-4" />
				<div class="flex items-center">{$i18n.t('Share')}</div>
			</DropdownMenu.Item>

			<hr class="border-gray-100 dark:border-gray-850 my-1" />

			<DropdownMenu.Item
				class="flex gap-2 items-center px-3 py-2 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={handleDelete}
			>
				<GarbageBin strokeWidth="2" />
				<div class="flex items-center">{$i18n.t('Delete')}</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
