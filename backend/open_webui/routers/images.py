import asyncio
import base64
import time
import io
import json
import logging
import mimetypes
import re
import logging
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
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
from open_webui.models.image_sessions import ImageSessions, ImageSessionForm
from open_webui.models.chats import Chats
from open_webui.utils.images.fal_flux import FalFluxClient
from open_webui.utils.images.prompt_analyzer import PromptAnalyzer
from open_webui.models.files import Files
from pydantic import BaseModel


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["IMAGES"])

IMAGE_CACHE_DIR = CACHE_DIR / "image" / "generations"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


router = APIRouter()

# Global PromptAnalyzer instance
_prompt_analyzer = None

def get_prompt_analyzer() -> PromptAnalyzer:
    """Get or create PromptAnalyzer singleton"""
    global _prompt_analyzer
    if _prompt_analyzer is None:
        _prompt_analyzer = PromptAnalyzer()
    return _prompt_analyzer
################


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
        #################fal
        "fal": {
            "FAL_API_KEY": request.app.state.config.FAL_API_KEY,
            "FAL_API_BASE_URL": request.app.state.config.FAL_API_BASE_URL,
            "FAL_MODEL": request.app.state.config.FAL_MODEL,  # 🆕 NEW
            "ENABLE_FAL_SMART_MODE": request.app.state.config.ENABLE_FAL_SMART_MODE,
            "FAL_OPENAI_API_KEY": request.app.state.config.FAL_OPENAI_API_KEY,
            "FAL_DEFAULT_IMAGE_SIZE": request.app.state.config.FAL_DEFAULT_IMAGE_SIZE,
            "FAL_NUM_INFERENCE_STEPS": request.app.state.config.FAL_NUM_INFERENCE_STEPS,
            "FAL_GUIDANCE_SCALE": request.app.state.config.FAL_GUIDANCE_SCALE,
        },
        ##########
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

##############fal
class FalConfigForm(BaseModel):
    FAL_API_KEY: str
    FAL_API_BASE_URL: Optional[str] = "https://fal.run"
    FAL_MODEL: str  # 🆕 NEW
    ENABLE_FAL_SMART_MODE: bool
    FAL_OPENAI_API_KEY: Optional[str] = "" 
    FAL_DEFAULT_IMAGE_SIZE: str
    FAL_NUM_INFERENCE_STEPS: int
    FAL_GUIDANCE_SCALE: float
#############

class ConfigForm(BaseModel):
    enabled: bool
    engine: str
    prompt_generation: bool
    openai: OpenAIConfigForm
    automatic1111: Automatic1111ConfigForm
    comfyui: ComfyUIConfigForm
    gemini: GeminiConfigForm
    #####fal
    fal: FalConfigForm

@router.post("/config/update")
async def update_config(
    request: Request, form_data: ConfigForm, user=Depends(get_admin_user)
):
    request.app.state.config.IMAGE_GENERATION_ENGINE = form_data.engine
    request.app.state.config.ENABLE_IMAGE_GENERATION = form_data.enabled

    request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION = (
        form_data.prompt_generation
    )

    request.app.state.config.IMAGES_OPENAI_API_BASE_URL = (
        form_data.openai.OPENAI_API_BASE_URL
    )
    request.app.state.config.IMAGES_OPENAI_API_KEY = form_data.openai.OPENAI_API_KEY

    request.app.state.config.IMAGES_GEMINI_API_BASE_URL = (
        form_data.gemini.GEMINI_API_BASE_URL
    )
    request.app.state.config.IMAGES_GEMINI_API_KEY = form_data.gemini.GEMINI_API_KEY

    request.app.state.config.AUTOMATIC1111_BASE_URL = (
        form_data.automatic1111.AUTOMATIC1111_BASE_URL
    )
    request.app.state.config.AUTOMATIC1111_API_AUTH = (
        form_data.automatic1111.AUTOMATIC1111_API_AUTH
    )

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

    request.app.state.config.COMFYUI_BASE_URL = (
        form_data.comfyui.COMFYUI_BASE_URL.strip("/")
    )
    request.app.state.config.COMFYUI_API_KEY = form_data.comfyui.COMFYUI_API_KEY

    request.app.state.config.COMFYUI_WORKFLOW = form_data.comfyui.COMFYUI_WORKFLOW
    request.app.state.config.COMFYUI_WORKFLOW_NODES = (
        form_data.comfyui.COMFYUI_WORKFLOW_NODES
    )
    # 🆕 ========== Fal Flux ========== 🆕
    request.app.state.config.FAL_API_KEY = form_data.fal.FAL_API_KEY
    request.app.state.config.FAL_API_BASE_URL = (
        form_data.fal.FAL_API_BASE_URL.strip("/")  #  strip
    )
    request.app.state.config.FAL_MODEL = form_data.fal.FAL_MODEL
    request.app.state.config.ENABLE_FAL_SMART_MODE = form_data.fal.ENABLE_FAL_SMART_MODE
    request.app.state.config.FAL_OPENAI_API_KEY = form_data.fal.FAL_OPENAI_API_KEY
    request.app.state.config.FAL_DEFAULT_IMAGE_SIZE = form_data.fal.FAL_DEFAULT_IMAGE_SIZE
    request.app.state.config.FAL_NUM_INFERENCE_STEPS = form_data.fal.FAL_NUM_INFERENCE_STEPS
    request.app.state.config.FAL_GUIDANCE_SCALE = form_data.fal.FAL_GUIDANCE_SCALE

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
        # 🆕 ========== Fal Flux ========== 🆕
        "fal": {
            "FAL_API_KEY": request.app.state.config.FAL_API_KEY,
            "FAL_API_BASE_URL": request.app.state.config.FAL_API_BASE_URL,
            "FAL_MODEL": request.app.state.config.FAL_MODEL,
            "ENABLE_FAL_SMART_MODE": request.app.state.config.ENABLE_FAL_SMART_MODE,
            "FAL_OPENAI_API_KEY": request.app.state.config.FAL_OPENAI_API_KEY,
            "FAL_DEFAULT_IMAGE_SIZE": request.app.state.config.FAL_DEFAULT_IMAGE_SIZE,
            "FAL_NUM_INFERENCE_STEPS": request.app.state.config.FAL_NUM_INFERENCE_STEPS,
            "FAL_GUIDANCE_SCALE": request.app.state.config.FAL_GUIDANCE_SCALE,
        },
    }


