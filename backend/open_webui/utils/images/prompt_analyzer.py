"""
Intelligent prompt analysis using OpenAI
Determines generation mode and optimal image size
"""
import os
import logging
import json
from typing import Optional

log = logging.getLogger(__name__)


class PromptAnalyzer:
    """
    Analyze user prompts to determine:
    1. Generation mode (text2img vs img2img)
    2. Optimal image size
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        
        if not self.api_key:
            log.warning("[PromptAnalyzer] OPENAI_API_KEY not set, using fallback rules")
        else:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    timeout=30.0
                )
                log.info("[PromptAnalyzer] Initialized with OpenAI")
            except ImportError:
                log.error("[PromptAnalyzer] OpenAI package not installed")
                self.client = None
    
    async def analyze(
        self, 
        prompt: str, 
        has_parent: bool = False,
        has_uploaded: bool = False
    ) -> dict:
        """
        Analyze user prompt to determine mode and size
        
        Returns:
            {
                "mode": "text2img" | "img2img",
                "mode_confidence": 0.0-1.0,
                "image_size": "landscape_4_3",
                "size_confidence": 0.0-1.0,
                "reasoning": "Brief explanation"
            }
        """
        if not self.client:
            return self._fallback_analysis(prompt, has_parent, has_uploaded)
        
        try:
            system_prompt = """You are an AI assistant analyzing image generation requests.

**Task 1: Determine Generation Mode**
- text2img: Create new image
- img2img: Modify existing image

Classification keywords:
- MODIFY (img2img): add, change, replace, remove, make it, modify, turn, convert
- MODIFY (Chinese): 加, 改, 换, 删, 把, 让, 变, 调整
- CREATE (text2img): generate, create, draw, make a new, design
- CREATE (Chinese): 生成, 创建, 画一个新, 设计

**Task 2: Determine Image Size**
Recommend optimal size based on user description.

Available sizes:
- square_hd: Square (avatars, logos, icons)
- square: Small square
- portrait_4_3: Vertical 4:3 (portraits, posters)
- portrait_16_9: Vertical 16:9 (phone wallpapers, vertical screens)
- landscape_4_3: Horizontal 4:3 (photos, general use)
- landscape_16_9: Horizontal 16:9 (desktop wallpapers, widescreen)

**Size Detection Keywords:**
Chinese: 竖屏, 横屏, 方形, 长方形, 人像, 风景, 壁纸, 头像, 宽屏
English: portrait, landscape, square, vertical, horizontal, wallpaper, avatar, widescreen

**Default Rules:**
- No size mentioned → landscape_4_3 (most common)
- Portrait/poster → portrait_4_3
- Wallpaper/scenery → landscape_16_9
- Avatar/logo → square_hd

**Context Consideration:**
- has_parent=true: There is a previously generated image in the conversation history
- has_uploaded=true: User uploaded a new image in this message
- If (has_parent OR has_uploaded) AND modify keywords → img2img
- If (has_parent OR has_uploaded) BUT completely different subject → text2img
- If neither parent nor upload → text2img

