"""
Image generation intelligence module for analyzing user intent and optimizing prompts
"""

import re
import logging
from typing import Dict, List, Optional

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS.get("IMAGES", logging.INFO))



STYLE_KEYWORDS = {
    "realistic": ["photorealistic", "8k uhd", "dslr", "soft lighting", "high quality"],
    "anime": ["anime style", "cel shading", "vibrant colors", "studio ghibli"],
    "artistic": ["oil painting", "impressionist", "brushstrokes", "artistic"],
    "cyberpunk": ["neon lights", "futuristic", "cyberpunk", "dark atmosphere"],
    "fantasy": ["magical", "mystical", "ethereal", "fantasy art"],
}

QUALITY_TAGS = [
    "masterpiece",
    "best quality",
    "highly detailed",
    "sharp focus",
    "professional",
]

NEGATIVE_PROMPTS_DEFAULT = [
    "blurry",
    "low quality",
    "distorted",
    "artifacts",
    "watermark",
    "text",
]


class PromptIntelligence:
 
    
    @staticmethod
    def _deduplicate_tags(prompt: str) -> str:
       
        
        tags = [tag.strip().lower() for tag in prompt.split(",") if tag.strip()]
        
        
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        
        return ", ".join(unique_tags)
    
    @staticmethod
    def _extract_quality_issues(feedback: Dict) -> List[str]:
        
        issues = []
        feedback_text = feedback.get("text", "").lower()
        
       
        issue_keywords = {
            "blurry": ["blurry", "blur"],
            "lighting": ["dark", "too bright", "lighting"],
            "composition": ["composition", "framing"],
            "color": ["color", "saturation"],
            "details": ["details", "not detailed"],
        }
        
        for issue_type, keywords in issue_keywords.items():
            if any(kw in feedback_text for kw in keywords):
                issues.append(issue_type)
        
        return issues
    
    @staticmethod
    async def analyze_intent(request: str) -> Dict:
        
        request_lower = request.lower()
        
        
        if any(kw in request_lower for kw in ["generate", "create", "make"]):
            intent = "generate"
        elif any(kw in request_lower for kw in ["modify", "change", "adjust"]):
            intent = "modify"
        elif any(kw in request_lower for kw in ["style", "in the style of"]):
            intent = "style_transfer"
        else:
            intent = "generate"  
        
        
        detected_style = None
        for style, keywords in STYLE_KEYWORDS.items():
            if any(kw in request_lower for kw in keywords):
                detected_style = style
                break
        
        return {
            "intent": intent,
            "detected_style": detected_style,
            "original_request": request,
        }
    
    @staticmethod
    async def optimize_prompt(
        original_prompt: str,
        detected_style: Optional[str] = None,
        enhance_quality: bool = True
    ) -> str:
        
        prompt = PromptIntelligence._deduplicate_tags(original_prompt)
        
        
        if detected_style and detected_style in STYLE_KEYWORDS:
            style_tags = STYLE_KEYWORDS[detected_style]
            
            for tag in style_tags:
                if tag.lower() not in prompt.lower():
                    prompt = f"{prompt}, {tag}"
        
        
        if enhance_quality:
            for tag in QUALITY_TAGS:
                if tag.lower() not in prompt.lower():
                    prompt = f"{prompt}, {tag}"
        
        
        prompt = PromptIntelligence._deduplicate_tags(prompt)
        
        return prompt
    
    @staticmethod
    async def generate_negative_prompt(issues: Optional[List[str]] = None) -> str:
        
        negative_tags = NEGATIVE_PROMPTS_DEFAULT.copy()
        
        
        if issues:
            if "blurry" in issues:
                negative_tags.extend(["out of focus", "motion blur"])
            if "lighting" in issues:
                negative_tags.extend(["overexposed", "underexposed"])
            if "details" in issues:
                negative_tags.extend(["low detail", "simple"])
        
        
        negative_tags = list(dict.fromkeys(negative_tags))
        
        return ", ".join(negative_tags)
    
    @staticmethod
    async def analyze_feedback(feedback: Dict) -> Dict:
        
        rating = feedback.get("rating", "neutral")
        issues = PromptIntelligence._extract_quality_issues(feedback)
        
        suggestions = {
            "prompt_adjustments": [],
            "parameter_adjustments": {},
            "detected_issues": issues,
        }
        
        
        if "blurry" in issues:
            suggestions["prompt_adjustments"].append("Add: 'sharp, high detail, crisp'")
            suggestions["parameter_adjustments"]["steps"] = "+10"  
        
        if "lighting" in issues:
            suggestions["prompt_adjustments"].append("Add: 'well-lit, balanced lighting'")
        
        if "details" in issues:
            suggestions["prompt_adjustments"].append("Add: 'intricate details, ultra detailed'")
            suggestions["parameter_adjustments"]["steps"] = "+15"
        
        if "color" in issues:
            suggestions["prompt_adjustments"].append("Adjust: 'vibrant colors, saturated'")
        
        
        if rating == "positive":
            suggestions["message"] = "Great! These parameters worked well. Consider using similar settings for future generations."
        
        return suggestions
    
    @staticmethod
    async def suggest_variations(base_prompt: str) -> List[str]:
        
        variations = []
        
        
        for style in ["realistic", "anime", "artistic"]:
            if style not in base_prompt.lower():
                style_tags = ", ".join(STYLE_KEYWORDS[style][:2])
                variations.append(f"{base_prompt}, {style_tags}")
        
        
        composition_tags = [
            "close-up shot",
            "wide angle",
            "bird's eye view",
            "cinematic composition",
        ]
        for comp in composition_tags[:2]:  
            variations.append(f"{base_prompt}, {comp}")
        
        return variations[:4]  



_intelligence_instance = None

def get_intelligence() -> PromptIntelligence:
    
    global _intelligence_instance
    if _intelligence_instance is None:
        _intelligence_instance = PromptIntelligence()
    return _intelligence_instance