def get_automatic1111_api_auth(request: Request):
    if request.app.state.config.AUTOMATIC1111_API_AUTH is None:
        return ""
    else:
        auth1111_byte_string = request.app.state.config.AUTOMATIC1111_API_AUTH.encode(
            "utf-8"
        )
        auth1111_base64_encoded_bytes = base64.b64encode(auth1111_byte_string)
        auth1111_base64_encoded_string = auth1111_base64_encoded_bytes.decode("utf-8")
        return f"Basic {auth1111_base64_encoded_string}"


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
            headers = {
                "Authorization": f"Bearer {request.app.state.config.COMFYUI_API_KEY}"
            }

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
            # TODO - get models from comfyui
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
                for key in info[workflow[model_node_id]["class_type"]]["input"][
                    "required"
                ]:
                    if "_name" in key:
                        model_list_key = key
                        break

                if model_list_key:
                    return list(
                        map(
                            lambda model: {"id": model, "name": model},
                            info[workflow[model_node_id]["class_type"]]["input"][
                                "required"
                            ][model_list_key][0],
                        )
                    )
            else:
                return list(
                    map(
                        lambda model: {"id": model, "name": model},
                        info["CheckpointLoaderSimple"]["input"]["required"][
                            "ckpt_name"
                        ][0],
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


class GenerateImageForm(BaseModel):
    model: Optional[str] = None
    prompt: str
    size: Optional[str] = None
    n: int = 1
    negative_prompt: Optional[str] = None


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
        filename=f"generated-image{image_format}",  # will be converted to a unique ID on upload_file
        headers={
            "content-type": content_type,
        },
    )
    file_item = upload_file(request, file, user, file_metadata=image_metadata)
    url = request.app.url_path_for("get_file_content_by_id", id=file_item.id)
    return url


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
            headers["Authorization"] = (
                f"Bearer {request.app.state.config.IMAGES_OPENAI_API_KEY}"
            )
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

            # Use asyncio.to_thread for the requests.post call
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

            # Use asyncio.to_thread for the requests.post call
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
                image_data, content_type = load_b64_image_data(
                    image["bytesBase64Encoded"]
                )
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
        #####fal--###############################################
        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "fal":
            log.info("[FalFlux] Basic text2img generation (non-chat context)")
            try:
                # Initialize client
                fal_client = FalFluxClient(
                    api_key=request.app.state.config.FAL_API_KEY,
                    model=request.app.state.config.FAL_MODEL
                )
                
                # Get size from form_data or config
                image_size = form_data.size if form_data.size else request.app.state.config.FAL_DEFAULT_IMAGE_SIZE
                
                # Parse size for Fal API format
                if "x" in image_size:
                    width, height = map(int, image_size.split("x"))
                    if width == height:
                        image_size = "square_hd"
                    elif width > height:
                        image_size = "landscape_4_3"
                    else:
                        image_size = "portrait_4_3"
                
                # Call Fal API with timeout
                result = await asyncio.wait_for(
                    fal_client.text2img(
                        prompt=form_data.prompt,
                        image_size=image_size,
                        num_inference_steps=request.app.state.config.FAL_NUM_INFERENCE_STEPS,
                        guidance_scale=request.app.state.config.FAL_GUIDANCE_SCALE,
                        seed=None
                    ),
                    timeout=60.0
                )
                
                # Download image from Fal
                image_data, content_type = load_url_image_data(result["image_url"])
                
                if not image_data:
                    log.error("[FalFlux] Failed to download image from Fal")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=ERROR_MESSAGES.DEFAULT("Failed to download generated image")
                    )
                
                # Check file size
                if len(image_data) > 15 * 1024 * 1024:  # 15MB
                    log.error(f"[FalFlux] Image too large: {len(image_data)} bytes")
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=ERROR_MESSAGES.DEFAULT("Generated image exceeds 15MB")
                    )
                
                # Upload to Open WebUI storage
                metadata = {
                    "prompt": form_data.prompt,
                    "engine": "fal",
                    "model": request.app.state.config.FAL_MODEL,
                    "fal_seed": result["seed"],
                    "width": result["width"],
                    "height": result["height"]
                }
                
                url = upload_image(request, metadata, image_data, content_type, user)
                
                images = [{"url": url}]
                
                log.info(
                    f"[FalFlux] Generated image: {result['width']}x{result['height']}, "
                    f"seed={result['seed']}"
                )
                
                return images
            
            except asyncio.TimeoutError:
                log.error("[FalFlux] Generation timed out after 60s")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=ERROR_MESSAGES.DEFAULT("Image generation timed out")
                )
            except HTTPException:
                raise
            except Exception as e:
                log.error(f"[FalFlux] Generation failed: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=ERROR_MESSAGES.DEFAULT(f"Image generation failed: {str(e)}")
                )
            ##############################################
        elif (
            request.app.state.config.IMAGE_GENERATION_ENGINE == "automatic1111"
            or request.app.state.config.IMAGE_GENERATION_ENGINE == ""
        ):
            if form_data.model:
                set_image_model(form_data.model)

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

            # Use asyncio.to_thread for the requests.post call
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
        if r != None:
            data = r.json()
            if "error" in data:
                error = data["error"]["message"]
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))



