"""
Unit tests for PromptAnalyzer
Tests the intelligent prompt analysis system in isolation
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch

from open_webui.utils.images.prompt_analyzer import PromptAnalyzer, get_prompt_analyzer


@pytest.mark.unit
@pytest.mark.prompt_analyzer
class TestPromptAnalyzerInitialization:
    """Test PromptAnalyzer initialization"""
    
    def test_init_without_openai_key(self):
        """Test initialization without OpenAI API key"""
        with patch.dict('os.environ', {}, clear=True):
            analyzer = PromptAnalyzer()
            assert analyzer.client is None
            assert analyzer.api_key is None
    
    def test_init_with_openai_key(self):
        """Test initialization with OpenAI API key"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            # Mock at the openai module level, not prompt_analyzer level
            with patch('openai.AsyncOpenAI') as mock_openai:
                analyzer = PromptAnalyzer()
                assert analyzer.api_key == 'test-key'
                mock_openai.assert_called_once()
    
    def test_singleton_pattern(self):
        """Test that get_prompt_analyzer returns the same instance"""
        analyzer1 = get_prompt_analyzer()
        analyzer2 = get_prompt_analyzer()
        assert analyzer1 is analyzer2


@pytest.mark.unit
@pytest.mark.prompt_analyzer
class TestPromptAnalyzerOpenAI:
    """Test PromptAnalyzer with OpenAI"""
    
    @pytest.mark.asyncio
    async def test_analyze_with_openai_success(self, mock_openai_client):
        """Test successful OpenAI analysis"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            # Mock at the openai module level
            with patch('openai.AsyncOpenAI', return_value=mock_openai_client):
                analyzer = PromptAnalyzer()
                
                result = await analyzer.analyze(
                    "create a beautiful sunset",
                    has_parent=False
                )
                
                assert result["mode"] == "text2img"
                assert result["mode_confidence"] >= 0.9
                assert result["image_size"] == "landscape_4_3"
                assert "reasoning" in result
    
    @pytest.mark.asyncio
    async def test_analyze_with_openai_fallback_on_error(self):
        """Test fallback when OpenAI fails"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            # Mock at the openai module level
            with patch('openai.AsyncOpenAI', return_value=mock_client):
                analyzer = PromptAnalyzer()
                
                result = await analyzer.analyze(
                    "create a sunset",
                    has_parent=False
                )
                
                # Should fallback to rule-based
                assert result["mode"] == "text2img"
                assert result["mode_confidence"] > 0


@pytest.mark.unit
@pytest.mark.prompt_analyzer
class TestPromptAnalyzerFallback:
    """Test PromptAnalyzer fallback (rule-based) analysis"""
    
    @pytest.mark.asyncio
    async def test_fallback_text2img_create_keywords(self):
        """Test text2img detection with creation keywords"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a sunset",
            "generate a cat",
            "draw a house",
            "make a new logo",
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=False)
            assert result["mode"] == "text2img", f"Failed for: {prompt}"
            assert result["mode_confidence"] >= 0.7
    
    @pytest.mark.asyncio
    async def test_fallback_img2img_modify_keywords(self):
        """Test img2img detection with modification keywords"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "make it blue",
            "add a tree",
            "change the color",
            "remove the background",
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=True)
            assert result["mode"] == "img2img", f"Failed for: {prompt}"
            assert result["mode_confidence"] >= 0.65
    
    @pytest.mark.asyncio
    async def test_fallback_context_awareness(self):
        """Test context-aware mode detection"""
        analyzer = PromptAnalyzer()
        
        prompt = "blue"
        
        # Without parent - text2img
        result1 = await analyzer.analyze(prompt, has_parent=False, has_uploaded=False)
        assert result1["mode"] == "text2img"
        
        # With parent - could be either
        result2 = await analyzer.analyze(prompt, has_parent=True, has_uploaded=False)
        assert result2["mode"] in ["text2img", "img2img"]
    
    @pytest.mark.asyncio
    async def test_fallback_size_detection_square(self):
        """Test square size detection"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a square logo",
            "make a profile avatar",
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=False)
            assert result["image_size"] == "square_hd", f"Failed for: {prompt}"
            assert result["size_confidence"] >= 0.8
    
    @pytest.mark.asyncio
    async def test_fallback_size_detection_portrait(self):
        """Test portrait size detection"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a portrait photo",
            "make a vertical poster"
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=False)
            assert "portrait" in result["image_size"], f"Failed for: {prompt}"
            assert result["size_confidence"] >= 0.8
    
    @pytest.mark.asyncio
    async def test_fallback_size_detection_landscape(self):
        """Test landscape size detection"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a landscape photo",
            "make a widescreen wallpaper"
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=False)
            assert "landscape" in result["image_size"], f"Failed for: {prompt}"
            assert result["size_confidence"] >= 0.7


@pytest.mark.unit
@pytest.mark.prompt_analyzer
class TestPromptAnalyzerEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_empty_prompt(self):
        """Test handling of empty prompt"""
        analyzer = PromptAnalyzer()
        result = await analyzer.analyze("", has_parent=False)
        
        assert result["mode"] in ["text2img", "img2img"]
        assert "image_size" in result
        assert 0 <= result["mode_confidence"] <= 1
    
    @pytest.mark.asyncio
    async def test_very_long_prompt(self):
        """Test handling of very long prompt"""
        analyzer = PromptAnalyzer()
        
        long_prompt = "create a beautiful sunset " * 100
        result = await analyzer.analyze(long_prompt, has_parent=False)
        
        assert result["mode"] == "text2img"
        assert result["mode_confidence"] >= 0.7
    
    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test handling of special characters"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create sunset",
            "make it 100% blue",
        ]
        
        for prompt in prompts:
            result = await analyzer.analyze(prompt, has_parent=False)
            assert result["mode"] in ["text2img", "img2img"]
            assert "image_size" in result


@pytest.mark.unit
@pytest.mark.prompt_analyzer
class TestPromptAnalyzerPerformance:
    """Test performance characteristics"""
    
    @pytest.mark.asyncio
    async def test_fallback_response_time(self):
        """Test fallback analysis is fast"""
        import time
        analyzer = PromptAnalyzer()
        
        start = time.time()
        for _ in range(10):
            await analyzer.analyze("create a cat", has_parent=False)
        elapsed = time.time() - start
        
        avg_time_ms = (elapsed / 10) * 1000
        assert avg_time_ms < 100, f"Average time {avg_time_ms:.2f}ms exceeds 100ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_analysis(self):
        """Test concurrent analysis"""
        analyzer = PromptAnalyzer()
        
        prompts = [
            "create a sunset",
            "make it blue",
            "generate a cat",
            "add a tree",
        ]
        
        results = await asyncio.gather(*[
            analyzer.analyze(prompt, has_parent=False)
            for prompt in prompts
        ])
        
        assert len(results) == len(prompts)
        for result in results:
            assert result["mode"] in ["text2img", "img2img"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])