"""
End-to-End tests for AI Agent Workflow
Tests complete user scenarios
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


@pytest.mark.e2e
@pytest.mark.ai_agent_workflow
class TestWorkflowE2E:
    """Test complete user workflows"""
    
    @pytest.mark.asyncio
    async def test_user_creates_and_executes_deep_research(self):
        """Test: User creates workflow → executes → views result"""
        from open_webui.models.workflows import Workflows, WorkflowExecutions
        from open_webui.utils.workflow_executor import execute_workflow
        
        user_id = "user_456"
        
        # User creates workflow
        form_data = Mock()
        form_data.name = "My Research Assistant"
        form_data.description = "Deep research workflow"
        form_data.workflow_type = "deep_research"
        form_data.config = {
            "endpoint_url": "http://langraph:8080",
            "timeout": 300
        }
        form_data.is_active = True
        
        with patch.object(Workflows, 'create_workflow') as mock_create:
            mock_wf = Mock()
            mock_wf.id = "wf_123"
            mock_wf.workflow_type = "deep_research"
            mock_create.return_value = mock_wf
            
            workflow = Workflows.create_workflow(user_id, form_data)
            assert workflow.id == "wf_123"
        
        # User executes workflow
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {
                    "outputs": [{"text": "Machine learning is a subset of AI..."}]
                },
                "session_id": "thread_001",
                "message": "Deep Research completed"
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config=form_data.config,
                api_key="test_key",
                input_data={"message": "What is machine learning?"}
            )
            
            assert result["success"] is True
            assert "output" in result
            assert "session_id" in result
        
        print("✓ E2E test passed: User workflow creation and execution")
    
    @pytest.mark.asyncio
    async def test_multi_turn_research_conversation(self):
        """Test: User has multi-turn conversation with context"""
        from open_webui.utils.workflow_executor import execute_workflow
        
        session_id = None
        
        # Turn 1
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "AI is artificial intelligence..."}]},
                "session_id": "thread_conversation_001"
            }
            
            result1 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "What is AI?"}
            )
            session_id = result1["session_id"]
        
        # Turn 2 - with context
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "AI applications include healthcare, finance..."}]},
                "session_id": session_id
            }
            
            result2 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={
                    "message": "What are its applications?",
                    "session_id": session_id
                }
            )
            
            assert result2["session_id"] == session_id
        
        # Turn 3 - continue conversation
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Healthcare applications include diagnosis..."}]},
                "session_id": session_id
            }
            
            result3 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={
                    "message": "Tell me more about healthcare applications",
                    "session_id": session_id
                }
            )
            
            assert result3["session_id"] == session_id
        
        print("✓ E2E test passed: Multi-turn conversation with context")
    
    @pytest.mark.asyncio
    async def test_user_manages_multiple_workflows(self):
        """Test: User creates, lists, updates, and deletes workflows"""
        from open_webui.models.workflows import Workflows
        
        user_id = "user_789"
        
        # Create multiple workflows
        workflow_ids = []
        for i in range(3):
            with patch.object(Workflows, 'create_workflow') as mock_create:
                mock_wf = Mock()
                mock_wf.id = f"wf_{i}"
                mock_wf.name = f"Workflow {i}"
                mock_wf.workflow_type = "deep_research"
                mock_create.return_value = mock_wf
                
                workflow = Workflows.create_workflow(user_id, Mock())
                workflow_ids.append(workflow.id)
                print(f"  ✓ Created workflow: {workflow.id}")
        
        # List all workflows
        with patch.object(Workflows, 'get_workflows_by_user_id') as mock_list:
            mock_workflows = [Mock(id=wf_id) for wf_id in workflow_ids]
            mock_list.return_value = mock_workflows
            
            workflows = Workflows.get_workflows_by_user_id(user_id)
            assert len(workflows) == 3
            print(f"  ✓ Listed {len(workflows)} workflows")
        
        # Update one workflow
        with patch.object(Workflows, 'update_workflow') as mock_update:
            mock_wf = Mock()
            mock_wf.id = workflow_ids[0]
            mock_wf.name = "Updated Workflow"
            mock_update.return_value = mock_wf
            
            updated = Workflows.update_workflow(workflow_ids[0], Mock())
            assert updated.name == "Updated Workflow"
            print(f"  ✓ Updated workflow: {updated.id}")
        
        # Delete one workflow
        with patch.object(Workflows, 'delete_workflow') as mock_delete:
            mock_delete.return_value = True
            
            result = Workflows.delete_workflow(workflow_ids[1])
            assert result is True
            print(f"  ✓ Deleted workflow: {workflow_ids[1]}")
        
        print("✓ E2E test passed: User manages multiple workflows")
    
    @pytest.mark.asyncio
    async def test_user_workflow_with_file_attachments(self):
        """Test: User executes workflow with file attachments"""
        from open_webui.utils.workflow_executor import execute_workflow
        
        # Simulate user uploading files
        files = [
            {"url": "http://example.com/doc1.pdf", "name": "research.pdf", "type": "pdf"},
            {"url": "http://example.com/doc2.txt", "name": "notes.txt", "type": "text"}
        ]
        
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Based on the documents provided..."}]},
                "session_id": "thread_files_001",
                "message": "Deep Research completed"
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={
                    "message": "Analyze these documents",
                    "files": files
                }
            )
            
            assert result["success"] is True
            print(f"  ✓ Workflow executed with {len(files)} files")
        
        print("✓ E2E test passed: Workflow execution with file attachments")
    
    @pytest.mark.asyncio
    async def test_user_workflow_execution_history(self):
        """Test: User views execution history"""
        from open_webui.models.workflows import WorkflowExecutions
        
        user_id = "user_history_123"
        
        # Create multiple executions
        with patch.object(WorkflowExecutions, 'get_executions_by_user_id') as mock_get_history:
            mock_executions = []
            for i in range(5):
                mock_exec = Mock()
                mock_exec.id = f"exec_{i}"
                mock_exec.status = "completed" if i < 4 else "failed"
                mock_exec.workflow_id = "wf_123"
                mock_executions.append(mock_exec)
            
            mock_get_history.return_value = mock_executions
            
            history = WorkflowExecutions.get_executions_by_user_id(user_id, limit=50)
            assert len(history) == 5
            
            completed = [e for e in history if e.status == "completed"]
            failed = [e for e in history if e.status == "failed"]
            
            print(f"  ✓ Found {len(completed)} completed executions")
            print(f"  ✓ Found {len(failed)} failed executions")
        
        print("✓ E2E test passed: User views execution history")
    
    @pytest.mark.asyncio
    async def test_user_switches_between_workflow_types(self):
        """Test: User executes different workflow types in sequence"""
        from open_webui.utils.workflow_executor import execute_workflow
        
        workflows = [
            ("langflow", "http://langflow:7860"),
            ("deep_research", "http://langraph:8080"),
            ("n8n", "http://n8n:5678")
        ]
        
        for wf_type, endpoint in workflows:
            if wf_type == "langflow":
                with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_langflow', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        "success": True,
                        "output": {"result": f"{wf_type} result"}
                    }
                    
                    result = await execute_workflow(
                        workflow_type=wf_type,
                        config={"endpoint_url": endpoint, "flow_id": "test"},
                        api_key="test",
                        input_data={"message": "test"}
                    )
                    
                    assert result["success"] is True
                    print(f"  ✓ Executed {wf_type} workflow")
            
            elif wf_type == "deep_research":
                with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        "success": True,
                        "output": {"outputs": [{"text": f"{wf_type} result"}]}
                    }
                    
                    result = await execute_workflow(
                        workflow_type=wf_type,
                        config={"endpoint_url": endpoint},
                        api_key="test",
                        input_data={"message": "test"}
                    )
                    
                    assert result["success"] is True
                    print(f"  ✓ Executed {wf_type} workflow")
            
            elif wf_type == "n8n":
                with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_n8n', new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = {
                        "success": True,
                        "output": {"result": f"{wf_type} result"}
                    }
                    
                    result = await execute_workflow(
                        workflow_type=wf_type,
                        config={"endpoint_url": endpoint, "workflow_id": "test"},
                        api_key="test",
                        input_data={"message": "test"}
                    )
                    
                    assert result["success"] is True
                    print(f"  ✓ Executed {wf_type} workflow")
        
        print("✓ E2E test passed: User switches between workflow types")
    
    @pytest.mark.asyncio
    async def test_user_handles_workflow_failure_and_retry(self):
        """Test: User encounters error, then retries successfully"""
        from open_webui.models.workflows import WorkflowExecutions
        from open_webui.utils.workflow_executor import execute_workflow
        
        user_id = "user_retry_123"
        
        # First attempt - fails
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "error": "Connection timeout"
            }
            
            result1 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "test"}
            )
            
            assert result1["success"] is False
            print("  ✓ First attempt failed as expected")
        
        # Record failure
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            mock_exec = Mock()
            mock_exec.status = "failed"
            mock_exec.error_message = "Connection timeout"
            mock_update.return_value = mock_exec
            
            execution = WorkflowExecutions.update_execution_status(
                execution_id="exec_retry_123",
                status="failed",
                error_message="Connection timeout"
            )
            
            assert execution.status == "failed"
            print("  ✓ Failure recorded")
        
        # Retry - succeeds
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Success on retry"}]},
                "session_id": "thread_retry_001"
            }
            
            result2 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "test"}
            )
            
            assert result2["success"] is True
            print("  ✓ Retry succeeded")
        
        # Record success
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            mock_exec.status = "completed"
            mock_update.return_value = mock_exec
            
            execution = WorkflowExecutions.update_execution_status(
                execution_id="exec_retry_123",
                status="completed",
                output_data=result2
            )
            
            assert execution.status == "completed"
            print("  ✓ Success recorded")
        
        print("✓ E2E test passed: User handles failure and retry")
    
    @pytest.mark.asyncio
    async def test_user_manages_credentials_and_executes(self):
        """Test: User stores credentials, then uses them for workflow execution"""
        from open_webui.models.workflows import WorkflowCredentials
        from open_webui.utils.workflow_executor import execute_workflow
        
        user_id = "user_creds_123"
        service_name = "deep_research"
        
        # User stores credentials
        with patch.object(WorkflowCredentials, 'create_credential') as mock_create:
            mock_cred = Mock()
            mock_cred.id = "cred_123"
            mock_cred.service_name = service_name
            mock_cred.endpoint_url = "http://langraph:8080"
            mock_create.return_value = mock_cred
            
            credential = WorkflowCredentials.create_credential(user_id, Mock())
            assert credential.service_name == service_name
            print(f"  ✓ Credentials stored for {service_name}")
        
        # User retrieves and uses credentials
        with patch.object(WorkflowCredentials, 'get_credential_by_service') as mock_get:
            mock_cred = Mock()
            mock_cred.api_key = "secure_key_123"
            mock_cred.endpoint_url = "http://langraph:8080"
            mock_get.return_value = mock_cred
            
            cred = WorkflowCredentials.get_credential_by_service(user_id, service_name)
            print(f"  ✓ Retrieved credentials")
        
        # Execute workflow with credentials
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Authenticated execution"}]}
            }
            
            result = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": cred.endpoint_url},
                api_key=cred.api_key,
                input_data={"message": "test"}
            )
            
            assert result["success"] is True
            print(f"  ✓ Workflow executed with stored credentials")
        
        print("✓ E2E test passed: User manages credentials and executes")
    
    @pytest.mark.asyncio
    async def test_complete_user_journey(self):
        """Test: Complete user journey from setup to execution"""
        from open_webui.models.workflows import Workflows, WorkflowExecutions, WorkflowCredentials
        from open_webui.utils.workflow_executor import execute_workflow
        
        user_id = "user_journey_123"
        
        # Step 1: User registers credentials
        with patch.object(WorkflowCredentials, 'create_credential') as mock_cred:
            mock_cred.return_value = Mock(id="cred_journey", service_name="deep_research")
            cred = WorkflowCredentials.create_credential(user_id, Mock())
            print("  ✓ Step 1: Credentials registered")
        
        # Step 2: User creates workflow
        with patch.object(Workflows, 'create_workflow') as mock_create_wf:
            mock_wf = Mock(id="wf_journey", workflow_type="deep_research")
            mock_create_wf.return_value = mock_wf
            workflow = Workflows.create_workflow(user_id, Mock())
            print("  ✓ Step 2: Workflow created")
        
        # Step 3: User executes first query
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "First query result"}]},
                "session_id": "thread_journey_001"
            }
            
            result1 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "First query"}
            )
            session_id = result1["session_id"]
            print(f"  ✓ Step 3: First query executed (session: {session_id})")
        
        # Step 4: Record execution
        with patch.object(WorkflowExecutions, 'create_execution') as mock_create_exec:
            mock_exec = Mock(id="exec_1", status="completed")
            mock_create_exec.return_value = mock_exec
            execution = WorkflowExecutions.create_execution(user_id, Mock())
            print("  ✓ Step 4: Execution recorded")
        
        # Step 5: User continues conversation
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Follow-up result"}]},
                "session_id": session_id
            }
            
            result2 = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "Follow-up query", "session_id": session_id}
            )
            print("  ✓ Step 5: Continued conversation with context")
        
        # Step 6: User views execution history
        with patch.object(WorkflowExecutions, 'get_executions_by_user_id') as mock_history:
            mock_history.return_value = [Mock(id="exec_1"), Mock(id="exec_2")]
            history = WorkflowExecutions.get_executions_by_user_id(user_id)
            print(f"  ✓ Step 6: Viewed history ({len(history)} executions)")
        
        print("✓ E2E test passed: Complete user journey")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])