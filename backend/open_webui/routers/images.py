
import asyncio
import base64
import io
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from open_webui.config import CACHE_DIR
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS, SRC_LOG_LEVELS
from open_webui.routers.files import upload_file
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.images.comfyui import (
    ComfyUIGenerateImageForm,
    ComfyUIWorkflow,
    comfyui_generate_image,
)
from pydantic import BaseModel

try:
    from PIL import Image
except ImportError:
    Image = None

'''Perryswork 0v0'''
from open_webui.utils.images.intelligence import get_intelligence
from open_webui.utils.images.project_manager import get_project_manager
'''Perryswork 0v0'''

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["IMAGES"])

IMAGE_CACHE_DIR = CACHE_DIR / "image" / "generations"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


# ==================== Configuration Endpoints ====================

@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "enabled": request.app.state.config.ENABLE_IMAGE_GENERATION,
        "engine": request.app.state.config.IMAGE_GENERATION_ENGINE,
        "prompt_generation": request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION,
        "openai": {
            "OPENAI_API_BASE_URL": request.app.state.config.IMAGES_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.IMAGES_OPENAI_API_KEY,
        },
        "automatic1111": {
            "AUTOMATIC1111_BASE_URL": request.app.state.config.AUTOMATIC1111_BASE_URL,
            "AUTOMATIC1111_API_AUTH": request.app.state.config.AUTOMATIC1111_API_AUTH,
            "AUTOMATIC1111_CFG_SCALE": request.app.state.config.AUTOMATIC1111_CFG_SCALE,
            "AUTOMATIC1111_SAMPLER": request.app.state.config.AUTOMATIC1111_SAMPLER,
            "AUTOMATIC1111_SCHEDULER": request.app.state.config.AUTOMATIC1111_SCHEDULER,
        },
        "comfyui": {
            "COMFYUI_BASE_URL": request.app.state.config.COMFYUI_BASE_URL,
            "COMFYUI_API_KEY": request.app.state.config.COMFYUI_API_KEY,
            "COMFYUI_WORKFLOW": request.app.state.config.COMFYUI_WORKFLOW,
            "COMFYUI_WORKFLOW_NODES": request.app.state.config.COMFYUI_WORKFLOW_NODES,
        },
        "gemini": {
            "GEMINI_API_BASE_URL": request.app.state.config.IMAGES_GEMINI_API_BASE_URL,
            "GEMINI_API_KEY": request.app.state.config.IMAGES_GEMINI_API_KEY,
        },
    }


class OpenAIConfigForm(BaseModel):
    OPENAI_API_BASE_URL: str
    OPENAI_API_KEY: str


class Automatic1111ConfigForm(BaseModel):
    AUTOMATIC1111_BASE_URL: str
    AUTOMATIC1111_API_AUTH: str
    AUTOMATIC1111_CFG_SCALE: Optional[str | float | int]
    AUTOMATIC1111_SAMPLER: Optional[str]
    AUTOMATIC1111_SCHEDULER: Optional[str]


class ComfyUIConfigForm(BaseModel):
    COMFYUI_BASE_URL: str
    COMFYUI_API_KEY: str
    COMFYUI_WORKFLOW: str
    COMFYUI_WORKFLOW_NODES: list[dict]


class GeminiConfigForm(BaseModel):
    GEMINI_API_BASE_URL: str
    GEMINI_API_KEY: str


class ConfigForm(BaseModel):
    enabled: bool
    engine: str
    prompt_generation: bool
    openai: OpenAIConfigForm
    automatic1111: Automatic1111ConfigForm
    comfyui: ComfyUIConfigForm
    gemini: GeminiConfigForm


