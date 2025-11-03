import { describe, it, expect } from 'vitest';
import { isValidHttpUrl } from '../../src/lib/utils/index';

describe('isValidHttpUrl', () => {
	it('should return true for valid HTTP URLs', () => {
		expect(isValidHttpUrl('http://example.com')).toBe(true);
		expect(isValidHttpUrl('https://example.com')).toBe(true);
		expect(isValidHttpUrl('https://subdomain.example.com/path?query=value')).toBe(true);
	});

	it('should return false for invalid URLs', () => {
		expect(isValidHttpUrl('not-a-url')).toBe(false);
		expect(isValidHttpUrl('ftp://example.com')).toBe(false);
		expect(isValidHttpUrl('mailto:test@example.com')).toBe(false);
		expect(isValidHttpUrl('')).toBe(false);
	});

	it('should return false for URLs without protocol', () => {
		expect(isValidHttpUrl('example.com')).toBe(false);
		expect(isValidHttpUrl('//example.com')).toBe(false);
	});

	it('should return false for malformed URLs', () => {
		expect(isValidHttpUrl('http://')).toBe(false);
		expect(isValidHttpUrl('http://:8080')).toBe(false);
	});
});