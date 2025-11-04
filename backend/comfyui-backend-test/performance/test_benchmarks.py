"""
Performance benchmarks for CerebraUI backend
Tests latency, throughput, and resource usage

"""
import pytest
import asyncio
import time
from statistics import mean, median
from typing import List


from open_webui.utils.images.prompt_analyzer import PromptAnalyzer


@pytest.mark.performance
@pytest.mark.benchmark
class TestPromptAnalyzerPerformance:
    """Benchmark PromptAnalyzer performance"""
    
    @pytest.mark.asyncio
    async def test_single_analysis_latency(self, performance_metrics):
        """Test single prompt analysis latency"""
        analyzer = PromptAnalyzer()
        latencies = []
        
        for _ in range(100):
            start = time.time()
            await analyzer.analyze("create a sunset", has_parent=False)
            latencies.append((time.time() - start) * 1000)  # Convert to ms
        
        avg_latency = mean(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[94]  # 95th percentile
        
        print(f"\n📊 Prompt Analysis Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max:     {max_latency:.2f}ms")
        print(f"   P95:     {p95_latency:.2f}ms")
        
        # Assertions
        expected = performance_metrics["prompt_analysis"]
        assert avg_latency < expected["max_latency_ms"], \
            f"Average latency {avg_latency:.2f}ms exceeds {expected['max_latency_ms']}ms"
        assert p95_latency < expected["p95_latency_ms"], \
            f"P95 latency {p95_latency:.2f}ms exceeds {expected['p95_latency_ms']}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_analysis_throughput(self):
        """Test throughput with concurrent requests"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a sunset",
            "make it blue",
            "generate a cat",
            "add a tree",
            "生成一个图片"
        ] * 20  # 100 total requests
        
        start = time.time()
        results = await asyncio.gather(*[
            analyzer.analyze(prompt, has_parent=False)
            for prompt in prompts
        ])
        elapsed = time.time() - start
        
        throughput = len(prompts) / elapsed
        
        print(f"\n📊 Concurrent Analysis Throughput:")
        print(f"   Total requests: {len(prompts)}")
        print(f"   Time elapsed:   {elapsed:.2f}s")
        print(f"   Throughput:     {throughput:.2f} req/s")
        
        assert len(results) == len(prompts)
        assert throughput > 10, f"Throughput {throughput:.2f} req/s is too low"
    
    @pytest.mark.asyncio
    async def test_analysis_with_different_prompt_lengths(self):
        """Test performance with varying prompt lengths"""
        analyzer = PromptAnalyzer()
        
        test_cases = [
            ("short", "cat" * 1),
            ("medium", "create a sunset " * 5),
            ("long", "generate a beautiful landscape " * 20),
        ]
        
        results = {}
        
        for label, prompt in test_cases:
            latencies = []
            for _ in range(50):
                start = time.time()
                await analyzer.analyze(prompt, has_parent=False)
                latencies.append((time.time() - start) * 1000)
            
            results[label] = {
                "avg": mean(latencies),
                "max": max(latencies),
                "length": len(prompt)
            }
        
        print(f"\n📊 Performance by Prompt Length:")
        for label, metrics in results.items():
            print(f"   {label:8} (len={metrics['length']:4}): "
                  f"avg={metrics['avg']:.2f}ms, max={metrics['max']:.2f}ms")
        
        # All should complete within reasonable time
        for metrics in results.values():
            assert metrics["max"] < 200, "Latency too high for long prompts"


@pytest.mark.performance
@pytest.mark.benchmark
class TestMemoryUsage:
    """Benchmark memory usage"""
    
    @pytest.mark.asyncio
    async def test_memory_leak(self):
        """Test for memory leaks in repeated analysis"""
        import gc
        import sys
        
        analyzer = PromptAnalyzer()
        
        # Force garbage collection
        gc.collect()
        
        # Measure initial memory
        if hasattr(sys, 'getsizeof'):
            initial_size = sys.getsizeof(analyzer)
            
            # Run many analyses
            for _ in range(1000):
                await analyzer.analyze("test prompt", has_parent=False)
            
            gc.collect()
            final_size = sys.getsizeof(analyzer)
            
            print(f"\n💾 Memory Usage:")
            print(f"   Initial: {initial_size} bytes")
            print(f"   Final:   {final_size} bytes")
            print(f"   Delta:   {final_size - initial_size} bytes")
            
            # Size should not grow significantly
            assert final_size < initial_size * 2, "Possible memory leak detected"


@pytest.mark.performance
class TestScalability:
    """Test system scalability"""
    
    @pytest.mark.asyncio
    async def test_increasing_load(self):
        """Test performance under increasing load"""
        analyzer = PromptAnalyzer()
        
        load_levels = [10, 50, 100, 200]
        results = []
        
        for load in load_levels:
            prompts = ["create a test"] * load
            
            start = time.time()
            await asyncio.gather(*[
                analyzer.analyze(prompt, has_parent=False)
                for prompt in prompts
            ])
            elapsed = time.time() - start
            
            throughput = load / elapsed
            results.append({
                "load": load,
                "time": elapsed,
                "throughput": throughput
            })
        
        print(f"\n📈 Scalability Test:")
        for r in results:
            print(f"   Load {r['load']:3}: "
                  f"{r['time']:.2f}s, "
                  f"{r['throughput']:.2f} req/s")
        
        # Throughput should remain reasonable
        for r in results:
            assert r["throughput"] > 5, \
                f"Throughput degraded at load {r['load']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--durations=0"])