<script>
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	let loaded = false;
	let password = '';
	let confirmPassword = '';
	let passwordError = '';
	let confirmPasswordError = '';

	async function setLogoImage() {
		await tick();
		const logo = document.getElementById('logo');

		if (logo) {
			const isDarkMode = document.documentElement.classList.contains('dark');

			if (isDarkMode) {
				const darkImage = new Image();
				darkImage.src = '/static/favicon-dark.png';

				darkImage.onload = () => {
					logo.src = '/static/favicon-dark.png';
					logo.style.filter = '';
				};

				darkImage.onerror = () => {
					logo.style.filter = 'invert(1)';
				};
			}
		}
	}

	function validatePassword() {
		passwordError = '';
		if (password.length < 6) {
			passwordError = 'Password must be at least 6 characters long';
			return false;
		}
		return true;
	}

	function validateConfirmPassword() {
		confirmPasswordError = '';
		if (confirmPassword !== password) {
			confirmPasswordError = 'Passwords do not match';
			return false;
		}
		return true;
	}

	const handleSubmit = (e) => {
		e.preventDefault();
		
		// 验证密码
		const isPasswordValid = validatePassword();
		const isConfirmPasswordValid = validateConfirmPassword();
		
		if (isPasswordValid && isConfirmPasswordValid) {
			// TODO: 这里应该调用重置密码的API
			// 现在先静态跳转到主页
			goto('/');
		}
	};

	onMount(async () => {
		loaded = true;
		setLogoImage();
	});
</script>

<svelte:head>
	<title>Reset your password</title>
</svelte:head>

<div class="w-full h-screen max-h-[100dvh] bg-white dark:bg-black">
	<div class="w-full h-full flex items-center justify-center">
		<div class="w-full max-w-md px-8">
			{#if loaded}
				<!-- Logo -->
				<div class="flex justify-center mb-8">
					<img
						id="logo"
						crossorigin="anonymous"
						src="{WEBUI_BASE_URL}/static/splash.png"
						class="w-16 h-16 rounded-full"
						alt="logo"
					/>
				</div>

				<!-- Title -->
				<div class="text-center mb-8">
					<h1 class="text-2xl font-bold text-black dark:text-white">
						Reset your password
					</h1>
				</div>

				<!-- Reset Form -->
				<form class="space-y-6" on:submit={handleSubmit}>
					<div>
						<label for="password" class="block text-sm font-medium text-black dark:text-white mb-2">
							Reset your password
						</label>
						<input
							id="password"
							bind:value={password}
							type="password"
							class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none {passwordError ? 'border-red-500' : ''}"
							placeholder="Enter new password"
							required
							on:blur={validatePassword}
						/>
						{#if passwordError}
							<p class="text-red-500 text-sm mt-1">{passwordError}</p>
						{/if}
					</div>

					<div>
						<label for="confirm-password" class="block text-sm font-medium text-black dark:text-white mb-2">
							Confirm your password
						</label>
						<input
							id="confirm-password"
							bind:value={confirmPassword}
							type="password"
							class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none {confirmPasswordError ? 'border-red-500' : ''}"
							placeholder="Confirm new password"
							required
							on:blur={validateConfirmPassword}
						/>
						{#if confirmPasswordError}
							<p class="text-red-500 text-sm mt-1">{confirmPasswordError}</p>
						{/if}
					</div>

					<button
						type="submit"
						class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors"
					>
						Confirm
					</button>
				</form>

				<!-- Back to Sign In Link -->
				<div class="text-center mt-6">
					<button
						type="button"
						class="text-sm text-[#A855F7] hover:text-[#9333EA] dark:text-[#A855F7] dark:hover:text-[#9333EA] font-medium"
						on:click={() => goto('/auth/login')}
					>
						Back to Sign In
					</button>
				</div>
			{/if}
		</div>
	</div>
</div>