@router.post("/config/update")
async def update_config(
    request: Request, form_data: ConfigForm, user=Depends(get_admin_user)
):
    request.app.state.config.IMAGE_GENERATION_ENGINE = form_data.engine
    request.app.state.config.ENABLE_IMAGE_GENERATION = form_data.enabled
    request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION = form_data.prompt_generation

    request.app.state.config.IMAGES_OPENAI_API_BASE_URL = form_data.openai.OPENAI_API_BASE_URL
    request.app.state.config.IMAGES_OPENAI_API_KEY = form_data.openai.OPENAI_API_KEY

    request.app.state.config.IMAGES_GEMINI_API_BASE_URL = form_data.gemini.GEMINI_API_BASE_URL
    request.app.state.config.IMAGES_GEMINI_API_KEY = form_data.gemini.GEMINI_API_KEY

    request.app.state.config.AUTOMATIC1111_BASE_URL = form_data.automatic1111.AUTOMATIC1111_BASE_URL
    request.app.state.config.AUTOMATIC1111_API_AUTH = form_data.automatic1111.AUTOMATIC1111_API_AUTH
    request.app.state.config.AUTOMATIC1111_CFG_SCALE = (
        float(form_data.automatic1111.AUTOMATIC1111_CFG_SCALE)
        if form_data.automatic1111.AUTOMATIC1111_CFG_SCALE
        else None
    )
    request.app.state.config.AUTOMATIC1111_SAMPLER = (
        form_data.automatic1111.AUTOMATIC1111_SAMPLER
        if form_data.automatic1111.AUTOMATIC1111_SAMPLER
        else None
    )
    request.app.state.config.AUTOMATIC1111_SCHEDULER = (
        form_data.automatic1111.AUTOMATIC1111_SCHEDULER
        if form_data.automatic1111.AUTOMATIC1111_SCHEDULER
        else None
    )

    request.app.state.config.COMFYUI_BASE_URL = form_data.comfyui.COMFYUI_BASE_URL.strip("/")
    request.app.state.config.COMFYUI_API_KEY = form_data.comfyui.COMFYUI_API_KEY
    request.app.state.config.COMFYUI_WORKFLOW = form_data.comfyui.COMFYUI_WORKFLOW
    request.app.state.config.COMFYUI_WORKFLOW_NODES = form_data.comfyui.COMFYUI_WORKFLOW_NODES

    return {
        "enabled": request.app.state.config.ENABLE_IMAGE_GENERATION,
        "engine": request.app.state.config.IMAGE_GENERATION_ENGINE,
        "prompt_generation": request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION,
        "openai": {
            "OPENAI_API_BASE_URL": request.app.state.config.IMAGES_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.IMAGES_OPENAI_API_KEY,
        },
        "automatic1111": {
            "AUTOMATIC1111_BASE_URL": request.app.state.config.AUTOMATIC1111_BASE_URL,
            "AUTOMATIC1111_API_AUTH": request.app.state.config.AUTOMATIC1111_API_AUTH,
            "AUTOMATIC1111_CFG_SCALE": request.app.state.config.AUTOMATIC1111_CFG_SCALE,
            "AUTOMATIC1111_SAMPLER": request.app.state.config.AUTOMATIC1111_SAMPLER,
            "AUTOMATIC1111_SCHEDULER": request.app.state.config.AUTOMATIC1111_SCHEDULER,
        },
        "comfyui": {
            "COMFYUI_BASE_URL": request.app.state.config.COMFYUI_BASE_URL,
            "COMFYUI_API_KEY": request.app.state.config.COMFYUI_API_KEY,
            "COMFYUI_WORKFLOW": request.app.state.config.COMFYUI_WORKFLOW,
            "COMFYUI_WORKFLOW_NODES": request.app.state.config.COMFYUI_WORKFLOW_NODES,
        },
        "gemini": {
            "GEMINI_API_BASE_URL": request.app.state.config.IMAGES_GEMINI_API_BASE_URL,
            "GEMINI_API_KEY": request.app.state.config.IMAGES_GEMINI_API_KEY,
        },
    }


@router.get("/config/url/verify")
async def verify_url(request: Request, user=Depends(get_admin_user)):
    if request.app.state.config.IMAGE_GENERATION_ENGINE == "automatic1111":
        try:
            r = requests.get(
                url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/options",
                headers={"authorization": get_automatic1111_api_auth(request)},
            )
            r.raise_for_status()
            return True
        except Exception:
            request.app.state.config.ENABLE_IMAGE_GENERATION = False
            raise HTTPException(status_code=400, detail=ERROR_MESSAGES.INVALID_URL)
    elif request.app.state.config.IMAGE_GENERATION_ENGINE == "comfyui":
        headers = None
        if request.app.state.config.COMFYUI_API_KEY:
            headers = {"Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"}
        try:
            r = requests.get(
                url=f"{request.app.state.config.COMFYUI_BASE_URL}/object_info",
                headers=headers,
            )
            r.raise_for_status()
            return True
        except Exception:
            request.app.state.config.ENABLE_IMAGE_GENERATION = False
            raise HTTPException(status_code=400, detail=ERROR_MESSAGES.INVALID_URL)
    else:
        return True


# ==================== Intelligent Generation Endpoints ====================

class IntelligentGenerationForm(BaseModel):
    """Form for intelligent image generation"""
    user_input: str
    project_id: Optional[str] = None
    continue_project: bool = False


class FeedbackForm(BaseModel):
    """Form for providing feedback"""
    feedback: str
    version: int


