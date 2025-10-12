<script>
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	let loaded = false;
	let email = '';
	let isLoading = false;
	let errorMessage = '';
	let emailSent = false;

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

	const sendResetEmail = async () => {
		console.log("sendResetEmail CALLED with email:", email);
		errorMessage = '';
		isLoading = true;

		try {
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/auths/forgot-password`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ email: email.toLowerCase().trim() })
			});

			const data = await response.json();

			if (response.ok) {
				emailSent = true;
			} else {
				errorMessage = data.detail || 'Failed to send reset email. Please try again.';
			}
		} catch (error) {
			console.error('Forgot password error:', error);
			errorMessage = 'An error occurred. Please try again.';
		} finally {
			isLoading = false;
		}
	};

	const handleSubmit = (e) => {
		e.preventDefault();
		sendResetEmail();
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

				{#if !emailSent}
					<!-- Initial State: Email Input Form -->
					<div class="text-center mb-8">
						<h1 class="text-2xl font-bold text-black dark:text-white">
							Reset your password
						</h1>
					</div>

					<!-- Error Message -->
					{#if errorMessage}
						<div class="mb-4 p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-200 rounded-lg text-sm">
							{errorMessage}
						</div>
					{/if}

					<!-- Reset Form -->
					<form class="space-y-6" on:submit={handleSubmit}>
						<div>
							<label for="email" class="block text-sm font-medium text-black dark:text-white mb-2">
								Email
							</label>
							<input
								id="email"
								bind:value={email}
								type="email"
								class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none"
								placeholder="Enter your email"
								required
								disabled={isLoading}
							/>
						</div>

						<button
							type="submit"
							class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
							disabled={isLoading}
						>
							{isLoading ? 'Sending...' : 'Send Email'}
						</button>
					</form>
				{:else}
					<!-- Success State: Email Sent Confirmation -->
					<div class="flex justify-center mb-8">
						<div class="w-16 h-16 bg-purple-600 rounded-full flex items-center justify-center">
							<svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
							</svg>
						</div>
					</div>

					<div class="text-center mb-4">
						<h1 class="text-2xl font-bold text-black dark:text-white">
							Check your email
						</h1>
					</div>

					<div class="text-center mb-8">
						<p class="text-gray-600 dark:text-gray-400">
							We've sent a password reset link to <strong>{email}</strong>.
							Please check your inbox and click the link to reset your password.
						</p>
					</div>

					<!-- Resend Button -->
					<button
						type="button"
						class="w-full bg-purple-600 hover:bg-purple-700 text-white py-3 px-4 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed mb-4"
						on:click={sendResetEmail}
						disabled={isLoading}
					>
						{isLoading ? 'Sending...' : 'Resend email'}
					</button>

					<div class="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
						<p>Didn't receive the email? Check your spam folder or try again.</p>
					</div>

					<!-- Change Email Button -->
					<button
						type="button"
						class="w-full text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
						on:click={() => emailSent = false}
					>
						Use a different email
					</button>
				{/if}

				<!-- Back to Sign In Link (always visible) -->
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