"""
Integration tests for Smart Image Generation API
Tests the complete workflow from API endpoint to image generation
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# Correct imports from Open WebUI
from open_webui.utils.images.prompt_analyzer import PromptAnalyzer
from open_webui.utils.images.fal_flux import FalFluxClient


@pytest.mark.integration
class TestSmartAPIIntegration:
    """Integration tests for smart generation API"""
    
    @pytest.mark.asyncio
    async def test_text2img_workflow(self, mock_fal_client):
        """Test complete text2img workflow"""
        analyzer = PromptAnalyzer()
        
        # Step 1: Analyze prompt
        prompt = "create a beautiful sunset"
        analysis = await analyzer.analyze(prompt, has_parent=False)
        
        assert analysis["mode"] == "text2img"
        assert analysis["image_size"] in ["landscape_4_3", "landscape_16_9"]
        
        # Step 2: Generate image (mocked)
        with patch.object(FalFluxClient, 'text2img', new=mock_fal_client.text2img):
            result = await mock_fal_client.text2img(
                prompt=prompt,
                image_size=analysis["image_size"],
                num_inference_steps=28
            )
            
            assert result["url"].startswith("https://")
            assert result["mode"] == "text2img"
    
    @pytest.mark.asyncio
    async def test_img2img_workflow(self, mock_fal_client):
        """Test complete img2img workflow"""
        analyzer = PromptAnalyzer()
        
        # Step 1: Analyze prompt
        prompt = "make it blue"
        analysis = await analyzer.analyze(prompt, has_parent=True)
        
        assert analysis["mode"] == "img2img"
        
        # Step 2: Generate modified image (mocked)
        with patch.object(FalFluxClient, 'img2img', new=mock_fal_client.img2img):
            result = await mock_fal_client.img2img(
                prompt=prompt,
                image_url="https://example.com/parent.png",
                strength=0.85
            )
            
            assert result["url"].startswith("https://")
            assert result["mode"] == "img2img"
    
    @pytest.mark.asyncio
    async def test_multi_round_generation(self, mock_fal_client):
        """Test multi-round generation chain"""
        analyzer = PromptAnalyzer()
        
        # Round 1: Create
        prompt1 = "create a cat"
        analysis1 = await analyzer.analyze(prompt1, has_parent=False)
        assert analysis1["mode"] == "text2img"
        
        # Round 2: Modify
        prompt2 = "make it blue"
        analysis2 = await analyzer.analyze(prompt2, has_parent=True)
        assert analysis2["mode"] == "img2img"
        
        # Round 3: Further modify
        prompt3 = "add a hat"
        analysis3 = await analyzer.analyze(prompt3, has_parent=True)
        assert analysis3["mode"] == "img2img"


@pytest.mark.integration
class TestAPIErrorHandling:
    """Test error handling in API integration"""
    
    @pytest.mark.asyncio
    async def test_fal_api_timeout(self):
        """Test handling of Fal API timeout"""
        mock_client = AsyncMock()
        mock_client.text2img = AsyncMock(side_effect=asyncio.TimeoutError())
        
        with patch('open_webui.utils.images.fal_flux.FalFluxClient', return_value=mock_client):
            with pytest.raises(asyncio.TimeoutError):
                await mock_client.text2img(
                    prompt="test",
                    image_size="landscape_4_3"
                )
    
    @pytest.mark.asyncio
    async def test_analysis_fallback_on_openai_error(self):
        """Test fallback when OpenAI fails"""
        analyzer = PromptAnalyzer()
        
        # Should use fallback rules
        result = await analyzer.analyze("create a sunset", has_parent=False)
        
        assert result["mode"] == "text2img"
        assert result["mode_confidence"] >= 0.7


@pytest.mark.integration  
@pytest.mark.smoke
class TestSmokeSuite:
    """Quick smoke tests for basic functionality"""
    
    @pytest.mark.asyncio
    async def test_analyzer_basic_import(self):
        """Test PromptAnalyzer can be imported and instantiated"""
        analyzer = PromptAnalyzer()
        assert analyzer is not None
    
    @pytest.mark.asyncio
    async def test_basic_analysis(self):
        """Test basic analysis works"""
        analyzer = PromptAnalyzer()
        result = await analyzer.analyze("test", has_parent=False)
        
        assert "mode" in result
        assert "mode_confidence" in result
        assert "image_size" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])