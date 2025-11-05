import { afterEach, vi } from 'vitest';

// Mock console methods to avoid noise in test output
global.console = {
	...console,
	log: vi.fn(),
	warn: vi.fn(),
	error: vi.fn()
};

// Setup for DOM environment (jsdom)
if (typeof window !== 'undefined') {
	// Add any global DOM setup here if needed
}