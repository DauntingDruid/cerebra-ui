"""
Project Version Manager - Fixed Version
Handles version control, feedback collection, and metadata storage for image generation projects.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4
from io import BytesIO

from open_webui.storage.provider import Storage
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS.get("IMAGES", logging.INFO))


class ProjectManager:
    
    
    def __init__(self):
        
        self.storage = Storage()
        self.projects_metadata_prefix = "image_projects/metadata/"
        self.projects_images_prefix = "image_projects/images/"
        self.projects_index_prefix = "image_projects/index/"
    
    
    
    def _put_json(self, key: str, obj: dict, tags: Optional[dict] = None) -> str:
        
        try:
            data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
            
            
            if hasattr(self.storage, "upload_bytes"):
                return self.storage.upload_bytes(
                    key, 
                    data, 
                    content_type="application/json",
                    tags=tags or {}
                )
            
            
            else:
                file_obj = BytesIO(data)
                file_obj.name = key.split("/")[-1]  
                return self.storage.upload_file(
                    file=file_obj,
                    filename=key,
                    tags=tags or {}
                )
        except Exception as e:
            log.error(f"Failed to write JSON to {key}: {e}")
            raise
    
    def _get_json(self, key: str) -> Optional[dict]:
        
        try:
            
            if hasattr(self.storage, "download_bytes"):
                data = self.storage.download_bytes(key)
                return json.loads(data.decode("utf-8"))
            
            
            else:
                path = self.storage.get_file(key)
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except FileNotFoundError:
            log.debug(f"JSON file not found: {key}")
            return None
        except Exception as e:
            log.error(f"Failed to read JSON from {key}: {e}")
            return None
    
    
    
    def _index_key(self, user_id: str) -> str:
        
        return f"{self.projects_index_prefix}{user_id}.json"
    
    def _upsert_index(
        self, 
        user_id: str, 
        project_id: str, 
        initial_request: str,
        created_at: str
    ):
       
        index_key = self._index_key(user_id)
        index = self._get_json(index_key) or {
            "user_id": user_id,
            "projects": [],
            "updated_at": datetime.utcnow().isoformat()
        }
        
       
        if not any(p["project_id"] == project_id for p in index["projects"]):
            index["projects"].append({
                "project_id": project_id,
                "created_at": created_at,
                "initial_request": initial_request[:100]  
            })
            index["updated_at"] = datetime.utcnow().isoformat()
            
            
            self._put_json(
                index_key, 
                index,
                tags={"type": "project_index", "user_id": user_id}
            )
            log.info(f"Added project {project_id} to user {user_id} index")
    
    
    
    def create_project(
        self,
        user_id: str,
        initial_request: str,
        image_urls: List[str],
        optimized_prompt: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        创建新项目并记录第一个版本
        """
        project_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        
        project_metadata = {
            "project_id": project_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "initial_request": initial_request,
            "versions": [
                {
                    "version": 1,
                    "timestamp": now,
                    "request": initial_request,
                    "optimized_prompt": optimized_prompt,
                    "image_urls": image_urls,
                    "feedback": None,
                    "metadata": metadata or {}
                }
            ],
            "feedback_summary": {
                "positive_count": 0,
                "negative_count": 0,
                "common_issues": []
            }
        }
        
        
        metadata_key = f"{self.projects_metadata_prefix}{project_id}.json"
        self._put_json(
            metadata_key,
            project_metadata,
            tags={"type": "project_metadata", "user_id": user_id}
        )
        
        
        self._upsert_index(user_id, project_id, initial_request, now)
        
        log.info(f"Created project {project_id} for user {user_id}")
        return project_metadata
    
    def add_version(
        self,
        project_id: str,
        user_id: str,
        request: str,
        image_urls: List[str],
        optimized_prompt: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
       
        metadata_key = f"{self.projects_metadata_prefix}{project_id}.json"
        project = self._get_json(metadata_key)
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        if project.get("user_id") != user_id:
            raise PermissionError(f"User {user_id} does not own project {project_id}")
        
        
        new_version = {
            "version": len(project["versions"]) + 1,
            "timestamp": datetime.utcnow().isoformat(),
            "request": request,
            "optimized_prompt": optimized_prompt,
            "image_urls": image_urls,
            "feedback": None,
            "metadata": metadata or {}
        }
        
        project["versions"].append(new_version)
        project["updated_at"] = datetime.utcnow().isoformat()
        
        
        self._put_json(
            metadata_key,
            project,
            tags={"type": "project_metadata", "user_id": user_id}
        )
        
        log.info(f"Added version {new_version['version']} to project {project_id}")
        return project
    
    def add_feedback(
        self,
        project_id: str,
        user_id: str,
        version: int,
        feedback: Dict
    ) -> Dict:
        """
        为特定版本添加反馈
        """
        metadata_key = f"{self.projects_metadata_prefix}{project_id}.json"
        project = self._get_json(metadata_key)
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        if project.get("user_id") != user_id:
            raise PermissionError(f"User {user_id} does not own project {project_id}")
        
       
        target_version = next(
            (v for v in project["versions"] if v["version"] == version),
            None
        )
        
        if not target_version:
            raise ValueError(f"Version {version} not found in project {project_id}")
        
       
        target_version["feedback"] = {
            **feedback,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        
        if feedback.get("rating") == "positive":
            project["feedback_summary"]["positive_count"] += 1
        elif feedback.get("rating") == "negative":
            project["feedback_summary"]["negative_count"] += 1
            
           
            if "issues" in feedback:
                for issue in feedback["issues"]:
                    if issue not in project["feedback_summary"]["common_issues"]:
                        project["feedback_summary"]["common_issues"].append(issue)
        
        project["updated_at"] = datetime.utcnow().isoformat()
        
      
        self._put_json(
            metadata_key,
            project,
            tags={"type": "project_metadata", "user_id": user_id}
        )
        
        log.info(f"Added feedback to project {project_id} version {version}")
        return project
    
    def get_project_metadata(self, project_id: str, user_id: str) -> Optional[Dict]:
       
        metadata_key = f"{self.projects_metadata_prefix}{project_id}.json"
        project = self._get_json(metadata_key)
        
        if not project:
            return None
        
        if project.get("user_id") != user_id:
            raise PermissionError(f"User {user_id} does not own project {project_id}")
        
        return project
    
    def list_user_projects(self, user_id: str) -> List[Dict]:
        
        index = self._get_json(self._index_key(user_id))
        
        if not index:
            return []
        
        # 返回项目摘要列表（按创建时间倒序）
        projects = sorted(
            index.get("projects", []),
            key=lambda p: p.get("created_at", ""),
            reverse=True
        )
        
        return projects



_project_manager_instance = None

def get_project_manager() -> ProjectManager:
    
    global _project_manager_instance
    if _project_manager_instance is None:
        _project_manager_instance = ProjectManager()
    return _project_manager_instance