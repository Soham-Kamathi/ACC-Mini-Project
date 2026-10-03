import os
import shutil
import tempfile
import docker
from backend.app.core.config import settings

class BuilderService:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            self.docker_available = True
        except Exception as e:
            print(f"[BuilderService Warning] Docker daemon not available: {e}")
            self.docker_available = False
            self.client = None

    def build_function_image(self, username: str, function_name: str, version_tag: str, code: str, requirements: str = "", runtime: str = "python311") -> str:
        """
        Builds a Docker container image for the serverless function and tags it.
        """
        image_name = f"{settings.DOCKER_REGISTRY}/{username}/{function_name}:{version_tag}".lower()
        
        # Create a temporary directory for the build context
        with tempfile.TemporaryDirectory() as build_dir:
            # 1. Write user handler code
            handler_path = os.path.join(build_dir, "handler.py")
            with open(handler_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 2. Write requirements.txt
            req_path = os.path.join(build_dir, "requirements.txt")
            with open(req_path, "w", encoding="utf-8") as f:
                f.write(requirements or "")

            # 3. Copy runtime template files
            base_runtime_dir = os.path.join(os.path.dirname(__file__), "..", "..", "runtimes", runtime)
            server_path = os.path.join(base_runtime_dir, "server.py")
            dockerfile_template_path = os.path.join(base_runtime_dir, "Dockerfile.template")

            if os.path.exists(server_path):
                shutil.copy(server_path, os.path.join(build_dir, "server.py"))
            else:
                raise FileNotFoundError(f"Runtime server wrapper not found at {server_path}")

            if os.path.exists(dockerfile_template_path):
                shutil.copy(dockerfile_template_path, os.path.join(build_dir, "Dockerfile"))
            else:
                raise FileNotFoundError(f"Dockerfile template not found at {dockerfile_template_path}")

            if not self.docker_available:
                print(f"[BuilderService Mock] Docker daemon not connected. Mocking image build for {image_name}")
                return image_name

            # 4. Execute Docker build
            print(f"[BuilderService] Building image {image_name}...")
            image, build_logs = self.client.images.build(
                path=build_dir,
                tag=image_name,
                rm=True,
                forcerm=True
            )
            
            # 5. Optionally push to registry if using remote registry
            if settings.DOCKER_REGISTRY and not settings.DOCKER_REGISTRY.startswith("localhost"):
                try:
                    self.client.images.push(image_name)
                    print(f"[BuilderService] Successfully pushed {image_name}")
                except Exception as e:
                    print(f"[BuilderService Warning] Failed to push to registry: {e}")

            print(f"[BuilderService] Build completed: {image_name}")
            return image_name

builder_service = BuilderService()
