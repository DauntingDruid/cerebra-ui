<script>
	import { toast } from 'svelte-sonner';
	import { onMount, getContext, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	// import { getBackendConfig } from '$lib/apis';
	// import { getSessionUser, userSignUp } from '$lib/apis/auths';

	// import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
	// import { WEBUI_NAME, config, user, socket } from '$lib/stores';

	import { WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME } from '$lib/stores';

	import { generateInitialsImage, canvasPixelTest } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let name = '';
	let email = '';
	let password = '';

	let sending = false;
	let sent = false;
	let errorMsg = '';

	const AUTH = import.meta.env.VITE_BETTERAUTH_PUBLIC ?? 'http://localhost:4000';

	const querystringValue = (key) => {
		const querystring = window.location.search;
		const urlParams = new URLSearchParams(querystring);
		return urlParams.get(key);
	};

	// const setSessionUser = async (sessionUser) => {
	// 	if (sessionUser) {
	// 		console.log(sessionUser);
	// 		toast.success($i18n.t(`You're now logged in.`));
	// 		if (sessionUser.token) {
	// 			localStorage.token = sessionUser.token;
	// 		}

	// 		$socket.emit('user-join', { auth: { token: sessionUser.token } });
	// 		await user.set(sessionUser);
	// 		await config.set(await getBackendConfig());

	// 		const redirectPath = querystringValue('redirect') || '/';
	// 		goto(redirectPath);
	// 	}
	// };

	// No auto-login here; user must verify first.

	// const signUpHandler = async () => {
	// 	const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
	// 		(error) => {
	// 			toast.error(`${error}`);
	// 			return null;
	// 		}
	// 	);
	// 	await setSessionUser(sessionUser);
		
	// 	// 注释掉邮箱验证跳转，直接进入主页
	// 	// goto('/auth/verify-email?type=signup');
	// };


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
			sent = true; // swap UI to the “check your email” message
		} catch (e) {
			errorMsg = e?.message ?? 'Something went wrong';
			toast.error(errorMsg);
		} finally {
			sending = false;
		}
	};



	const checkOauthCallback = async () => {
		if (!$page.url.hash) {
			return;
		}
		const hash = $page.url.hash.substring(1);
		if (!hash) {
			return;
		}
		const params = new URLSearchParams(hash);
		const token = params.get('token');
		if (!token) {
			return;
		}
		const sessionUser = await getSessionUser(token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		if (!sessionUser) {
			return;
		}
		localStorage.token = token;
		await setSessionUser(sessionUser);
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

	// onMount(async () => {
	// 	if ($user !== undefined) {
	// 		const redirectPath = querystringValue('redirect') || '/';
	// 		goto(redirectPath);
	// 	}
	// 	await checkOauthCallback();

	// 	loaded = true;
	// 	setLogoImage();
	// });

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

				<!-- Title -->
				<!-- <div class="text-center mb-8">
					<h1 class="text-2xl font-bold text-black dark:text-white">
						Create your free account
					</h1>
				</div> -->

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
						class="w-full bg-gray-800 dark:bg-gray-700 text-white py-3 px-4 rounded-lg font-medium hover:bg-gray-900 dark:hover:bg-gray-600 transition-colors"
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
					<!-- Success message -->
					<div class="text-center space-y-4">
						<h1 class="text-2xl font-bold text-black dark:text-white">Check your email</h1>
						<p class="text-sm text-gray-400">
							We sent a verification link to
							<span class="font-medium text-gray-200">{email}</span>.<br />
							Please check your inbox (and spam). The link expires in 24 hours.
						</p>
						<div class="pt-2">
							<button class="underline text-sm" on:click={() => goto('/auth/login')}>
								Back to Sign In
							</button>
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</div>