Return ONLY valid JSON (no markdown):
{
    "mode": "text2img" or "img2img",
    "mode_confidence": 0.0-1.0,
    "image_size": "landscape_4_3",
    "size_confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}

Examples:

Prompt: "make it blue"
Context: has_parent=true
→ {"mode": "img2img", "mode_confidence": 0.95, "image_size": "landscape_4_3", "size_confidence": 0.7, "reasoning": "Modification keyword, no size specified"}

Prompt: "生成一个竖屏的猫咪照片"
Context: has_parent=false
→ {"mode": "text2img", "mode_confidence": 1.0, "image_size": "portrait_4_3", "size_confidence": 0.9, "reasoning": "New creation, explicit portrait orientation"}

Prompt: "create a square logo with cat"
Context: has_parent=true
→ {"mode": "text2img", "mode_confidence": 0.95, "image_size": "square_hd", "size_confidence": 0.95, "reasoning": "Requests new creation despite history, explicit square"}"""

            user_message = f"""Analyze this request:

Prompt: "{prompt}"
Has previous image: {has_parent}
User uploaded image: {has_uploaded}

Return JSON analysis."""

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=250
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Extract JSON from markdown if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(result_text)
            
            # Validate mode
            if "mode" not in result or result["mode"] not in ["text2img", "img2img"]:
                log.warning(f"[PromptAnalyzer] Invalid mode: {result.get('mode')}")
                return self._fallback_analysis(prompt, has_parent, has_uploaded)
            
            # Validate size
            valid_sizes = [
                "square_hd", "square", 
                "portrait_4_3", "portrait_16_9", 
                "landscape_4_3", "landscape_16_9"
            ]
            
            if "image_size" not in result or result["image_size"] not in valid_sizes:
                log.warning(f"[PromptAnalyzer] Invalid size: {result.get('image_size')}")
                result["image_size"] = "landscape_4_3"
                result["size_confidence"] = 0.5
            
            # Fill in defaults
            if "mode_confidence" not in result:
                result["mode_confidence"] = 0.8
            if "size_confidence" not in result:
                result["size_confidence"] = 0.7
            if "reasoning" not in result:
                result["reasoning"] = "OpenAI analysis"
            
            log.info(
                f"[PromptAnalyzer] OpenAI: mode={result['mode']} "
                f"mode_conf={result['mode_confidence']:.2f} "
                f"size={result['image_size']} "
                f"size_conf={result['size_confidence']:.2f}"
            )
            
            return result
            
        except json.JSONDecodeError as e:
            log.error(f"[PromptAnalyzer] JSON parse error: {e}")
            return self._fallback_analysis(prompt, has_parent, has_uploaded)
        except Exception as e:
            log.error(f"[PromptAnalyzer] OpenAI error: {e}")
            return self._fallback_analysis(prompt, has_parent, has_uploaded)
    
    def _fallback_analysis(
        self, 
        prompt: str, 
        has_parent: bool, 
        has_uploaded: bool
    ) -> dict:
        """
        Rule-based fallback when OpenAI unavailable
        Uses keyword matching for both mode and size detection
        """
        prompt_lower = prompt.lower()
        
        # ===== Mode Detection =====
        modification_keywords = [
            # English
            "add", "change", "replace", "remove", "make it", "turn", "convert",
            "modify", "update", "alter", "adjust",
            # Chinese
            "加", "改", "换", "删", "把", "让", "变", "调整"
        ]
        
        creation_keywords = [
            "generate", "create", "draw", "make a new", "design", "illustrate",
            "生成", "创建", "画一个新", "设计"
        ]
        
        has_creation_keyword = any(kw in prompt_lower for kw in creation_keywords)
        has_modification_keyword = any(kw in prompt_lower for kw in modification_keywords)
        
        # Mode logic
        if has_creation_keyword:
            mode = "text2img"
            mode_confidence = 0.85
        elif has_modification_keyword and (has_parent or has_uploaded):
            mode = "img2img"
            mode_confidence = 0.8
        elif has_modification_keyword and not (has_parent or has_uploaded):
            mode = "text2img"
            mode_confidence = 0.6
        elif has_parent or has_uploaded:
            mode = "img2img"
            mode_confidence = 0.65
        else:
            mode = "text2img"
            mode_confidence = 0.7
        
        # ===== Size Detection =====
        size_keywords = {
            "square_hd": [
                "方形", "正方形", "头像", "logo", "图标",
                "square", "avatar", "icon", "profile"
            ],
            "portrait_4_3": [
                "竖屏", "人像", "海报", "竖版",
                "portrait", "vertical", "poster"
            ],
            "portrait_16_9": [
                "竖屏壁纸", "手机壁纸", "竖屏16:9",
                "phone wallpaper", "mobile wallpaper"
            ],
            "landscape_4_3": [
                "横屏", "照片", "相片", "横版",
                "landscape", "horizontal", "photo"
            ],
            "landscape_16_9": [
                "宽屏", "电脑壁纸", "风景", "桌面壁纸",
                "wallpaper", "widescreen", "desktop", "scenery"
            ]
        }
        
        detected_size = "landscape_4_3"  # Default
        size_confidence = 0.7
        
        for size, keywords in size_keywords.items():
            if any(kw in prompt_lower for kw in keywords):
                detected_size = size
                size_confidence = 0.85
                break
        
        reasoning = f"Rule-based: {mode}, {detected_size}"
        
        log.info(
            f"[PromptAnalyzer] Fallback: mode={mode} "
            f"mode_conf={mode_confidence:.2f} "
            f"size={detected_size} "
            f"size_conf={size_confidence:.2f}"
        )
        
        return {
            "mode": mode,
            "mode_confidence": mode_confidence,
            "image_size": detected_size,
            "size_confidence": size_confidence,
            "reasoning": reasoning
        }
    
# ===== Singleton instance =====
_analyzer_instance = None

def get_prompt_analyzer() -> PromptAnalyzer:
    """
    Get singleton PromptAnalyzer instance
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = PromptAnalyzer()
    return _analyzer_instance