import cloudinary
import cloudinary.uploader
from config import settings

cloudinary.config(
    cloud_name = settings.CLOUDINARY_CLOUD_NAME,
    api_key    = settings.CLOUDINARY_API_KEY,
    api_secret = settings.CLOUDINARY_API_SECRET,
)

def upload_image(file_path: str, folder: str, filename: str) -> str:
    """Upload image to Cloudinary and return public URL."""
    result = cloudinary.uploader.upload(
        file_path,
        folder   = f"autobill/{folder}",
        public_id= filename,
        overwrite= True,
    )
    return result["secure_url"]