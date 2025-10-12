<script>
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	let loaded = false;
	let password = '';
	let confirmPassword = '';
	let passwordError = '';
	let confirmPasswordError = '';
	let isLoading = false;
	let errorMessage = '';
	let successMessage = '';
	let token = '';

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

	const handleSubmit = async (e) => {
		e.preventDefault();
		errorMessage = '';
		
		// Validate passwords
		const isPasswordValid = validatePassword();
		const isConfirmPasswordValid = validateConfirmPassword();
		
		if (!isPasswordValid || !isConfirmPasswordValid) {
			return;
		}

		if (!token) {
			errorMessage = 'Invalid or missing reset token. Please request a new password reset link.';
			return;
		}

		isLoading = true;

		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/auths/reset-password`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ 
					token: token,
					password: password 
				})
			});

			const data = await response.json();

			if (response.ok) {
				successMessage = data.message || 'Password reset successfully!';
				// Redirect to login after 2 seconds
				setTimeout(() => {
					goto('/auth/login');
				}, 2000);
			} else {
				errorMessage = data.detail || 'Failed to reset password. The link may have expired.';
			}
		} catch (error) {
			console.error('Reset password error:', error);
			errorMessage = 'An error occurred. Please try again or request a new reset link.';
		} finally {
			isLoading = false;
		}
	};

	onMount(async () => {
		loaded = true;
		setLogoImage();

		// Get token from URL query parameters
		const urlParams = new URLSearchParams(window.location.search);
		token = urlParams.get('token') || '';

		if (!token) {
			errorMessage = 'Invalid or missing reset token. Please request a new password reset link.';
		}
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

				<!-- Success Message -->
				{#if successMessage}
					<div class="mb-4 p-3 bg-green-100 dark:bg-green-900 border border-green-400 dark:border-green-700 text-green-700 dark:text-green-200 rounded-lg text-sm">
						{successMessage}
						<p class="mt-1 text-xs">Redirecting to login...</p>
					</div>
				{/if}

				<!-- Error Message -->
				{#if errorMessage}
					<div class="mb-4 p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-200 rounded-lg text-sm">
						{errorMessage}
					</div>
				{/if}

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
							disabled={isLoading || !!successMessage}
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
							disabled={isLoading || !!successMessage}
							on:blur={validateConfirmPassword}
						/>
						{#if confirmPasswordError}
							<p class="text-red-500 text-sm mt-1">{confirmPasswordError}</p>
						{/if}
					</div>

					<button
						type="submit"
						class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={isLoading || !!successMessage || !token}
					>
						{isLoading ? 'Resetting...' : 'Confirm'}
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