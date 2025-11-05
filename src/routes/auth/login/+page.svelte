<script>
	import { toast } from 'svelte-sonner';
	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { getBackendConfig } from '$lib/apis';
	import { getSessionUser } from '$lib/apis/auths';

	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, config, user, socket } from '$lib/stores';

	const i18n = getContext('i18n');

	let loaded = false;
	let email = '';
	let password = '';
	let turnstileToken = '';
	let turnstileWidgetId;
	
	const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY;

	const querystringValue = (key) => {
		const querystring = window.location.search;
		const urlParams = new URLSearchParams(querystring);
		return urlParams.get(key);
	};

	function initTurnstile() {
		const containerSelector = '#turnstile-widget';

		if (!import.meta.env.VITE_TURNSTILE_SITE_KEY) {
			console.error('❌ Missing VITE_TURNSTILE_SITE_KEY in .env');
			toast.error('Security check not configured.');
			return;
		}

		const widgetContainer = document.querySelector(containerSelector);
		if (!widgetContainer) {
			console.warn('⚠️ Widget container not found — retrying…');
			setTimeout(initTurnstile, 150);
			return;
		}

		if (!window.turnstile || typeof window.turnstile.render !== 'function') {
			console.warn('⚠️ Turnstile script not ready — retrying…');
			setTimeout(initTurnstile, 150);
			return;
		}

		// ✅ Only clean up if we really have an existing widget
		try {
			if (turnstileWidgetId !== undefined && turnstileWidgetId !== null) {
			// Either reset or remove works; remove guarantees a clean slate
			window.turnstile.remove(turnstileWidgetId);
			console.log('♻️ Removed previous widget');
			turnstileWidgetId = undefined;
			}
		} catch (e) {
			console.warn('Cleanup failed:', e);
		}

		// Clear the container before rendering
		widgetContainer.innerHTML = '';

		try {
			console.log('🎯 Rendering Turnstile widget (manual click mode)…');
			turnstileWidgetId = window.turnstile.render(containerSelector, {
			sitekey: import.meta.env.VITE_TURNSTILE_SITE_KEY,
			theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
			size: 'normal',
			appearance: 'always',     // shows the checkbox/UI
			action: 'login',

			callback: (token) => {
				turnstileToken = token;
				console.log('✅ Turnstile verified manually');
			},
			'expired-callback': () => {
				turnstileToken = '';
				console.log('⏰ Turnstile expired');
			},
			'timeout-callback': () => {
				turnstileToken = '';
				console.log('⏰ Turnstile timeout');
			},
			'error-callback': () => {
				turnstileToken = '';
				console.error('❌ Turnstile error');
				toast.error('Verification failed. Please try again.');
			}
			});
			console.log('✅ Widget rendered with ID:', turnstileWidgetId);
		} catch (e) {
			console.error('❌ Failed to render Turnstile:', e);
			toast.error('Security verification failed to load.');
		}
		}


	const signInHandler = async () => {
		console.log('🔐 Sign in attempt...');
		console.log('📧 Email:', email);
		console.log('🎫 Turnstile token:', turnstileToken ? 'Present' : 'Missing');

		// Check Turnstile
		if (!turnstileToken) {
			toast.error('Please complete the security verification.');
			return;
		}

		try {
			// Call backend signin
			console.log('Calling backend signin...');
			const response = await fetch(`${WEBUI_BASE_URL}/api/v1/auths/signin`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					email: email.toLowerCase(),
					password: password,
					turnstile_token: turnstileToken
				})
			});

			console.log('📬 Response status:', response.status);

			if (!response.ok) {
				const error = await response.json();
				console.error('❌ Backend error:', error);
				throw new Error(error.detail || 'Sign in failed');
			}

			const sessionUser = await response.json();
			
			console.log('✅ Sign in response:', sessionUser);
			console.log('📧 email_verified field:', sessionUser.email_verified);
			console.log('📧 email_verified type:', typeof sessionUser.email_verified);

			// CRITICAL CHECK: Email verification status
			if (sessionUser.email_verified === false) {
				console.log('❌ Email NOT verified - redirecting to pending page');
				
				// Store token
				if (sessionUser.token) {
					localStorage.token = sessionUser.token;
				}
				
				toast.error('Email not verified. Please check your inbox.');
				
				// Redirect to pending page
				console.log('🔀 Redirecting to /auth/verify-pending');
				await goto(`/auth/verify-pending?email=${encodeURIComponent(sessionUser.email)}`);
				return;
			}

			// Email IS verified - proceed with login
			console.log('✅ Email verified - logging in');
			
			toast.success('You\'re now logged in.');
			
			if (sessionUser.token) {
				localStorage.token = sessionUser.token;
			}

			$socket.emit('user-join', { auth: { token: sessionUser.token } });
			await user.set(sessionUser);
			await config.set(await getBackendConfig());

			const redirectPath = querystringValue('redirect') || '/';
			console.log('🏠 Redirecting to:', redirectPath);
			goto(redirectPath);

		} catch (error) {
			console.error('❌ Sign in error:', error);
			toast.error(error.message || 'Sign in failed');
			
			// Reset turnstile
			if (window.turnstile && turnstileWidgetId !== undefined) {
				window.turnstile.reset(turnstileWidgetId);
				turnstileToken = '';
			}
		}
	};

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

	onMount(async () => {
		console.log('🚀 Login page mounted');
		
		// Check for verification success
		const urlParams = new URLSearchParams(window.location.search);
		if (urlParams.get('verified') === 'true') {
			toast.success('Email verified successfully! You can now sign in.');
		}

		if ($user !== undefined) {
			const redirectPath = querystringValue('redirect') || '/';
			goto(redirectPath);
		}

		loaded = true;
		setLogoImage();

		// Load Turnstile script
		console.log('📦 Loading Turnstile script...');
		const existing = document.querySelector('script[data-turnstile]');

		if (!existing) {
			const script = document.createElement('script');
			script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
			script.async = true;
			script.defer = true;
			script.setAttribute('data-turnstile', '1');
			script.onload = () => setTimeout(initTurnstile, 200);
			script.onerror = () => toast.error('Failed to load security verification. Please refresh.');
			document.head.appendChild(script);
		} else {
			if (window.turnstile) setTimeout(initTurnstile, 200);
		}
	});

	onDestroy(() => {
		if (window.turnstile && turnstileWidgetId !== undefined) {
			try {
				window.turnstile.remove(turnstileWidgetId);
				console.log('🧹 Turnstile cleaned up');
			} catch (e) {
				console.log('Cleanup error:', e);
			}
		}
	});
