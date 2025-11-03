import { describe, it, expect } from 'vitest';
import { removeEmojis, removeFormattings, cleanText } from '../../src/lib/utils/index';

describe('removeEmojis', () => {
	it('should remove emojis from strings', () => {
		expect(removeEmojis('Hello 😀 World')).toBe('Hello  World');
		expect(removeEmojis('Test 🎉 with 🚀 emojis')).toBe('Test  with  emojis');
	});

	it('should return the same string if no emojis are present', () => {
		expect(removeEmojis('Hello World')).toBe('Hello World');
		expect(removeEmojis('123')).toBe('123');
	});

	it('should handle empty strings', () => {
		expect(removeEmojis('')).toBe('');
	});
});

describe('removeFormattings', () => {
	it('should remove markdown bold formatting', () => {
		expect(removeFormattings('**bold** text')).toBe('bold text');
		expect(removeFormattings('__bold__ text')).toBe('bold text');
	});

	it('should remove markdown italic formatting', () => {
		expect(removeFormattings('*italic* text')).toBe('italic text');
		expect(removeFormattings('_italic_ text')).toBe('italic text');
	});

	it('should remove markdown code blocks', () => {
		expect(removeFormattings('Code ```block``` here')).toBe('Code  here');
		expect(removeFormattings('```\ncode\n```')).toBe('');
	});

	it('should remove inline code', () => {
		expect(removeFormattings('Use `code` here')).toBe('Use code here');
	});

	it('should remove markdown links', () => {
		expect(removeFormattings('Visit [link](https://example.com)')).toBe('Visit link');
		expect(removeFormattings('![image](url)')).toBe('image');
	});

	it('should remove headers', () => {
		expect(removeFormattings('# Header 1')).toBe('Header 1');
		expect(removeFormattings('## Header 2')).toBe('Header 2');
		expect(removeFormattings('### Header 3')).toBe('Header 3');
	});

	it('should remove lists', () => {
		expect(removeFormattings('- Item 1\n- Item 2')).toBe('Item 1\nItem 2');
		expect(removeFormattings('1. First\n2. Second')).toBe('First\nSecond');
	});

	it('should preserve plain text', () => {
		expect(removeFormattings('Plain text with no formatting')).toBe('Plain text with no formatting');
	});
});

describe('cleanText', () => {
	it('should remove both emojis and formatting', () => {
		// Note: cleanText may leave spaces where emojis were removed
		expect(cleanText('**Bold** text 😀').trim()).toBe('Bold text');
		expect(cleanText('  *Italic* 🎉  ').trim()).toBe('Italic');
		expect(cleanText('**Bold** text 😀 ').trim()).toBe('Bold text'); // Handle trailing space after emoji
	});

	it('should trim whitespace', () => {
		expect(cleanText('  text  ')).toBe('text');
		expect(cleanText('\n\ntext\n\n')).toBe('text');
	});

	it('should handle empty strings', () => {
		expect(cleanText('')).toBe('');
		expect(cleanText('   ')).toBe('');
	});
});