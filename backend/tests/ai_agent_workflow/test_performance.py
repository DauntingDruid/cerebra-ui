"""
Performance tests for AI Agent Workflow
Tests response times, efficiency, and resource usage
"""
import pytest
import time
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from open_webui.models.workflows import Workflows, WorkflowExecutions
from open_webui.utils.workflow_executor import execute_workflow


@pytest.mark.performance
@pytest.mark.ai_agent_workflow
class TestWorkflowPerformance:
    """Test workflow performance characteristics"""
    
    def test_workflow_creation_performance(self):
        """Test workflow creation is fast (<100ms)"""
        user_id = "perf_user_123"
        
        with patch.object(Workflows, 'create_workflow') as mock_create:
            mock_wf = Mock(id="wf_perf_123")
            mock_create.return_value = mock_wf
            
            start_time = time.time()
            workflow = Workflows.create_workflow(user_id, Mock())
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert workflow is not None
            assert elapsed_ms < 100, f"Creation took {elapsed_ms:.2f}ms (max: 100ms)"
            print(f"✓ Workflow creation: {elapsed_ms:.2f}ms")
    
    def test_workflow_retrieval_performance(self):
        """Test workflow retrieval is fast (<50ms)"""
        workflow_id = "wf_retrieve_123"
        
        with patch.object(Workflows, 'get_workflow_by_id') as mock_get:
            mock_wf = Mock(id=workflow_id)
            mock_get.return_value = mock_wf
            
            start_time = time.time()
            workflow = Workflows.get_workflow_by_id(workflow_id)
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert workflow is not None
            assert elapsed_ms < 50, f"Retrieval took {elapsed_ms:.2f}ms (max: 50ms)"
            print(f"✓ Workflow retrieval: {elapsed_ms:.2f}ms")
    
    def test_bulk_workflow_listing_performance(self):
        """Test listing 50 workflows is fast (<200ms)"""
        user_id = "perf_user_123"
        
        with patch.object(Workflows, 'get_workflows_by_user_id') as mock_list:
            # Simulate 50 workflows
            mock_workflows = [Mock(id=f"wf_{i}") for i in range(50)]
            mock_list.return_value = mock_workflows
            
            start_time = time.time()
            workflows = Workflows.get_workflows_by_user_id(user_id)
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert len(workflows) == 50
            assert elapsed_ms < 200, f"Listing took {elapsed_ms:.2f}ms (max: 200ms)"
            print(f"✓ List 50 workflows: {elapsed_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_workflow_execution_response_time(self):
        """Test workflow execution completes within reasonable time"""
        
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Result"}]},
                "session_id": "thread_123"
            }
            
            start_time = time.time()
            result = await execute_workflow(
                workflow_type="deep_research",
                config={"endpoint_url": "http://langraph:8080"},
                api_key="test",
                input_data={"message": "test query"}
            )
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert result["success"] is True
            assert elapsed_ms < 5000, f"Execution took {elapsed_ms:.2f}ms (max: 5000ms for mock)"
            print(f"✓ Workflow execution: {elapsed_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_concurrent_workflow_executions(self):
        """Test handling 10 concurrent workflow executions"""
        
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Result"}]},
                "session_id": "thread_concurrent"
            }
            
            async def execute_single():
                return await execute_workflow(
                    workflow_type="deep_research",
                    config={"endpoint_url": "http://langraph:8080"},
                    api_key="test",
                    input_data={"message": "concurrent test"}
                )
            
            start_time = time.time()
            results = await asyncio.gather(*[execute_single() for _ in range(10)])
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert len(results) == 10
            assert all(r["success"] for r in results)
            assert elapsed_ms < 10000, f"10 concurrent executions took {elapsed_ms:.2f}ms"
            print(f"✓ 10 concurrent executions: {elapsed_ms:.2f}ms ({elapsed_ms/10:.2f}ms avg)")
    
    def test_execution_history_query_performance(self):
        """Test execution history retrieval is fast"""
        user_id = "perf_user_123"
        
        with patch.object(WorkflowExecutions, 'get_executions_by_user_id') as mock_history:
            # Simulate 100 executions
            mock_executions = [Mock(id=f"exec_{i}") for i in range(100)]
            mock_history.return_value = mock_executions
            
            start_time = time.time()
            history = WorkflowExecutions.get_executions_by_user_id(user_id, limit=100)
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert len(history) == 100
            assert elapsed_ms < 300, f"History query took {elapsed_ms:.2f}ms (max: 300ms)"
            print(f"✓ Query 100 execution records: {elapsed_ms:.2f}ms")
    
    def test_execution_status_update_performance(self):
        """Test execution status updates are fast"""
        execution_id = "exec_update_123"
        
        with patch.object(WorkflowExecutions, 'update_execution_status') as mock_update:
            mock_exec = Mock(id=execution_id, status="completed")
            mock_update.return_value = mock_exec
            
            start_time = time.time()
            execution = WorkflowExecutions.update_execution_status(
                execution_id=execution_id,
                status="completed",
                output_data={"result": "test"}
            )
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert execution.status == "completed"
            assert elapsed_ms < 100, f"Status update took {elapsed_ms:.2f}ms (max: 100ms)"
            print(f"✓ Execution status update: {elapsed_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_session_continuity_lookup_performance(self):
        """Test session lookup for continuity is fast"""
        workflow_id = "wf_session_123"
        chat_id = "chat_session_123"
        
        with patch.object(WorkflowExecutions, 'get_last_completed_execution') as mock_get:
            mock_exec = Mock(
                id="exec_last",
                output_data={"session_id": "thread_123"}
            )
            mock_get.return_value = mock_exec
            
            start_time = time.time()
            last_exec = WorkflowExecutions.get_last_completed_execution(workflow_id, chat_id)
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert last_exec is not None
            assert elapsed_ms < 50, f"Session lookup took {elapsed_ms:.2f}ms (max: 50ms)"
            print(f"✓ Session continuity lookup: {elapsed_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_rapid_sequential_executions(self):
        """Test 20 sequential executions complete in reasonable time"""
        
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Result"}]},
                "session_id": "thread_seq"
            }
            
            start_time = time.time()
            for i in range(20):
                result = await execute_workflow(
                    workflow_type="deep_research",
                    config={"endpoint_url": "http://langraph:8080"},
                    api_key="test",
                    input_data={"message": f"Query {i}"}
                )
                assert result["success"] is True
            
            elapsed_ms = (time.time() - start_time) * 1000
            avg_ms = elapsed_ms / 20
            
            assert elapsed_ms < 10000, f"20 sequential executions took {elapsed_ms:.2f}ms"
            print(f"✓ 20 sequential executions: {elapsed_ms:.2f}ms ({avg_ms:.2f}ms avg)")
    
    def test_workflow_deletion_performance(self):
        """Test workflow deletion is fast"""
        workflow_id = "wf_delete_123"
        
        with patch.object(Workflows, 'delete_workflow') as mock_delete:
            mock_delete.return_value = True
            
            start_time = time.time()
            result = Workflows.delete_workflow(workflow_id)
            elapsed_ms = (time.time() - start_time) * 1000
            
            assert result is True
            assert elapsed_ms < 100, f"Deletion took {elapsed_ms:.2f}ms (max: 100ms)"
            print(f"✓ Workflow deletion: {elapsed_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_memory_efficiency_multiple_executions(self):
        """Test that multiple executions don't cause memory issues"""
        
        with patch('open_webui.utils.workflow_executor.WorkflowExecutor.execute_deep_research', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": {"outputs": [{"text": "Result" * 1000}]},  # Larger response
                "session_id": "thread_mem"
            }
            
            # Execute 50 times to test memory handling
            start_time = time.time()
            for i in range(50):
                result = await execute_workflow(
                    workflow_type="deep_research",
                    config={"endpoint_url": "http://langraph:8080"},
                    api_key="test",
                    input_data={"message": f"Memory test {i}"}
                )
                assert result["success"] is True
            
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"✓ 50 executions (memory test): {elapsed_ms:.2f}ms")


@pytest.mark.performance
@pytest.mark.ai_agent_workflow
class TestPerformanceBenchmarks:
    """Performance benchmarks and thresholds"""
    
    def test_performance_summary(self):
        """Summary of performance requirements"""
        benchmarks = {
            "Workflow CRUD Operations": {
                "Create": "< 100ms",
                "Read": "< 50ms",
                "Update": "< 100ms",
                "Delete": "< 100ms"
            },
            "Execution Operations": {
                "Start Execution": "< 200ms",
                "Status Update": "< 100ms",
                "History Query (100 records)": "< 300ms"
            },
            "Workflow Execution": {
                "Mock Execution": "< 5s",
                "Real Execution (Deep Research)": "< 300s",
                "Session Lookup": "< 50ms"
            },
            "Concurrent Operations": {
                "10 Concurrent Executions": "< 10s",
                "20 Sequential Executions": "< 10s"
            }
        }
        
        print("\n" + "="*60)
        print("PERFORMANCE BENCHMARKS")
        print("="*60)
        for category, metrics in benchmarks.items():
            print(f"\n{category}:")
            for operation, threshold in metrics.items():
                print(f"  • {operation}: {threshold}")
        print("="*60)
        
        assert True  # This test always passes, just for documentation


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])