@router.post("/intelligent/generate")
async def intelligent_generate(
    request: Request,
    form_data: IntelligentGenerationForm,
    user=Depends(get_verified_user)
):
    try:
        intelligence = get_intelligence()
        manager = get_project_manager()
        
        # Analyze intent
        intent_analysis = await intelligence.analyze_intent(form_data.user_input)
        log.info(f"Intent analysis: {intent_analysis}")
        
        # Optimize prompt
        optimized_prompt = await intelligence.optimize_prompt(
            form_data.user_input,
            detected_style=intent_analysis.get("detected_style"),
            enhance_quality=True
        )
        log.info(f"Optimized prompt: {optimized_prompt}")
        
        # Generate negative prompt
        negative_prompt = await intelligence.generate_negative_prompt()
        
        # Create generation form
        generation_form = GenerateImageForm(
            prompt=optimized_prompt,
            negative_prompt=negative_prompt,
            n=1,
            size=request.app.state.config.IMAGE_SIZE
        )
        
        try:
            images = await image_generations(request, generation_form, user)
        except Exception as e:
            log.error(f"Image generation failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Image generation service failed: {str(e)[:100]}"
            )
        
        if not images or len(images) == 0:
            raise HTTPException(
                status_code=500,
                detail="Image generation returned empty result"
            )
        
        image_urls = [img["url"] for img in images]
        
        # Save to project
        if form_data.project_id and form_data.continue_project:
            project = manager.add_version(
                project_id=form_data.project_id,
                user_id=user.id,
                request=form_data.user_input,
                image_urls=image_urls,
                optimized_prompt=optimized_prompt,
                metadata={
                    "intent": intent_analysis["intent"],
                    "detected_style": intent_analysis.get("detected_style"),
                    "negative_prompt": negative_prompt,
                    "parameters": {
                        "size": request.app.state.config.IMAGE_SIZE,
                        "steps": request.app.state.config.IMAGE_STEPS,
                    }
                }
            )
            version_num = len(project["versions"])
            project_id = form_data.project_id
        else:
            project = manager.create_project(
                user_id=user.id,
                initial_request=form_data.user_input,
                image_urls=image_urls,
                optimized_prompt=optimized_prompt,
                metadata={
                    "intent": intent_analysis["intent"],
                    "detected_style": intent_analysis.get("detected_style"),
                    "negative_prompt": negative_prompt,
                    "parameters": {
                        "size": request.app.state.config.IMAGE_SIZE,
                        "steps": request.app.state.config.IMAGE_STEPS,
                    }
                }
            )
            project_id = project["project_id"]
            version_num = 1
        
        log.info(f"Created/updated project {project_id} for user {user.id}")
        
        return {
            "success": True,
            "project_id": project_id,
            "version": version_num,
            "images": images,
            "original_request": form_data.user_input,
            "optimized_prompt": optimized_prompt,
            "negative_prompt": negative_prompt,
            "intent_analysis": intent_analysis,
            "suggestions": [
                "You can provide feedback to improve the image",
                "Try different styles or modifications",
                "Request specific changes to iterate"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"Intelligent generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {str(e)[:100]}"
        )


@router.post("/projects/{project_id}/feedback")
async def add_feedback(
    request: Request,
    project_id: str,
    form_data: FeedbackForm,
    user=Depends(get_verified_user)
):
    try:
        manager = get_project_manager()
        intelligence = get_intelligence()
        
        project = manager.get_project_metadata(project_id, user.id)
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        target_version = next(
            (v for v in project["versions"] if v["version"] == form_data.version),
            None
        )
        
        if not target_version:
            raise HTTPException(
                status_code=404,
                detail=f"Version {form_data.version} not found"
            )
        
        analysis = await intelligence.analyze_feedback({
            "rating": "neutral",
            "text": form_data.feedback,
        })
        
        updated_project = manager.add_feedback(
            project_id=project_id,
            user_id=user.id,
            version=form_data.version,
            feedback={
                "text": form_data.feedback,
                "rating": "neutral",
                **analysis
            }
        )
        
        log.info(f"Feedback added to project {project_id} version {form_data.version}")
        
        return {
            "success": True,
            "message": "Feedback saved successfully",
            "analysis": analysis,
            "next_steps": [
                "Generate a new version with improvements",
                "Try the suggested modifications",
                "Adjust the style or composition"
            ]
        }
        
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"Failed to add feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add feedback: {str(e)[:100]}"
        )


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    user=Depends(get_verified_user)
):
    """Get project history"""
    try:
        manager = get_project_manager()
        metadata = manager.get_project_metadata(project_id, user.id)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {
            "success": True,
            "project": metadata
        }
        
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"Failed to get project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get project: {str(e)[:100]}"
        )


