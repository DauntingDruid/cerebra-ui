import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { theme } from '../../src/lib/stores/index';

describe('Theme Store', () => {
	beforeEach(() => {
		// Reset theme to default
		theme.set('system');
	});

	it('should have default value of system', () => {
		expect(get(theme)).toBe('system');
	});

	it('should update theme value', () => {
		theme.set('dark');
		expect(get(theme)).toBe('dark');

		theme.set('light');
		expect(get(theme)).toBe('light');

		theme.set('system');
		expect(get(theme)).toBe('system');
	});

	it('should maintain state across updates', () => {
		theme.set('dark');
		expect(get(theme)).toBe('dark');

		// Multiple updates
		theme.set('light');
		theme.set('dark');
		theme.set('system');

		expect(get(theme)).toBe('system');
	});
});