</script>

<svelte:head>
	<title>Sign In - {$WEBUI_NAME}</title>
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
					<h1 class="text-2xl font-bold text-black dark:text-white mb-2">
						{$i18n.t('Sign in to your account')}
					</h1>
				</div>

				<!-- Login Form -->
				<form
				class="space-y-6"
				on:submit={(e) => {
					e.preventDefault();
					signInHandler();
				}}
				>

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
						<div class="flex justify-between items-center mb-2">
								<label for="password" class="block text-sm font-medium text-black dark:text-white">
									{$i18n.t('Password')}
								</label>
							<button
								type="button"
								class="text-sm text-[#A855F7] hover:text-[#9333EA]"
								on:click={() => goto('/auth/forgot-password')}
							>
									{$i18n.t('Forgot?')}
							</button>
						</div>
						<input
							id="password"
							bind:value={password}
							type="password"
							class="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-black dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none"
								placeholder="{$i18n.t('Enter your password')}"
							required
						/>
					</div>

					<!-- Cloudflare Turnstile -->
					<div class="flex justify-center py-2">
						<div id="turnstile-widget" style="min-height: 65px; width: 300px;"></div>
					</div>

					<button
						type="submit"
						class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={!turnstileToken}
					>
						{$i18n.t('Sign in')}
					</button>
				</form>

				<!-- Sign Up Link -->
				<div class="text-center mt-6">
					<span class="text-sm text-gray-600 dark:text-gray-400">
						{$i18n.t('Don\'t have an account?')}
					</span>
					<button
						type="button"
						class="ml-1 text-sm text-[#A855F7] hover:text-[#9333EA] font-medium"
						on:click={() => goto('/auth/signup')}
					>
						{$i18n.t('Sign up')}
					</button>
				</div>

				<!-- Debug Info (Remove in production) -->
				<div class="mt-4 text-xs text-gray-500 text-center">
					Turnstile: {turnstileToken ? '✅ Verified' : '⏳ Pending'}
				</div>
			{/if}
		</div>
	</div>
</div>