@router.get("/projects")
async def list_projects(user=Depends(get_verified_user)):
    """List all user projects"""
    try:
        manager = get_project_manager()
        projects = manager.list_user_projects(user.id)
        
        return {
            "success": True,
            "projects": projects,
            "count": len(projects)
        }
        
    except Exception as e:
        log.exception(f"Failed to list projects: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list projects: {str(e)[:100]}"
        )


# ==================== Perry's Multi-Image Processing Endpoints ====================

'''Perry's Work 0v0 - Multi-Image Processing'''


async def process_multimodal_images(
    primary_image_data: bytes,
    secondary_image_data: Optional[bytes] = None,
    tertiary_image_data: Optional[bytes] = None,
) -> dict:
    """
    Process multiple images for multimodal generation
    
    Args:
        primary_image_data: Main subject image bytes
        secondary_image_data: Optional secondary reference image
        tertiary_image_data: Optional tertiary reference image
    
    Returns:
        dict: Processed images with base64 encoding and metadata
    """
    if Image is None:
        raise HTTPException(
            status_code=500, 
            detail="PIL library not installed. Install with: pip install Pillow"
        )
    
    processed = {}
    
    # Process primary image
    primary_img = Image.open(io.BytesIO(primary_image_data))
    if primary_img.mode != 'RGB':
        primary_img = primary_img.convert('RGB')
    
    # Resize if needed
    max_size = 1024
    if primary_img.width > max_size or primary_img.height > max_size:
        primary_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    buffer = io.BytesIO()
    primary_img.save(buffer, format="JPEG", quality=90)
    processed['primary'] = base64.b64encode(buffer.getvalue()).decode()
    
    # Process secondary image if provided
    if secondary_image_data:
        secondary_img = Image.open(io.BytesIO(secondary_image_data))
        if secondary_img.mode != 'RGB':
            secondary_img = secondary_img.convert('RGB')
        if secondary_img.width > max_size or secondary_img.height > max_size:
            secondary_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        secondary_img.save(buffer, format="JPEG", quality=90)
        processed['secondary'] = base64.b64encode(buffer.getvalue()).decode()
    
    # Process tertiary image if provided
    if tertiary_image_data:
        tertiary_img = Image.open(io.BytesIO(tertiary_image_data))
        if tertiary_img.mode != 'RGB':
            tertiary_img = tertiary_img.convert('RGB')
        if tertiary_img.width > max_size or tertiary_img.height > max_size:
            tertiary_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        tertiary_img.save(buffer, format="JPEG", quality=90)
        processed['tertiary'] = base64.b64encode(buffer.getvalue()).decode()
    
    return processed


def build_fashion_transfer_prompt(
    base_prompt: str,
    clothing_type: str,
    fit_adjustment: str = "well-fitted",
    lighting: str = "natural lighting",
) -> str:
    """Build specialized prompt for fashion transfer"""
    prompt_parts = [
        base_prompt,
        f"person wearing {clothing_type}",
        fit_adjustment,
        lighting,
        f"Transfer the {clothing_type} from reference image onto the person",
        "Maintain original pose and appearance",
        "High quality, realistic, detailed clothing texture, proper fit and draping"
    ]
    
    return ", ".join(prompt_parts)


def build_multimodal_prompt(
    main_prompt: str,
    primary_prompt: str = "",
    secondary_prompt: str = "",
    tertiary_prompt: str = "",
    composition_prompt: str = "",
) -> str:
    """Build comprehensive prompt for multimodal generation"""
    parts = [main_prompt]
    
    if primary_prompt:
        parts.append(f"Primary element: {primary_prompt}")
    if secondary_prompt:
        parts.append(f"Secondary element: {secondary_prompt}")
    if tertiary_prompt:
        parts.append(f"Background/Environment: {tertiary_prompt}")
    if composition_prompt:
        parts.append(f"Composition: {composition_prompt}")
    
    return ". ".join(parts)


