import { defineConfig } from 'cypress';

export default defineConfig({
	e2e: {
		// Default to Docker port (3000), can be overridden with CYPRESS_BASE_URL env var
		baseUrl: process.env.CYPRESS_BASE_URL || 'http://localhost:3000',
		// Ignore uncaught exceptions from the application (common in SPA frameworks)
		setupNodeEvents(on, config) {
			// Handle uncaught exceptions from the application
			on('task', {
				log(message) {
					console.log(message);
					return null;
				}
			});
			return config;
		}
	},
	video: true
});
