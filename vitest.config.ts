import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';

const packageJson = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));

export default defineConfig({
	plugins: [sveltekit()],
	define: {
		APP_VERSION: JSON.stringify(packageJson.version || '0.1.0'),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'test-build')
	},
	test: {
		include: ['frontend_test/**/*.{test,spec}.{js,ts}'],
		globals: true,
		environment: 'node',
		setupFiles: ['./frontend_test/setup/setup.ts']
	}
});