@router.post("/generations/multimodal-advanced")
async def image_multimodal_advanced_generation(
    request: Request,
    primary_image: UploadFile = File(..., description="Main subject image"),
    secondary_image: Optional[UploadFile] = File(None, description="Secondary reference image"),
    tertiary_image: Optional[UploadFile] = File(None, description="Third reference image"),
    prompt: str = Form(..., description="Main generation prompt"),
    primary_prompt: str = Form("", description="Specific instructions for primary image"),
    secondary_prompt: str = Form("", description="Specific instructions for secondary image"),
    tertiary_prompt: str = Form("", description="Specific instructions for tertiary image"),
    negative_prompt: str = Form("", description="What to avoid"),
    width: int = Form(1024, description="Output width"),
    height: int = Form(1024, description="Output height"),
    primary_weight: float = Form(0.6, description="Primary image influence (0.0-1.0)"),
    secondary_weight: float = Form(0.3, description="Secondary image influence (0.0-1.0)"),
    tertiary_weight: float = Form(0.1, description="Tertiary image influence (0.0-1.0)"),
    user=Depends(get_verified_user),
):
    """
    Advanced multimodal generation with up to 3 images and complex instructions
    
    Examples:
    - Fashion: Person + Clothing + Background scene
    - Interior: Furniture + Color scheme + Room layout
    - Character: Base character + Outfit + Environment
    """
    log.info(f"Advanced multimodal request from user {user.id}")
    
    try:
        # Process images
        primary_data = await primary_image.read()
        primary_base64 = base64.b64encode(primary_data).decode()
        
        secondary_base64 = None
        if secondary_image:
            secondary_data = await secondary_image.read()
            secondary_base64 = base64.b64encode(secondary_data).decode()
        
        tertiary_base64 = None
        if tertiary_image:
            tertiary_data = await tertiary_image.read()
            tertiary_base64 = base64.b64encode(tertiary_data).decode()
        
        # Build comprehensive prompt
        full_prompt_parts = [prompt]
        if primary_prompt:
            full_prompt_parts.append(f"Primary: {primary_prompt}")
        if secondary_prompt and secondary_image:
            full_prompt_parts.append(f"Secondary: {secondary_prompt}")
        if tertiary_prompt and tertiary_image:
            full_prompt_parts.append(f"Background: {tertiary_prompt}")
        
        combined_prompt = ". ".join(full_prompt_parts)
        
        # Prepare metadata for image upload
        metadata = {
            "prompt": combined_prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "type": "multimodal-advanced",
            "images_used": sum([1, 1 if secondary_image else 0, 1 if tertiary_image else 0])
        }
        
        # Use ComfyUI workflow
        form_data = ComfyUIGenerateImageForm(
            **{
                "workflow": ComfyUIWorkflow(
                    **{
                        "workflow": request.app.state.config.COMFYUI_WORKFLOW,
                        "nodes": request.app.state.config.COMFYUI_WORKFLOW_NODES,
                    }
                ),
                "prompt": combined_prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "n": 1,
            }
        )
        
        res = await comfyui_generate_image(
            request.app.state.config.IMAGE_GENERATION_MODEL,
            form_data,
            user.id,
            request.app.state.config.COMFYUI_BASE_URL,
            request.app.state.config.COMFYUI_API_KEY,
        )
        
        images = []
        for image in res["data"]:
            headers = None
            if request.app.state.config.COMFYUI_API_KEY:
                headers = {
                    "Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"
                }
            
            image_data, content_type = load_url_image_data(image["url"], headers)
            url = upload_image(request, metadata, image_data, content_type, user)
            images.append({"url": url})
        
        return images
        
    except Exception as e:
        log.error(f"Fashion transfer failed: {str(e)}")
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


'''Perry's work end here 0v0'''


# ==================== Helper Functions ====================

def get_automatic1111_api_auth(request: Request):
    if request.app.state.config.AUTOMATIC1111_API_AUTH is None:
        return ""
    else:
        auth1111_byte_string = request.app.state.config.AUTOMATIC1111_API_AUTH.encode("utf-8")
        auth1111_base64_encoded_bytes = base64.b64encode(auth1111_byte_string)
        auth1111_base64_encoded_string = auth1111_base64_encoded_bytes.decode("utf-8")
        return f"Basic {auth1111_base64_encoded_string}"


def set_image_model(request: Request, model: str):
    log.info(f"Setting image model to {model}")
    request.app.state.config.IMAGE_GENERATION_MODEL = model
    if request.app.state.config.IMAGE_GENERATION_ENGINE in ["", "automatic1111"]:
        api_auth = get_automatic1111_api_auth(request)
        r = requests.get(
            url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/options",
            headers={"authorization": api_auth},
        )
        options = r.json()
        if model != options["sd_model_checkpoint"]:
            options["sd_model_checkpoint"] = model
            r = requests.post(
                url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/options",
                json=options,
                headers={"authorization": api_auth},
            )
    return request.app.state.config.IMAGE_GENERATION_MODEL


def get_image_model(request):
    if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else "dall-e-2"
        )
    elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else "imagen-3.0-generate-002"
        )
    elif request.app.state.config.IMAGE_GENERATION_ENGINE == "comfyui":
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else ""
        )
    elif (
        request.app.state.config.IMAGE_GENERATION_ENGINE == "automatic1111"
        or request.app.state.config.IMAGE_GENERATION_ENGINE == ""
    ):
        try:
            r = requests.get(
                url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/options",
                headers={"authorization": get_automatic1111_api_auth(request)},
            )
            options = r.json()
            return options["sd_model_checkpoint"]
        except Exception as e:
            request.app.state.config.ENABLE_IMAGE_GENERATION = False
            raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


