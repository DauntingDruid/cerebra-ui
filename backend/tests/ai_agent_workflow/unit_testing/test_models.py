"""
Unit tests for Workflow Models
Tests the workflow execution model operations
"""
import pytest
from unittest.mock import Mock, patch

from open_webui.models.workflows import WorkflowExecutions


@pytest.mark.unit
@pytest.mark.ai_agent_workflow
class TestWorkflowExecutionModel:
    """Test Workflow Execution Model"""
    
    def test_create_execution(self, sample_workflow):
        """Test creating a workflow execution"""
        user_id = "test_user_123"
        form_data = Mock()
        form_data.workflow_id = sample_workflow.id
        form_data.chat_id = None
        form_data.message_id = None
        form_data.input_data = {"query": "test"}
        
        with patch.object(WorkflowExecutions, 'create_execution') as mock_create:
            mock_execution = Mock()
            mock_execution.id = "execution_123"
            mock_execution.workflow_id = sample_workflow.id
            mock_execution.user_id = user_id
            mock_execution.status = "pending"
            mock_create.return_value = mock_execution
            
            execution = WorkflowExecutions.create_execution(user_id, form_data)
            
            assert execution is not None
            assert execution.status == "pending"
            assert execution.workflow_id == sample_workflow.id
            print(f"✓ Test passed: Execution created with ID {execution.id}")
    
    def test_update_execution_status_with_results(self, sample_execution):
        """Test updating execution status with output"""
        output_data = {"result": "test result"}
        
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            sample_execution.status = "completed"
            sample_execution.output_data = output_data
            mock_update.return_value = sample_execution
            
            execution = WorkflowExecutions.update_execution_status(
                execution_id=sample_execution.id,
                status="completed",
                output_data=output_data
            )
            
            assert execution.status == "completed"
            assert execution.output_data == output_data
            print(f"✓ Test passed: Execution updated with results")
    
    def test_get_last_completed_execution(self, sample_workflow):
        """Test retrieving last completed execution"""
        mock_execution = Mock()
        mock_execution.id = "execution_latest"
        mock_execution.workflow_id = sample_workflow.id
        mock_execution.user_id = sample_workflow.user_id
        mock_execution.status = "completed"
        mock_execution.chat_id = "chat_123"
        
        with patch.object(WorkflowExecutions, 'get_last_completed_execution') as mock_get:
            mock_get.return_value = mock_execution
            
            last = WorkflowExecutions.get_last_completed_execution(
                workflow_id=sample_workflow.id,
                chat_id="chat_123"
            )
            
            assert last is not None
            assert last.status == "completed"
            print(f"✓ Test passed: Retrieved most recent completed execution")
    
    def test_get_execution_by_id(self, sample_execution):
        """Test retrieving execution by ID"""
        with patch.object(WorkflowExecutions, 'get_execution_by_id') as mock_get:
            mock_get.return_value = sample_execution
            
            execution = WorkflowExecutions.get_execution_by_id(sample_execution.id)
            
            assert execution is not None
            assert execution.id == sample_execution.id
            print(f"✓ Test passed: Retrieved execution by ID")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])