# ========================================
# Smart Multi-Round Image Generation (Fal Flux)
# ========================================

class SmartGenerateImageForm(BaseModel):
    chat_id: str
    prompt: str
    image_size: Optional[str] = "square_hd"
    num_inference_steps: Optional[int] = 28
    guidance_scale: Optional[float] = 3.5
    seed: Optional[int] = None


@router.post("/generations/smart")
async def smart_image_generation(
    request: Request,
    form_data: SmartGenerateImageForm,
    user=Depends(get_verified_user),
):
    """
    Smart multi-round image generation with Fal Flux
    - Auto-detects text2img vs img2img
    - Maintains parent-child session chain
    """
    start_time = time.time()
    
    try:
        # 1. Verify chat ownership
        chat = Chats.get_chat_by_id_and_user_id(form_data.chat_id, user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "message": "Chat not found or access denied"}
            )
        

       ############# 
        # 2. Check for parent session
        last_session = ImageSessions.get_last_session(form_data.chat_id, user.id)
        has_parent = last_session is not None  
        
        # 3. ✅ NEW: Intelligent analysis (mode + size)
        analyzer = get_prompt_analyzer()
        analysis = await analyzer.analyze(
            prompt=form_data.prompt,
            has_parent=has_parent,
            has_uploaded=False  # Phase 2.5 doesn't support uploads yet
        )
        
        suggested_mode = analysis["mode"]
        suggested_size = analysis["image_size"]
        mode_confidence = analysis.get("mode_confidence", 0.8)
        size_confidence = analysis.get("size_confidence", 0.7)
        reasoning = analysis.get("reasoning", "")
        
        log.info(
            f"[SmartGen] Analysis: mode={suggested_mode} (conf={mode_confidence:.2f}) "
            f"size={suggested_size} (conf={size_confidence:.2f}) reason='{reasoning}'"
        )
        
        # ✅ NEW: Size priority logic
        # Priority: User-specified > LLM-analyzed > Default
        if form_data.image_size and form_data.image_size != "square_hd":
            final_image_size = form_data.image_size
            size_source = "user_specified"
            log.info(f"[SmartGen] Using user-specified size: {final_image_size}")
        else:
            final_image_size = suggested_size
            size_source = "llm_analyzed"
            log.info(f"[SmartGen] Using analyzed size: {final_image_size} (conf={size_confidence:.2f})")
        
        # ✅ CHANGED: Verify parent session ownership
        if last_session and last_session.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "message": "Parent session not owned by user"}
            )
        
        # ✅ CHANGED: Use analyzer's mode
        mode = suggested_mode
        log.info(f"[SmartGen] Using mode: {mode} (from analyzer)")
        ###############
        
        # 4. Initialize Fal client
        fal_client = FalFluxClient(
            api_key=request.app.state.config.FAL_API_KEY,
            model=request.app.state.config.FAL_MODEL  # 🆕 NEW
        )
        
        # 5. Generate image with timeout ✅ NEW
        if mode == "text2img":
            log.info(f"[SmartGen] text2img for chat={form_data.chat_id}")
            result = await asyncio.wait_for(
                fal_client.text2img(
                    prompt=form_data.prompt,
                    image_size=final_image_size,
                    num_inference_steps=form_data.num_inference_steps,
                    guidance_scale=form_data.guidance_scale,
                    seed=form_data.seed
                ),
                timeout=60.0
            )
        else:
            # img2img: read parent image from disk
            log.info(f"[SmartGen] img2img for chat={form_data.chat_id}, parent={last_session.file_id}")
            
            # Get parent file from database
            parent_file = Files.get_file_by_id(last_session.file_id)
            
            if not parent_file or not parent_file.path:
                raise ValueError("Parent image file not found")
            
            # Read image bytes from disk
            with open(parent_file.path, 'rb') as f:
                parent_image_bytes = f.read()
            
            result = await asyncio.wait_for(
                fal_client.img2img(
                    prompt=form_data.prompt,
                    image_bytes=parent_image_bytes,
                    strength=0.35,
                    image_size=final_image_size,
                    num_inference_steps=form_data.num_inference_steps,
                    guidance_scale=form_data.guidance_scale,
                    seed=form_data.seed
                ),
                timeout=90.0  # img2img needs more time
            )
        
        # 6. Download generated image from Fal
        image_data, content_type = load_url_image_data(result["image_url"])
        
        if not image_data:
            raise ValueError("Failed to download generated image from Fal")
        
        # 7. ✅ NEW: Check file size
        if len(image_data) > 15 * 1024 * 1024:  # 15MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": "image_too_large", "message": "Generated image exceeds 15MB"}
            )
        
        # 8. Upload to our storage
        metadata = {
            "prompt": form_data.prompt,
            "mode": mode,
            "engine": "fal",
            "model": "fal-ai/flux-pro/v1.1",
            "fal_seed": result["seed"],
            "parent_session_id": last_session.id if last_session else None
        }
        
        file_url = upload_image(request, metadata, image_data, content_type, user)
        
        # 9. ✅ NEW: Extract file_id safely (robust parsing)
        segments = file_url.rstrip("/").split("/")
        if "files" in segments and len(segments) >= segments.index("files") + 2:
            file_id = segments[segments.index("files") + 1]
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "internal_error", "message": f"Unexpected file URL format: {file_url}"}
            )
        
        # 10. Save session to database
        session = ImageSessions.create_session(ImageSessionForm(
            chat_id=form_data.chat_id,
            user_id=user.id,
            file_id=file_id,
            parent_session_id=last_session.id if last_session else None,
            prompt=form_data.prompt,
            optimized_prompt=form_data.prompt,
            mode=mode,
            fal_seed=result["seed"],
            meta_json={
                "engine": "fal",
                "model": "fal-ai/flux-pro/v1.1",
                # ✅ Size detection metadata
                "suggested_size": suggested_size,
                "size_confidence": size_confidence,
                "final_size": final_image_size,
                "size_source": size_source,
                # ✅ Mode detection metadata
                "suggested_mode": suggested_mode,
                "mode_confidence": mode_confidence,
                "mode_reasoning": reasoning,
                "actual_mode": mode,
                "image_size": form_data.image_size,
                "steps": form_data.num_inference_steps,
                "guidance_scale": form_data.guidance_scale,
                "width": result["width"],
                "height": result["height"]
            }
        ))
        
        # 11. ✅ NEW: Enhanced logging with latency
        latency_ms = (time.time() - start_time) * 1000
        log.info(
            f"[SmartGen] Success: session={session.id} mode={mode} "
            f"chat={form_data.chat_id} user={user.id} latency_ms={latency_ms:.0f}"
        )
        
        # 12. ✅ NEW: Enhanced response with width/height/engine/model
        return {
            "url": file_url,
            "file_id": file_id,
            "session_id": session.id,
            "mode": mode,
            "seed": result["seed"],
            "parent_session_id": last_session.id if last_session else None,
            "width": result["width"],
            "height": result["height"],
            "engine": "fal",
            "model": "fal-ai/flux-pro/v1.1",
            "meta_json": session.meta_json
        }
        
    except asyncio.TimeoutError:
        latency = time.time() - start_time
        log.error(f"[SmartGen] Timeout after {latency:.1f}s")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "timeout", "message": "Image generation timed out"}
        )
    except HTTPException:
        raise
    except ValueError as e:
        log.error(f"[SmartGen] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "message": str(e)}
        )
    except Exception as e:
        log.error(f"[SmartGen] Generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "generation_failed", "message": "Image generation failed"}
        )