def load_b64_image_data(b64_str):
    try:
        if "," in b64_str:
            header, encoded = b64_str.split(",", 1)
            mime_type = header.split(";")[0]
            img_data = base64.b64decode(encoded)
        else:
            mime_type = "image/png"
            img_data = base64.b64decode(b64_str)
        return img_data, mime_type
    except Exception as e:
        log.exception(f"Error loading image data: {e}")
        return None


def load_url_image_data(url, headers=None):
    try:
        if headers:
            r = requests.get(url, headers=headers)
        else:
            r = requests.get(url)

        r.raise_for_status()
        if r.headers["content-type"].split("/")[0] == "image":
            mime_type = r.headers["content-type"]
            return r.content, mime_type
        else:
            log.error("Url does not point to an image.")
            return None

    except Exception as e:
        log.exception(f"Error saving image: {e}")
        return None


def upload_image(request, image_metadata, image_data, content_type, user):
    image_format = mimetypes.guess_extension(content_type)
    file = UploadFile(
        file=io.BytesIO(image_data),
        filename=f"generated-image{image_format}",
        headers={
            "content-type": content_type,
        },
    )
    file_item = upload_file(request, file, user, file_metadata=image_metadata)
    url = request.app.url_path_for("get_file_content_by_id", id=file_item.id)
    return url


# ==================== Image Configuration ====================

class ImageConfigForm(BaseModel):
    MODEL: str
    IMAGE_SIZE: str
    IMAGE_STEPS: int


@router.get("/image/config")
async def get_image_config(request: Request, user=Depends(get_admin_user)):
    return {
        "MODEL": request.app.state.config.IMAGE_GENERATION_MODEL,
        "IMAGE_SIZE": request.app.state.config.IMAGE_SIZE,
        "IMAGE_STEPS": request.app.state.config.IMAGE_STEPS,
    }


@router.post("/image/config/update")
async def update_image_config(
    request: Request, form_data: ImageConfigForm, user=Depends(get_admin_user)
):
    set_image_model(request, form_data.MODEL)

    pattern = r"^\d+x\d+$"
    if re.match(pattern, form_data.IMAGE_SIZE):
        request.app.state.config.IMAGE_SIZE = form_data.IMAGE_SIZE
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT("  (e.g., 512x512)."),
        )

    if form_data.IMAGE_STEPS >= 0:
        request.app.state.config.IMAGE_STEPS = form_data.IMAGE_STEPS
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT("  (e.g., 50)."),
        )

    return {
        "MODEL": request.app.state.config.IMAGE_GENERATION_MODEL,
        "IMAGE_SIZE": request.app.state.config.IMAGE_SIZE,
        "IMAGE_STEPS": request.app.state.config.IMAGE_STEPS,
    }


# ==================== Models Management ====================

@router.get("/models")
def get_models(request: Request, user=Depends(get_verified_user)):
    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":
            return [
                {"id": "dall-e-2", "name": "DALL·E 2"},
                {"id": "dall-e-3", "name": "DALL·E 3"},
            ]
        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
            return [
                {"id": "imagen-3-0-generate-002", "name": "imagen-3.0 generate-002"},
            ]
        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "comfyui":
            headers = {
                "Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"
            }
            r = requests.get(
                url=f"{request.app.state.config.COMFYUI_BASE_URL}/object_info",
                headers=headers,
            )
            info = r.json()

            workflow = json.loads(request.app.state.config.COMFYUI_WORKFLOW)
            model_node_id = None

            for node in request.app.state.config.COMFYUI_WORKFLOW_NODES:
                if node["type"] == "model":
                    if node["node_ids"]:
                        model_node_id = node["node_ids"][0]
                    break

            if model_node_id:
                model_list_key = None

                log.info(workflow[model_node_id]["class_type"])
                for key in info[workflow[model_node_id]["class_type"]]["input"]["required"]:
                    if "_name" in key:
                        model_list_key = key
                        break

                if model_list_key:
                    return list(
                        map(
                            lambda model: {"id": model, "name": model},
                            info[workflow[model_node_id]["class_type"]]["input"]["required"][model_list_key][0],
                        )
                    )
            else:
                return list(
                    map(
                        lambda model: {"id": model, "name": model},
                        info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0],
                    )
                )
        elif (
            request.app.state.config.IMAGE_GENERATION_ENGINE == "automatic1111"
            or request.app.state.config.IMAGE_GENERATION_ENGINE == ""
        ):
            r = requests.get(
                url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/sd-models",
                headers={"authorization": get_automatic1111_api_auth(request)},
            )
            models = r.json()
            return list(
                map(
                    lambda model: {"id": model["title"], "name": model["model_name"]},
                    models,
                )
            )
    except Exception as e:
        request.app.state.config.ENABLE_IMAGE_GENERATION = False
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


