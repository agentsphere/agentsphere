from pathlib import Path
import shutil
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import logger, settings

router = APIRouter()
BASE_REPO_PATH = Path(f"{settings.BASE_REPO_PATH}")

@router.get("/repos/{uuid}/{reponame}")
async def download_repository(uuid: str, reponame: str):
    repo_path = BASE_REPO_PATH / uuid / reponame

    # Validate repository path
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(status_code=404, detail="Repository not found.")

    # Define the path for the ZIP file in the same directory as the repository
    zip_path = repo_path.parent / f"{reponame}.zip"

    try:
        # Create the ZIP file
        shutil.make_archive(
            base_name=str(zip_path)[:-4],  # Remove the ".zip" extension for base_name
            format="zip",
            root_dir=repo_path
        )

        # Return the ZIP file as a response
        return FileResponse(
            path=zip_path,
            filename=f"{reponame}.zip",
            media_type="application/zip"
        )
    except Exception as e:
        logger.error("Error creating ZIP file: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create ZIP file.") from e
