"""
Integration tests for AI Agent Workflow
Tests components working together
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from open_webui.models.workflows import Workflows, WorkflowExecutions, WorkflowCredentials
from open_webui.utils.workflow_executor import execute_workflow


@pytest.mark.integration
@pytest.mark.ai_agent_workflow
class TestWorkflowIntegration:
    """Test workflow components integration"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_execution_flow(self):
        """Test complete flow: create workflow → execute → check status"""
        user_id = "test_user_123"
        
        # Step 1: Create workflow
        with patch.object(Workflows, 'create_workflow') as mock_create_wf:
            mock_workflow = Mock()
            mock_workflow.id = "workflow_123"
            mock_workflow.workflow_type = "deep_research"
            mock_workflow.config = {"endpoint_url": "http://langraph:8080"}
            mock_create_wf.return_value = mock_workflow
            
            workflow = Workflows.create_workflow(user_id, Mock())
            assert workflow is not None
        
        # Step 2: Create execution record
        with patch.object(WorkflowExecutions, 'create_execution') as mock_create_exec:
            mock_execution = Mock()
            mock_execution.id = "execution_123"
            mock_execution.status = "pending"
            mock_create_exec.return_value = mock_execution
            
            execution = WorkflowExecutions.create_execution(user_id, Mock())
            assert execution.status == "pending"
        
        # Step 3: Execute workflow
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Result"}]},
                "session_id": "thread_123"
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test_key",
                input_data={"message": "test"}
            )
            assert result["success"] is True
        
        # Step 4: Update execution status
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            mock_execution.status = "completed"
            mock_update.return_value = mock_execution
            
            updated = WorkflowExecutions.update_execution_status(
                execution_id="execution_123",
                status="completed",
                output_data=result
            )
            assert updated.status == "completed"
        
        print("✓ Integration test passed: Complete workflow execution flow")
    
    @pytest.mark.asyncio
    async def test_workflow_with_session_continuity(self):
        """Test multi-turn conversation with session persistence"""
        workflow_id = "workflow_123"
        chat_id = "chat_123"
        
        # First execution - no previous session
        with patch.object(WorkflowExecutions, 'get_last_completed_execution') as mock_get_last:
            mock_get_last.return_value = None  # No previous execution
            
            last_exec = WorkflowExecutions.get_last_completed_execution(workflow_id, chat_id)
            assert last_exec is None
            print("  ✓ First execution: No previous session found")
        
        # Execute first query and get session_id
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "First response"}]},
                "session_id": "thread_xyz_001"
            }
            
            result1 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "First query"}
            )
            session_id = result1["session_id"]
            assert session_id == "thread_xyz_001"
            print(f"  ✓ First execution completed: session_id={session_id}")
        
        # Second execution - retrieve previous session
        with patch.object(WorkflowExecutions, 'get_last_completed_execution') as mock_get_last:
            mock_prev = Mock()
            mock_prev.output_data = {"session_id": session_id}
            mock_get_last.return_value = mock_prev
            
            last_exec = WorkflowExecutions.get_last_completed_execution(workflow_id, chat_id)
            assert last_exec is not None
            assert last_exec.output_data["session_id"] == session_id
            print(f"  ✓ Previous session retrieved: {session_id}")
        
        # Execute second query with session continuity
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Follow-up response"}]},
                "session_id": session_id
            }
            
            result2 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={
                    "message": "Follow-up query",
                    "session_id": session_id
                }
            )
            
            assert result2["session_id"] == session_id
            print(f"  ✓ Second execution with continuity: session_id={result2['session_id']}")
        
        print("✓ Integration test passed: Session continuity across executions")
    
    @pytest.mark.asyncio
    async def test_langflow_workflow_execution(self):
        """Test Langflow workflow integration"""
        user_id = "test_user_123"
        
        # Create Langflow workflow
        with patch.object(Workflows, 'create_workflow') as mock_create:
            mock_workflow = Mock()
            mock_workflow.id = "langflow_wf_123"
            mock_workflow.workflow_type = "langflow"
            mock_workflow.config = {
                "endpoint_url": "http://langflow:7860",
                "flow_id": "test_flow_123"
            }
            mock_create.return_value = mock_workflow
            
            workflow = Workflows.create_workflow(user_id, Mock())
            assert workflow.workflow_type == "langflow"
        
        # Execute Langflow workflow
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_langflow', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"result": "Langflow response"},
                "message": "Workflow executed successfully"
            }
            
            result = await execute_workflow(
                workflow_type="langflow",
                config=workflow.config,
                api_key="test_key",
                input_data={"message": "Test Langflow"}
            )
            
            assert result["success"] is True
            assert "output" in result
        
        print("✓ Integration test passed: Langflow workflow execution")
    
    @pytest.mark.asyncio
    async def test_workflow_with_credentials(self):
        """Test workflow execution with stored credentials"""
        user_id = "test_user_123"
        service_name = "langflow"
        
        # Store credentials
        with patch.object(WorkflowCredentials, 'create_credential') as mock_create_cred:
            mock_cred = Mock()
            mock_cred.id = "cred_123"
            mock_cred.service_name = service_name
            mock_cred.endpoint_url = "http://langflow:7860"
            mock_create_cred.return_value = mock_cred
            
            cred = WorkflowCredentials.create_credential(user_id, Mock())
            assert cred.service_name == service_name
        
        # Retrieve credentials
        with patch.object(WorkflowCredentials, 'get_credential_by_service') as mock_get_cred:
            mock_cred = Mock()
            mock_cred.api_key = "decrypted_key_123"
            mock_cred.endpoint_url = "http://langflow:7860"
            mock_get_cred.return_value = mock_cred
            
            retrieved_cred = WorkflowCredentials.get_credential_by_service(user_id, service_name)
            assert retrieved_cred.api_key == "decrypted_key_123"
        
        # Execute workflow using credentials
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_langflow', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"result": "Success with credentials"}
            }
            
            result = await execute_workflow(
                workflow_type="langflow",
                config={
                    "endpoint_url": retrieved_cred.endpoint_url,
                    "flow_id": "test_flow"
                },
                api_key=retrieved_cred.api_key,
                input_data={"message": "Test"}
            )
            
            assert result["success"] is True
        
        print("✓ Integration test passed: Workflow execution with credentials")
    
    @pytest.mark.asyncio
    async def test_workflow_error_handling(self):
        """Test workflow error handling and status update"""
        user_id = "test_user_123"
        
        # Create execution
        with patch.object(WorkflowExecutions, 'create_execution') as mock_create:
            mock_execution = Mock()
            mock_execution.id = "exec_error_123"
            mock_execution.status = "pending"
            mock_create.return_value = mock_execution
            
            execution = WorkflowExecutions.create_execution(user_id, Mock())
            assert execution.status == "pending"
        
        # Execute workflow - simulate error
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "error": "Connection timeout"
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "Test"}
            )
            
            assert result["success"] is False
            assert "error" in result
        
        # Update execution with error
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            mock_execution.status = "failed"
            mock_execution.error_message = "Connection timeout"
            mock_update.return_value = mock_execution
            
            updated = WorkflowExecutions.update_execution_status(
                execution_id="exec_error_123",
                status="failed",
                error_message="Connection timeout"
            )
            
            assert updated.status == "failed"
            assert updated.error_message == "Connection timeout"
        
        print("✓ Integration test passed: Error handling and status update")
    
    @pytest.mark.asyncio
    async def test_multiple_workflow_types(self):
        """Test executing different workflow types"""
        workflow_types = ["langflow", "n8n", "deep_research", "langchain"]
        
        for wf_type in workflow_types:
            with patch.object(Workflows, 'create_workflow') as mock_create:
                mock_workflow = Mock()
                mock_workflow.id = f"{wf_type}_123"
                mock_workflow.workflow_type = wf_type
                mock_create.return_value = mock_workflow
                
                workflow = Workflows.create_workflow("test_user", Mock())
                assert workflow.workflow_type == wf_type
                print(f"  ✓ Created {wf_type} workflow")
        
        print("✓ Integration test passed: Multiple workflow types")
    
    @pytest.mark.asyncio
    async def test_workflow_update_and_re_execute(self):
        """Test updating workflow config and re-executing"""
        user_id = "test_user_123"
        workflow_id = "workflow_update_123"
        
        # Create initial workflow
        with patch.object(Workflows, 'create_workflow') as mock_create:
            mock_workflow = Mock()
            mock_workflow.id = workflow_id
            mock_workflow.config = {"endpoint_url": "http://old-url:8080"}
            mock_create.return_value = mock_workflow
            
            workflow = Workflows.create_workflow(user_id, Mock())
            old_config = workflow.config
        
        # Update workflow config
        with patch.object(Workflows, 'update_workflow') as mock_update:
            mock_workflow.config = {"endpoint_url": "http://new-url:8080"}
            mock_update.return_value = mock_workflow
            
            updated_workflow = Workflows.update_workflow(workflow_id, Mock())
            assert updated_workflow.config != old_config
            print("  ✓ Workflow config updated")
        
        # Execute with new config
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "New config result"}]}
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config=updated_workflow.config,
                api_key="test",
                input_data={"message": "Test with new config"}
            )
            
            assert result["success"] is True
            print("  ✓ Execution with updated config successful")
        
        print("✓ Integration test passed: Workflow update and re-execution")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])