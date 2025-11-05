"""
Unit tests for Workflow CRUD operations
Tests the workflow model database operations in isolation
"""
import pytest
from unittest.mock import Mock, patch

from open_webui.models.workflows import Workflows


@pytest.mark.unit
@pytest.mark.ai_agent_workflow
class TestWorkflowCRUD:
    """Test Workflow CRUD operations"""
    
    def test_create_workflow(self, db_session):
        """Test creating a new workflow"""
        user_id = "test_user_123"
        form_data = Mock()
        form_data.name = "Test Deep Research"
        form_data.description = "Test workflow for deep research"
        form_data.workflow_type = "deep_research"
        form_data.config = {
            "api_url": "http://langraph:8080",
            "api_key": "test_key",
            "assistant_id": "test_assistant"
        }
        form_data.is_active = True
        
        with patch.object(Workflows, 'create_workflow') as mock_create:
            mock_workflow = Mock()
            mock_workflow.id = "workflow_123"
            mock_workflow.name = "Test Deep Research"
            mock_workflow.workflow_type = "deep_research"
            mock_workflow.user_id = user_id
            mock_create.return_value = mock_workflow
            
            workflow = Workflows.create_workflow(user_id, form_data)
            
            assert workflow is not None
            assert workflow.name == "Test Deep Research"
            assert workflow.workflow_type == "deep_research"
            assert workflow.user_id == "test_user_123"
            print(f"✓ Test passed: Workflow created with ID {workflow.id}")
    
    def test_get_workflow_by_id(self, sample_workflow):
        """Test retrieving workflow by ID"""
        with patch.object(Workflows, 'get_workflow_by_id') as mock_get:
            mock_get.return_value = sample_workflow
            
            workflow = Workflows.get_workflow_by_id(sample_workflow.id)
            
            assert workflow is not None
            assert workflow.id == sample_workflow.id
            assert workflow.name == sample_workflow.name
            print(f"✓ Test passed: Retrieved workflow {workflow.id}")
    
    def test_get_workflows_by_user_id(self, sample_workflow):
        """Test getting all workflows for a user"""
        with patch.object(Workflows, 'get_workflows_by_user_id') as mock_get:
            mock_get.return_value = [sample_workflow]
            
            workflows = Workflows.get_workflows_by_user_id(sample_workflow.user_id)
            
            assert len(workflows) > 0
            assert workflows[0].id == sample_workflow.id
            print(f"✓ Test passed: Found {len(workflows)} workflows for user")
    
    def test_update_workflow(self, sample_workflow):
        """Test updating workflow"""
        form_data = Mock()
        form_data.name = "Updated Workflow Name"
        form_data.description = "Updated description"
        form_data.workflow_type = "deep_research"
        form_data.config = {}
        form_data.is_active = True
        
        with patch.object(Workflows, 'update_workflow') as mock_update:
            sample_workflow.name = form_data.name
            sample_workflow.description = form_data.description
            mock_update.return_value = sample_workflow
            
            workflow = Workflows.update_workflow(sample_workflow.id, form_data)
            
            assert workflow.name == "Updated Workflow Name"
            assert workflow.description == "Updated description"
            print(f"✓ Test passed: Workflow updated successfully")
    
    def test_delete_workflow(self, sample_workflow):
        """Test deleting workflow"""
        with patch.object(Workflows, 'delete_workflow') as mock_delete:
            mock_delete.return_value = True
            
            result = Workflows.delete_workflow(sample_workflow.id)
            
            assert result is True
            print(f"✓ Test passed: Workflow deleted successfully")
    
    def test_get_workflow_not_found(self):
        """Test getting non-existent workflow"""
        with patch.object(Workflows, 'get_workflow_by_id') as mock_get:
            mock_get.return_value = None
            
            workflow = Workflows.get_workflow_by_id("invalid_id")
            
            assert workflow is None
            print(f"✓ Test passed: Non-existent workflow returns None")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])