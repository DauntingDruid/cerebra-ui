<script>
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	let loaded = false;
	let email = '';
	let type = 'signup'; // 'signup' or 'reset'
	let isResending = false;
	let message = '';
	let errorMessage = '';

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

	const handleResendEmail = async () => {
		errorMessage = '';
		message = '';
		isResending = true;

		try {
			// Choose endpoint based on type
			const endpoint = type === 'reset' 
				? '/api/v1/auths/forgot-password'
				: '/api/v1/auths/send-verification';

			const response = await fetch(`${WEBUI_BASE_URL}${endpoint}`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ email: email.toLowerCase().trim() })
			});

			const data = await response.json();

			if (response.ok) {
				message = type === 'reset' 
					? 'Password reset email has been resent!'
					: 'Verification email has been resent!';
			} else {
				errorMessage = data.detail || 'Failed to resend email. Please try again.';
			}
		} catch (error) {
			console.error('Resend email error:', error);
			errorMessage = 'An error occurred. Please try again.';
		} finally {
			isResending = false;
		}
	};

	onMount(async () => {
		loaded = true;
		setLogoImage();

		// Get parameters from URL
		const urlParams = new URLSearchParams(window.location.search);
		email = urlParams.get('email') || '';
		type = urlParams.get('type') || 'signup';
	});
</script>

<svelte:head>
	<title>{type === 'reset' ? 'Check your email' : 'Verify your email'}</title>
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

				<!-- Email Icon -->
				<div class="flex justify-center mb-8">
					<div class="w-16 h-16 bg-purple-600 rounded-full flex items-center justify-center">
						<svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
						</svg>
					</div>
				</div>

				<!-- Title -->
				<div class="text-center mb-4">
					<h1 class="text-2xl font-bold text-black dark:text-white">
						Check your email
					</h1>
				</div>

				<!-- Description -->
				<div class="text-center mb-8">
					<p class="text-gray-600 dark:text-gray-400">
						{#if type === 'reset'}
							We've sent a password reset link to your email address.
							Please check your inbox and click the link to reset your password.
						{:else}
							We've sent a verification link to your email address.
							Please check your inbox and click the link to verify your account.
						{/if}
					</p>
				</div>

				<!-- Success Message -->
				{#if message}
					<div class="mb-4 p-3 bg-green-100 dark:bg-green-900 border border-green-400 dark:border-green-700 text-green-700 dark:text-green-200 rounded-lg text-sm">
						{message}
					</div>
				{/if}

				<!-- Error Message -->
				{#if errorMessage}
					<div class="mb-4 p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-200 rounded-lg text-sm">
						{errorMessage}
					</div>
				{/if}

				<!-- Resend Button -->
				<div class="text-center mb-6">
					<button
						type="button"
						class="bg-purple-600 hover:bg-purple-700 text-white py-3 px-6 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						on:click={handleResendEmail}
						disabled={isResending || !email}
					>
						{isResending ? 'Sending...' : 'Resend email'}
					</button>
				</div>

				<!-- Test Button (for development) -->
				{#if type === 'reset'}
					<div class="text-center mb-6">
						<p class="text-sm text-gray-600 dark:text-gray-400 mb-3">
							For testing purposes, you can click the link below to proceed to password reset:
						</p>
						<button
							type="button"
							class="bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded-lg text-sm font-medium transition-colors"
							on:click={() => goto('/auth/reset-password/confirm?token=test-token')}
						>
							Continue to Password Reset
						</button>
					</div>
				{/if}

				<!-- Additional Info -->
				<div class="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
					<p>Didn't receive the email? Check your spam folder or try again.</p>
				</div>

				<!-- Back to Sign In Link -->
				<div class="text-center">
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