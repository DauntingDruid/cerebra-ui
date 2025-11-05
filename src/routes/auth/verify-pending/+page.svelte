<script>
	import { onMount, getContext, tick,onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { page } from '$app/stores';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, user } from '$lib/stores';

	const i18n = getContext('i18n');
	const AUTH = import.meta.env.VITE_BETTERAUTH_PUBLIC;

	let loaded = false;
	let email = '';
	let isResending = false;
	let errorMsg = '';

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

	// Resend verification email
	async function resendVerification() {
		if (!email) {
			toast.error('Email address is required');
			return;
		}

		isResending = true;
		errorMsg = '';

		try {
			const response = await fetch(`${AUTH}/api/auth/request-verification`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email: email.toLowerCase().trim() })
			});

			if (response.ok) {
				toast.success('Verification email resent! Please check your inbox.');
			} else {
				const data = await response.json();
				const error = data?.error || 'Failed to send verification email.';
				errorMsg = error;
				toast.error(error);
			}
		} catch (error) {
			console.error('Resend error:', error);
			const msg = error?.message || 'An error occurred. Please try again.';
			errorMsg = msg;
			toast.error(msg);
		} finally {
			isResending = false;
		}
	}

	let pollTimer;

    onMount(async () => {
        loaded = true;
        setLogoImage();

        const urlParams = new URLSearchParams(window.location.search);
        email = urlParams.get('email') || ($user && $user.email) || '';

        if (!email) {
            toast.error('Session expired. Please sign in again.');
            goto('/auth/login');
            return;
        }

        // Poll BetterAuth service for verification status
        const poll = async () => {
            try {
            const r = await fetch(`${AUTH}/api/auth/status?email=${encodeURIComponent(email)}`);
            const j = await r.json();
            if (j?.emailVerified === true) {
                toast.success('Email verified! Redirecting...');
                // optional: clear any stale token and go to login (or home)
                localStorage.removeItem('token');
                goto('/auth/login?verified=true');
            }
            } catch (e) {

            }
        };

    // initial check + interval
        poll();
        pollTimer = setInterval(poll, 4000);
    });

    onDestroy(() => {
        if (pollTimer) clearInterval(pollTimer);
    });
</script>

<svelte:head>
	<title>Account Verification Pending - {$WEBUI_NAME}</title>
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

				<!-- Alert Icon -->
				<div class="flex justify-center mb-8">
					<div class="w-20 h-20 bg-yellow-100 dark:bg-yellow-900/30 rounded-full flex items-center justify-center">
						<svg 
							class="w-10 h-10 text-yellow-600 dark:text-yellow-500" 
							fill="none" 
							stroke="currentColor" 
							viewBox="0 0 24 24"
						>
							<path 
								stroke-linecap="round" 
								stroke-linejoin="round" 
								stroke-width="2" 
								d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
							/>
						</svg>
					</div>
				</div>

				<!-- Title -->
				<div class="text-center mb-4">
					<h1 class="text-2xl font-bold text-black dark:text-white mb-2">
						Account Verification Pending
					</h1>
					<p class="text-gray-600 dark:text-gray-400">
						Please verify your email address to continue.
					</p>
				</div>

				<!-- Email Display -->
				<div class="text-center mb-8">
					<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">
						We sent a verification link to:
					</p>
					<p class="text-base font-medium text-gray-800 dark:text-gray-200">
						{email}
					</p>
					<p class="text-xs text-gray-500 dark:text-gray-500 mt-2">
						The link expires in 24 hours
					</p>
				</div>

				<!-- Instructions -->
				<div class="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-6 mb-6">
					<h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
						How to verify your email:
					</h3>
					<ol class="space-y-2 text-sm text-gray-600 dark:text-gray-400">
						<li class="flex items-start">
							<span class="mr-2 text-purple-600 dark:text-purple-400">1.</span>
							<span>Check your inbox for an email from CerebraUI</span>
						</li>
						<li class="flex items-start">
							<span class="mr-2 text-purple-600 dark:text-purple-400">2.</span>
							<span>Click the verification link in the email</span>
						</li>
						<li class="flex items-start">
							<span class="mr-2 text-purple-600 dark:text-purple-400">3.</span>
							<span>You'll be redirected back to sign in</span>
						</li>
					</ol>
				</div>

				<!-- Error Message -->
				{#if errorMsg}
					<div class="mb-4 p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-200 rounded-lg text-sm">
						{errorMsg}
					</div>
				{/if}

				<!-- Resend Button -->
				<button
					type="button"
					class="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white py-3 px-4 rounded-lg font-medium transition-colors mb-4"
					on:click={resendVerification}
					disabled={isResending}
				>
					{isResending ? 'Sending...' : 'Resend Verification Email'}
				</button>

				<!-- Help Text -->
				<div class="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
					<p>Didn't receive the email?</p>
					<p>Check your spam folder or use the button above to resend.</p>
				</div>

				<!-- Back to Sign In Link -->
				<div class="text-center">
					<button
						type="button"
						class="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 underline"
						on:click={() => {
							// Clear token if exists
							localStorage.removeItem('token');
							goto('/auth/login');
						}}
					>
						Back to Sign In
					</button>
				</div>
			{/if}
		</div>
	</div>
</div>