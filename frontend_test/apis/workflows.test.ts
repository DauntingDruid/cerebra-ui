import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createNewWorkflow, getWorkflows, getWorkflowById, updateWorkflowById } from '../../src/lib/apis/workflows';
import type { Workflow } from '../../src/lib/apis/workflows';

// Mock the fetch function
global.fetch = vi.fn();

describe('Workflows API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	describe('createNewWorkflow', () => {
		it('should create a new workflow successfully', async () => {
			const mockWorkflow: Workflow = {
				id: 'wf-123',
				user_id: 'user-1',
				name: 'Summary Generator',
				description: 'Generates research summaries',
				workflow_type: 'langflow',
				config: {},
				is_active: true,
				created_at: '2024-01-01T00:00:00Z',
				updated_at: '2024-01-01T00:00:00Z'
			};

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => mockWorkflow
			});

			const workflowData = {
				name: 'Summary Generator',
				description: 'Generates research summaries',
				workflow_type: 'langflow' as const,
				config: {}
			};

			const result = await createNewWorkflow('token', workflowData);

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/workflows/'),
				expect.objectContaining({
					method: 'POST',
					headers: expect.objectContaining({
						'Content-Type': 'application/json'
					}),
					body: JSON.stringify(workflowData),
					credentials: 'include'
				})
			);

			expect(result).toEqual(mockWorkflow);
			expect(result.name).toBe('Summary Generator');
		});

		it('should handle API errors', async () => {
			(global.fetch as any).mockResolvedValueOnce({
				ok: false,
				json: async () => ({ detail: 'Workflow name already exists' })
			});

			await expect(
				createNewWorkflow('token', { name: 'Duplicate', workflow_type: 'langflow' })
			).rejects.toThrow('Workflow name already exists');
		});
	});

	describe('getWorkflows', () => {
		it('should fetch all workflows', async () => {
			const mockWorkflows: Workflow[] = [
				{
					id: 'wf-1',
					user_id: 'user-1',
					name: 'Workflow 1',
					workflow_type: 'langflow',
					config: {},
					is_active: true,
					created_at: '2024-01-01T00:00:00Z',
					updated_at: '2024-01-01T00:00:00Z'
				},
				{
					id: 'wf-2',
					user_id: 'user-1',
					name: 'Deep Research',
					workflow_type: 'deep_research',
					config: {},
					is_active: true,
					created_at: '2024-01-01T00:00:00Z',
					updated_at: '2024-01-01T00:00:00Z'
				}
			];

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => mockWorkflows
			});

			const result = await getWorkflows('token');

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/workflows/'),
				expect.objectContaining({
					method: 'GET',
					credentials: 'include'
				})
			);

			expect(result).toHaveLength(2);
			expect(result[0].name).toBe('Workflow 1');
			expect(result[1].workflow_type).toBe('deep_research');
		});
	});

	describe('getWorkflowById', () => {
		it('should fetch a workflow by ID', async () => {
			const mockWorkflow: Workflow = {
				id: 'wf-123',
				user_id: 'user-1',
				name: 'Data Cleaner',
				workflow_type: 'custom',
				config: { steps: ['clean', 'validate'] },
				is_active: true,
				created_at: '2024-01-01T00:00:00Z',
				updated_at: '2024-01-01T00:00:00Z'
			};

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => mockWorkflow
			});

			const result = await getWorkflowById('token', 'wf-123');

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/workflows/wf-123'),
				expect.objectContaining({
					method: 'GET',
					credentials: 'include'
				})
			);

			expect(result).toEqual(mockWorkflow);
			expect(result.name).toBe('Data Cleaner');
		});
	});

	describe('updateWorkflowById', () => {
		it('should update an existing workflow', async () => {
			const updatedWorkflow: Workflow = {
				id: 'wf-123',
				user_id: 'user-1',
				name: 'Data Cleaner Updated',
				workflow_type: 'custom',
				config: { steps: ['clean', 'validate', 'format'] },
				is_active: true,
				created_at: '2024-01-01T00:00:00Z',
				updated_at: '2024-01-02T00:00:00Z'
			};

			(global.fetch as any).mockResolvedValueOnce({
				ok: true,
				json: async () => updatedWorkflow
			});

			const updateData = {
				name: 'Data Cleaner Updated',
				config: { steps: ['clean', 'validate', 'format'] }
			};

			const result = await updateWorkflowById('token', 'wf-123', updateData);

			expect(global.fetch).toHaveBeenCalledWith(
				expect.stringContaining('/api/v1/workflows/wf-123'),
				expect.objectContaining({
					method: 'PUT',
					body: JSON.stringify(updateData),
					credentials: 'include'
				})
			);

			expect(result.name).toBe('Data Cleaner Updated');
		});
	});
});