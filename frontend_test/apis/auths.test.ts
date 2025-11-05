import { describe, it, expect, beforeEach, vi } from 'vitest';
import { userSignIn, userSignUp } from '../../src/lib/apis/auths';

// Mock the fetch function
global.fetch = vi.fn();

describe('Authentication API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.spyOn(console, 'log').mockImplementation(() => {});
	});

	describe('userSignIn', () => {
		it('should sign in user with valid credentials', async () => {
			const mockUser = {
				token: 'auth-token-123',
				user: {
					id: 'user-1',
					email: 'test@example.com',
					name: 'Test User'
				}
			};

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => mockUser
			});

			const result = await userSignIn('test@example.com', 'password123');

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/auths/signin'),
				expect.objectContaining({
					method: 'POST',
					headers: expect.objectContaining({
						'Content-Type': 'application/json'
					}),
					body: JSON.stringify({
						email: 'test@example.com',
						password: 'password123'
					}),
					credentials: 'include'
				})
			);

			expect(result).toEqual(mockUser);
			expect(result.token).toBe('auth-token-123');
		});

		it('should throw error with invalid credentials', async () => {
			(global.fetch as any).mockResolvedValueOnce({
				ok: false,
				json: async () => ({ detail: 'Invalid email or password' })
			});

			await expect(userSignIn('wrong@example.com', 'wrongpassword')).rejects.toBe(
				'Invalid email or password'
			);
		});

		it('should handle network errors', async () => {
			(global.fetch as any).mockRejectedValueOnce({
				detail: 'Network error'
			});

			await expect(userSignIn('test@example.com', 'password')).rejects.toBe('Network error');
		});
	});

	describe('userSignUp', () => {
		it('should register a new user successfully', async () => {
			const mockUser = {
				token: 'auth-token-456',
				user: {
					id: 'user-2',
					email: 'newuser@example.com',
					name: 'New User',
					profile_image_url: 'https://example.com/avatar.png'
				}
			};

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => mockUser
			});

			const result = await userSignUp('New User', 'newuser@example.com', 'password123', 'avatar.png');

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/auths/signup'),
				expect.objectContaining({
					method: 'POST',
					headers: expect.objectContaining({
						'Content-Type': 'application/json'
					}),
					body: JSON.stringify({
						name: 'New User',
						email: 'newuser@example.com',
						password: 'password123',
						profile_image_url: 'avatar.png'
					}),
					credentials: 'include'
				})
			);

			expect(result).toEqual(mockUser);
			expect(result.user.email).toBe('newuser@example.com');
		});

		it('should throw error when email already exists', async () => {
			(global.fetch as any).mockResolvedValueOnce({
				ok: false,
				json: async () => ({ detail: 'Email already registered' })
			});

			await expect(
				userSignUp('Existing User', 'existing@example.com', 'password', 'avatar.png')
			).rejects.toBe('Email already registered');
		});

		it('should throw error for invalid email format', async () => {
			(global.fetch as any).mockResolvedValueOnce({
				ok: false,
				json: async () => ({ detail: 'Invalid email format' })
			});

			await expect(
				userSignUp('User', 'invalid-email', 'password', 'avatar.png')
			).rejects.toBe('Invalid email format');
		});
	});
});