# ==================== Image Generation ====================

class GenerateImageForm(BaseModel):
    model: Optional[str] = None
    prompt: str
    size: Optional[str] = None
    n: int = 1
    negative_prompt: Optional[str] = None


@router.post("/generations")
async def image_generations(
    request: Request,
    form_data: GenerateImageForm,
    user=Depends(get_verified_user),
):
    width, height = tuple(map(int, request.app.state.config.IMAGE_SIZE.split("x")))

    r = None
    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":
            headers = {}
            headers["Authorization"] = f"Bearer {request.app.state.config.IMAGES_OPENAI_API_KEY}"
            headers["Content-Type"] = "application/json"

            if ENABLE_FORWARD_USER_INFO_HEADERS:
                headers["X-OpenWebUI-User-Name"] = user.name
                headers["X-OpenWebUI-User-Id"] = user.id
                headers["X-OpenWebUI-User-Email"] = user.email
                headers["X-OpenWebUI-User-Role"] = user.role

            data = {
                "model": (
                    request.app.state.config.IMAGE_GENERATION_MODEL
                    if request.app.state.config.IMAGE_GENERATION_MODEL != ""
                    else "dall-e-2"
                ),
                "prompt": form_data.prompt,
                "n": form_data.n,
                "size": (
                    form_data.size
                    if form_data.size
                    else request.app.state.config.IMAGE_SIZE
                ),
                "response_format": "b64_json",
            }

            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.IMAGES_OPENAI_API_BASE_URL}/images/generations",
                json=data,
                headers=headers,
            )

            r.raise_for_status()
            res = r.json()

            images = []

            for image in res["data"]:
                if image_url := image.get("url", None):
                    image_data, content_type = load_url_image_data(image_url, headers)
                else:
                    image_data, content_type = load_b64_image_data(image["b64_json"])

                url = upload_image(request, data, image_data, content_type, user)
                images.append({"url": url})
            
            return images

        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
            headers = {}
            headers["Content-Type"] = "application/json"
            headers["x-goog-api-key"] = request.app.state.config.IMAGES_GEMINI_API_KEY

            model = get_image_model(request)
            data = {
                "instances": {"prompt": form_data.prompt},
                "parameters": {
                    "sampleCount": form_data.n,
                    "outputOptions": {"mimeType": "image/png"},
                },
            }

            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.IMAGES_GEMINI_API_BASE_URL}/models/{model}:predict",
                json=data,
                headers=headers,
            )

            r.raise_for_status()
            res = r.json()

            images = []
            for image in res["predictions"]:
                image_data, content_type = load_b64_image_data(image["bytesBase64Encoded"])
                url = upload_image(request, data, image_data, content_type, user)
                images.append({"url": url})

            return images

        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "comfyui":
            data = {
                "prompt": form_data.prompt,
                "width": width,
                "height": height,
                "n": form_data.n,
            }

            if request.app.state.config.IMAGE_STEPS is not None:
                data["steps"] = request.app.state.config.IMAGE_STEPS

            if form_data.negative_prompt is not None:
                data["negative_prompt"] = form_data.negative_prompt

            form_data = ComfyUIGenerateImageForm(
                **{
                    "workflow": ComfyUIWorkflow(
                        **{
                            "workflow": request.app.state.config.COMFYUI_WORKFLOW,
                            "nodes": request.app.state.config.COMFYUI_WORKFLOW_NODES,
                        }
                    ),
                    **data,
                }
            )
            res = await comfyui_generate_image(
                request.app.state.config.IMAGE_GENERATION_MODEL,
                form_data,
                user.id,
                request.app.state.config.COMFYUI_BASE_URL,
                request.app.state.config.COMFYUI_API_KEY,
            )
            log.debug(f"res: {res}")

            images = []

            for image in res["data"]:
                headers = None
                if request.app.state.config.COMFYUI_API_KEY:
                    headers = {
                        "Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"
                    }

                image_data, content_type = load_url_image_data(image["url"], headers)
                url = upload_image(
                    request,
                    form_data.model_dump(exclude_none=True),
                    image_data,
                    content_type,
                    user,
                )
                images.append({"url": url})
            
            return images
            
        elif (
            request.app.state.config.IMAGE_GENERATION_ENGINE == "automatic1111"
            or request.app.state.config.IMAGE_GENERATION_ENGINE == ""
        ):
            if form_data.model:
                set_image_model(request, form_data.model)

            data = {
                "prompt": form_data.prompt,
                "batch_size": form_data.n,
                "width": width,
                "height": height,
            }

            if request.app.state.config.IMAGE_STEPS is not None:
                data["steps"] = request.app.state.config.IMAGE_STEPS

            if form_data.negative_prompt is not None:
                data["negative_prompt"] = form_data.negative_prompt

            if request.app.state.config.AUTOMATIC1111_CFG_SCALE:
                data["cfg_scale"] = request.app.state.config.AUTOMATIC1111_CFG_SCALE

            if request.app.state.config.AUTOMATIC1111_SAMPLER:
                data["sampler_name"] = request.app.state.config.AUTOMATIC1111_SAMPLER

            if request.app.state.config.AUTOMATIC1111_SCHEDULER:
                data["scheduler"] = request.app.state.config.AUTOMATIC1111_SCHEDULER

            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.AUTOMATIC1111_BASE_URL}/sdapi/v1/txt2img",
                json=data,
                headers={"authorization": get_automatic1111_api_auth(request)},
            )

            res = r.json()
            log.debug(f"res: {res}")

            images = []

            for image in res["images"]:
                image_data, content_type = load_b64_image_data(image)
                url = upload_image(
                    request,
                    {**data, "info": res["info"]},
                    image_data,
                    content_type,
                    user,
                )
                images.append({"url": url})
            
            return images
            
    except Exception as e:
        error = e
        if r is not None:
            try:
                data = r.json()
                if "error" in data:
                    error = data["error"]["message"]
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))
        
        
    except Exception as e:
        log.error(f"Advanced multimodal generation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


@router.post("/generations/fashion-transfer")
async def image_fashion_transfer(
    request: Request,
    person_image: UploadFile = File(..., description="Photo of the person"),
    clothing_image: UploadFile = File(..., description="Clothing item to transfer"),
    scene_image: Optional[UploadFile] = File(None, description="Background scene (optional)"),
    prompt: str = Form("high quality fashion photo", description="Style description"),
    clothing_type: str = Form("clothing", description="Type of clothing (shirt, dress, pants, etc.)"),
    negative_prompt: str = Form("blurry, distorted, unrealistic", description="What to avoid"),
    width: int = Form(1024, description="Output width"),
    height: int = Form(1024, description="Output height"),
    clothing_strength: float = Form(0.8, description="How strongly to apply clothing (0.0-1.0)"),
    user=Depends(get_verified_user),
):
    """
    Specialized fashion transfer endpoint
    
    Perfect for: "Put the shirt from image 1 on the person in image 2, in the scene from image 3"
    """
    log.info(f"Fashion transfer request: {clothing_type} from user {user.id}")
    
    try:
        # Process images
        person_data = await person_image.read()
        person_base64 = base64.b64encode(person_data).decode()
        
        clothing_data = await clothing_image.read()
        clothing_base64 = base64.b64encode(clothing_data).decode()
        
        scene_base64 = None
        if scene_image:
            scene_data = await scene_image.read()
            scene_base64 = base64.b64encode(scene_data).decode()
    


        # Build specialized fashion prompt
        fashion_prompt = build_fashion_transfer_prompt(prompt, clothing_type)
        
        # Prepare metadata
        metadata = {
            "prompt": fashion_prompt,
            "negative_prompt": f"{negative_prompt}, wrong size, floating clothes",
            "width": width,
            "height": height,
            "type": "fashion-transfer",
            "clothing_type": clothing_type,
            "clothing_strength": clothing_strength
        }
        
        # Use ComfyUI workflow
        form_data = ComfyUIGenerateImageForm(
            **{
                "workflow": ComfyUIWorkflow(
                    **{
                        "workflow": request.app.state.config.COMFYUI_WORKFLOW,
                        "nodes": request.app.state.config.COMFYUI_WORKFLOW_NODES,
                    }
                ),
                "prompt": fashion_prompt,
                "negative_prompt": metadata["negative_prompt"],
                "width": width,
                "height": height,
                "n": 1,
            }
        )
        
        res = await comfyui_generate_image(
            request.app.state.config.IMAGE_GENERATION_MODEL,
            form_data,
            user.id,
            request.app.state.config.COMFYUI_BASE_URL,
            request.app.state.config.COMFYUI_API_KEY,
        )
        
        images = []
        for image in res["data"]:
            headers = None
            if request.app.state.config.COMFYUI_API_KEY:
                headers = {
                    "Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"
                }       
    
            image_data, content_type = load_url_image_data(image["url"], headers)
            url = upload_image(request, metadata, image_data, content_type, user)
            images.append({"url": url})

        return images
    except Exception as e:
        log.error(f"Advanced multimodal generation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))
