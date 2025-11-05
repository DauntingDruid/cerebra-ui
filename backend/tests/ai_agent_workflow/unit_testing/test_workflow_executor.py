"""
Unit tests for Workflow Executor
Tests the workflow execution engine in isolation
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from open_webui.utils.workflow_executor import execute_workflow, WorkflowExecutor


@pytest.mark.unit
@pytest.mark.ai_agent_workflow
class TestWorkflowExecutor:
    """Test Workflow Executor"""
    
    @pytest.mark.asyncio
    async def test_execute_deep_research_new_execution(self, deep_research_workflow):
        """Test executing Deep Research workflow"""
        workflow_type = "deep_research"
        config = {
            "endpoint_url": "http://langraph:8080",
            "timeout": 300
        }
        api_key = "test_key"
        input_data = {"message": "What is machine learning?"}
        
        with patch.object(WorkflowExecutor, 'execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Machine learning is..."}]},
                "session_id": "thread_xyz_001",
                "message": "Deep Research completed"
            }
            
            result = await execute_workflow(
                workflow_type=workflow_type,
                config=config,
                api_key=api_key,
                input_data=input_data
            )
            
            assert result is not None
            assert result["success"] is True
            assert "output" in result
            assert "session_id" in result
            print(f"✓ Test passed: Deep Research executed, session_id: {result['session_id']}")
    
    @pytest.mark.asyncio
    async def test_execute_langflow_workflow(self):
        """Test executing Langflow workflow"""
        workflow_type = "langflow"
        config = {
            "endpoint_url": "http://langflow:7860",
            "flow_id": "test_flow_123",
            "timeout": 300
        }
        api_key = "test_key"
        input_data = {"message": "Test query", "session_id": "session_123"}
        
        with patch.object(WorkflowExecutor, 'execute_langflow', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"result": "Test result"},
                "message": "Workflow executed successfully"
            }
            
            result = await execute_workflow(
                workflow_type=workflow_type,
                config=config,
                api_key=api_key,
                input_data=input_data
            )
            
            assert result["success"] is True
            print(f"✓ Test passed: Langflow workflow executed")
    
    @pytest.mark.asyncio
    async def test_execute_with_session_continuity(self):
        """Test workflow execution with session_id for continuity"""
        workflow_type = "deep_research"
        config = {"endpoint_url": "http://langraph:8080"}
        input_data = {
            "message": "Follow-up question",
            "session_id": "thread_existing_123"  # Reusing existing session
        }
        
        with patch.object(WorkflowExecutor, 'execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Follow-up answer"}]},
                "session_id": "thread_existing_123",  # Same session returned
                "message": "Deep Research completed"
            }
            
            result = await execute_workflow(
                workflow_type=workflow_type,
                config=config,
                api_key="test_key",
                input_data=input_data
            )
            
            assert result["session_id"] == "thread_existing_123"
            print(f"✓ Test passed: Session continuity maintained")
    
    @pytest.mark.asyncio
    async def test_invalid_workflow_type(self):
        """Test execution with invalid workflow type"""
        workflow_type = "invalid_type"
        config = {}
        input_data = {"message": "test"}
        
        result = await execute_workflow(
            workflow_type=workflow_type,
            config=config,
            api_key="test_key",
            input_data=input_data
        )
        
        assert result["success"] is False
        assert "Unknown workflow type" in result["error"]
        print(f"✓ Test passed: Invalid workflow type returns error")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])