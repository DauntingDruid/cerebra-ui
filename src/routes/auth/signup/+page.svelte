<script>
	import { toast } from 'svelte-sonner';
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';

	import { WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME } from '$lib/stores';

	const i18n = getContext('i18n');
	const AUTH = import.meta.env.VITE_BETTERAUTH_PUBLIC;

	let loaded = false;
	let name = '';
	let email = '';
	let password = '';

	let sending = false;
	let sent = false;
	let errorMsg = '';
	let isResending = false;

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

	const signUpHandler = async () => {
		sending = true;
		errorMsg = '';
		try {
			// 1) Create user in BetterAuth
			const r = await fetch(`${AUTH}/api/auth/signup`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, email, password })
			});
			const data = await r.json().catch(() => ({}));
			if (!r.ok) throw new Error(data?.error || 'Sign up failed');

			// 2) Send verification email
			const v = await fetch(`${AUTH}/api/auth/request-verification`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email })
			});
			const vdata = await v.json().catch(() => ({}));
			if (!v.ok) throw new Error(vdata?.error || 'Could not send verification email');

			toast.success('Verification link sent. Please check your email.');
			sent = true;
		} catch (e) {
			errorMsg = e?.message ?? 'Something went wrong';
			toast.error(errorMsg);
		} finally {
			sending = false;
		}
	};

	const handleResendEmail = async () => {
		isResending = true;
		errorMsg = '';
		
		try {
			const response = await fetch(`${AUTH}/api/auth/request-verification`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email })
			});

			if (response.ok) {
				toast.success('Verification email resent! Please check your inbox.');
			} else {
				const data = await response.json();
				throw new Error(data?.error || 'Failed to resend email');
			}
		} catch (error) {
			errorMsg = error.message;
			toast.error(errorMsg);
		} finally {
			isResending = false;
		}
	};

	onMount(async () => {
		loaded = true;
		setLogoImage();
	});
</script>

<svelte:head>
	<title>Create your free account</title>
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

				{#if !sent}
					<!-- Title -->
					<div class="text-center mb-8">
						<h1 class="text-2xl font-bold text-black dark:text-white">
							Create your free account
						</h1>
					</div>

					<!-- Signup Form -->
					<form
						class="space-y-6"
						on:submit={(e) => {
							e.preventDefault();
							signUpHandler();
						}}
					>
						<div>
							<label for="name" class="block text-sm font-medium text-black dark:text-white mb-2">
								Name
							</label>
							<input
								id="name"
								bind:value={name}
								type="text"
								class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none"
								placeholder="Enter your full name"
								required
							/>
						</div>

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
							/>
						</div>

						<div>
							<label for="password" class="block text-sm font-medium text-black dark:text-white mb-2">
								Password
							</label>
							<input
								id="password"
								bind:value={password}
								type="password"
								class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none"
								placeholder="Enter your password"
								required
							/>
						</div>

						{#if errorMsg}
							<p class="text-sm text-red-400">{errorMsg}</p>
						{/if}

						<button
							type="submit"
							class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
							disabled={sending}
						>
							{sending ? 'Sending…' : 'Sign Up'}
						</button>
					</form>

					<!-- Sign In Link -->
					<div class="text-center mt-6">
						<span class="text-sm text-gray-600 dark:text-gray-400">
							Already have an account?
						</span>
						<button
							type="button"
							class="ml-1 text-sm text-[#A855F7] hover:text-[#9333EA] dark:text-[#A855F7] dark:hover:text-[#9333EA] font-medium"
							on:click={() => goto('/auth/login')}
						>
							Sign In
						</button>
					</div>
				{:else}
					<div class="text-center space-y-6">
						<!-- Email Icon -->
						<div class="flex justify-center mb-4">
							<div class="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
								<svg class="w-8 h-8 text-green-600 dark:text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
								</svg>
							</div>
						</div>

						<h1 class="text-2xl font-bold text-black dark:text-white">Check your email</h1>
						
						<p class="text-sm text-gray-600 dark:text-gray-400">
							We sent a verification link to<br />
							<span class="font-medium text-gray-800 dark:text-gray-200">{email}</span>
						</p>
						
						<p class="text-sm text-gray-600 dark:text-gray-400">
							Please check your inbox (and spam folder).<br />
							The link expires in 24 hours.
						</p>
						
						{#if errorMsg}
							<div class="p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-200 rounded-lg text-sm">
								{errorMsg}
							</div>
						{/if}

						<div class="pt-2">
							<button
								type="button"
								class="w-full bg-purple-600 hover:bg-purple-700 text-white py-3 px-4 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
								on:click={handleResendEmail}
								disabled={isResending}
							>
								{isResending ? 'Sending...' : 'Resend Verification Email'}
							</button>
						</div>

						<div class="pt-2">
							<button 
								type="button"
								class="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 underline" 
								on:click={() => goto('/auth/login')}
							>
								Back to Sign In
							</button>
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</div>