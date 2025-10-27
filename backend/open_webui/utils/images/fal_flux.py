"""
Fal Flux API client with async support
"""
import os
import logging
import asyncio
from typing import Optional

log = logging.getLogger(__name__)

class FalFluxClient:
    """Wrapper for Fal Flux API"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = str(api_key) if api_key is not None else os.getenv("FAL_KEY")
        # 🆕 NEW: Read model from env or parameter, with fallback
        self.model = str(model) if model is not None else os.getenv("FAL_MODEL", "fal-ai/flux-pro/v1.1")
        
        if not self.api_key:
            raise ValueError("FAL_KEY not set")
        
        os.environ["FAL_KEY"] = self.api_key
        log.info(f"[FalFlux] Initialized: model={self.model}")
    
    async def text2img(
        self,
        prompt: str,
        image_size: str = "square_hd",
        num_inference_steps: int = 28,
        guidance_scale: float = 3.5,
        seed: Optional[int] = None
    ) -> dict:
        """Generate image from text"""
        def _sync_call():
            import fal_client
            
            arguments = {
                "prompt": prompt,
                "image_size": image_size,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "num_images": 1,
                "enable_safety_checker": False
            }
            
            if seed:
                arguments["seed"] = seed
            
            return fal_client.subscribe(self.model, arguments=arguments, with_logs=True)
        
        try:
            result = await asyncio.to_thread(_sync_call)
            
            if not result or "images" not in result:
                raise ValueError("Fal API returned no images")
            
            image = result["images"][0]
            
            return {
                "image_url": image["url"],
                "seed": result.get("seed"),
                "width": image.get("width", 1024),
                "height": image.get("height", 1024)
            }
        except Exception as e:
            log.error(f"[FalFlux] text2img error: {e}", exc_info=True)
            raise
    
    async def img2img(
        self,
        prompt: str,
        image_bytes: bytes,
        strength: float = 0.35,
        image_size: str = "square_hd",
        num_inference_steps: int = 28,
        guidance_scale: float = 3.5,
        seed: Optional[int] = None
    ) -> dict:
        """
        Modify existing image
        Note: Fal requires image_url, so we upload bytes to Fal's storage first
        """
        def _sync_call():
            import fal_client
            
            # Upload image bytes to Fal's temporary storage
            image_url = fal_client.upload(image_bytes, "image/png")
            
            arguments = {
                "prompt": prompt,
                "image_url": image_url,
                "strength": strength,
                "image_size": image_size,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "enable_safety_checker": False
            }
            
            if seed:
                arguments["seed"] = seed
            
            return fal_client.subscribe(self.model, arguments=arguments, with_logs=True)
        
        try:
            result = await asyncio.to_thread(_sync_call)
            
            if not result or "images" not in result:
                raise ValueError("Fal API returned no images")
            
            image = result["images"][0]
            
            return {
                "image_url": image["url"],
                "seed": result.get("seed"),
                "width": image.get("width", 1024),
                "height": image.get("height", 1024)
            }
        except Exception as e:
            log.error(f"[FalFlux] img2img error: {e}", exc_info=True)
            raise
