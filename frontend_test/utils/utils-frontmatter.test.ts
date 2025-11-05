import { describe, it, expect } from 'vitest';
import { extractFrontmatter } from '../../src/lib/utils/index';

describe('extractFrontmatter', () => {
	it('should extract frontmatter from valid format', () => {
		const content = `"""
title: Test Document
author: John Doe
date: 2024-01-01
"""
Content here`;

		const result = extractFrontmatter(content);

		expect(result).toEqual({
			title: 'Test Document',
			author: 'John Doe',
			date: '2024-01-01'
		});
	});

	it('should return empty object when content does not start with triple quotes', () => {
		const content = `title: Test
Content here`;

		const result = extractFrontmatter(content);

		expect(result).toEqual({});
	});

	it('should extract frontmatter with empty values', () => {
		const content = `"""
title: Test
description: 
"""
Content`;

		const result = extractFrontmatter(content);

		expect(result).toEqual({
			title: 'Test',
			description: ''
		});
	});

	it('should handle frontmatter with special characters', () => {
		const content = `"""
title: Test Document v2.0
url: https://example.com/path?query=value
"""
Content`;

		const result = extractFrontmatter(content);

		expect(result).toEqual({
			title: 'Test Document v2.0',
			url: 'https://example.com/path?query=value'
		});
	});

	it('should return empty object when frontmatter is not properly closed', () => {
		const content = `"""
title: Test
Content here`;

		const result = extractFrontmatter(content);

		// Should still extract what it can find
		expect(result).toEqual({
			title: 'Test'
		});
	});

	it('should handle empty frontmatter block', () => {
		const content = `"""
"""
Content here`;

		const result = extractFrontmatter(content);

		expect(result).toEqual({});
	});
});