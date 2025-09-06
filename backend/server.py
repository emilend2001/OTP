from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import pyotp
import qrcode
import io
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import bcrypt
import subprocess
import asyncio
from collections import defaultdict
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="OTP Linux Password Change System")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Rate limiting storage
rate_limit_storage = defaultdict(list)
MAX_ATTEMPTS_PER_HOUR = 5

# Define Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    email: EmailStr
    totp_secret: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_otp_used: Optional[str] = None
    last_otp_time: Optional[datetime] = None

class UserCreate(BaseModel):
    username: str
    email: EmailStr

class PasswordChangeRequest(BaseModel):
    username: str
    otp_code: str
    new_password: str

class QRCodeResponse(BaseModel):
    qr_code_base64: str
    secret: str

# Rate limiting helper
def check_rate_limit(identifier: str) -> bool:
    """Check if request is within rate limit"""
    current_time = time.time()
    user_attempts = rate_limit_storage[identifier]
    
    # Remove attempts older than 1 hour
    user_attempts[:] = [attempt_time for attempt_time in user_attempts 
                       if current_time - attempt_time < 3600]
    
    if len(user_attempts) >= MAX_ATTEMPTS_PER_HOUR:
        return False
    
    user_attempts.append(current_time)
    return True

# TOTP Helper Functions
def generate_totp_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()

def generate_qr_code(username: str, secret: str) -> str:
    """Generate QR code for TOTP secret"""
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=f"{username}@linux-system",
        issuer_name="Linux OTP System"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
    
    return img_base64

def verify_totp(secret: str, token: str) -> bool:
    """Verify TOTP token"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)

# Email Helper Functions
async def send_email_async(to_email: str, subject: str, body: str, qr_code_base64: str = None):
    """Send email with QR code attachment"""
    try:
        gmail_user = os.environ.get('GMAIL_USER')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_user or not gmail_password:
            logging.warning("Gmail credentials not configured. Email not sent.")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body
        msg.attach(MIMEText(body, 'html'))
        
        # Add QR code as inline image if provided
        if qr_code_base64:
            from email.mime.image import MIMEImage
            qr_image = base64.b64decode(qr_code_base64)
            img = MIMEImage(qr_image)
            img.add_header('Content-ID', '<qr_code>')
            img.add_header('Content-Disposition', 'inline', filename='qr_code.png')
            msg.attach(img)
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        text = msg.as_string()
        server.sendmail(gmail_user, to_email, text)
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        return False

# Linux System Helper Functions
async def check_linux_user_exists(username: str) -> bool:
    """Check if Linux user exists (test mode)"""
    try:
        # In test mode, we'll simulate this
        # In production: subprocess.run(['id', username], capture_output=True)
        logging.info(f"Checking if user {username} exists (TEST MODE)")
        # Simulate some common test users
        test_users = ['testuser', 'demo', 'test', username]
        return username in test_users or len(username) > 3
    except Exception as e:
        logging.error(f"Error checking user existence: {str(e)}")
        return False

async def change_linux_password(username: str, new_password: str) -> bool:
    """Change Linux user password (test mode)"""
    try:
        logging.info(f"Changing password for user {username} (TEST MODE)")
        # In test mode, we'll just log the action
        # In production: subprocess with passwd command would be used
        
        # Simulate password change
        await asyncio.sleep(0.5)  # Simulate processing time
        
        logging.info(f"Password changed successfully for user {username} (simulated)")
        return True
    except Exception as e:
        logging.error(f"Error changing password: {str(e)}")
        return False

# API Routes
@api_router.post("/register", response_model=dict)
async def register_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    """Register a new user and send QR code via email"""
    
    # Rate limiting
    if not check_rate_limit(f"register_{user_data.email}"):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")
    
    # Check if user already exists
    existing_user = await db.users.find_one({"username": user_data.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    existing_email = await db.users.find_one({"email": user_data.email})
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if Linux user exists
    if not await check_linux_user_exists(user_data.username):
        raise HTTPException(status_code=400, detail="Linux user does not exist on the system")
    
    # Generate TOTP secret
    totp_secret = generate_totp_secret()
    
    # Generate QR code
    qr_code_base64 = generate_qr_code(user_data.username, totp_secret)
    
    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        totp_secret=totp_secret
    )
    
    # Save to database
    await db.users.insert_one(user.dict())
    
    # Send email with QR code
    email_subject = "Linux OTP Sistemi - QR Kodu"
    email_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 28px;">🔐 Linux OTP Sistemi</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Təhlükəsiz şifrə dəyişdirmə sistemi</p>
            </div>
            
            <div style="background: white; padding: 30px; border: 1px solid #e1e5e9; border-radius: 0 0 10px 10px;">
                <h2 style="color: #2c3e50; margin-top: 0;">Salamlar <strong>{user_data.username}</strong>!</h2>
                <p style="font-size: 16px;">Linux istifadəçi şifrə dəyişdirmə sistemi üçün qeydiyyatınız tamamlandı.</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #495057; margin-top: 0;">📱 Quraşdırma Addımları:</h3>
                    <ol style="font-size: 15px; line-height: 1.8;">
                        <li><strong>Google Authenticator</strong> tətbiqini telefonunuza endirin</li>
                        <li>Tətbiqdə <strong>"QR kod skan etmə"</strong> seçimini seçin</li>
                        <li>Aşağıdakı QR kodu skan edin</li>
                    </ol>
                </div>
                
                <div style="text-align: center; margin: 30px 0; padding: 20px; background: #fff; border: 2px dashed #6c757d; border-radius: 10px;">
                    <img src="cid:qr_code" alt="QR Code" style="max-width: 280px; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
                    <p style="margin-top: 15px; font-size: 14px; color: #6c757d;">QR Kod - Google Authenticator ilə skan edin</p>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>⚠️ Diqqət:</strong> Bu QR kod yalnız sizə xasdır. Başqaları ilə paylaşmayın!</p>
                </div>
                
                <div style="background: #d1ecf1; border: 1px solid #b6d7ff; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #0c5460;"><strong>🔑 Şifrə dəyişdirmək üçün:</strong><br>
                    Sistem üzərindən istifadəçi adınız və Google Authenticator-dan aldığınız 6 rəqəmli kodu istifadə edin.</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e9ecef;">
                    <p style="color: #6c757d; font-size: 14px; margin: 0;">
                        Suallarınız varsa bizimlə əlaqə saxlayın.<br>
                        <strong>Uğurlar!</strong> 🎉
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Add email sending to background tasks
    background_tasks.add_task(send_email_async, user_data.email, email_subject, email_body, qr_code_base64)
    
    return {
        "status": "success",
        "message": "User registered successfully. QR code sent to email.",
        "username": user_data.username
    }

@api_router.post("/change-password", response_model=dict)
async def change_password(request: PasswordChangeRequest):
    """Change Linux user password using OTP verification"""
    
    # Rate limiting
    if not check_rate_limit(f"change_pass_{request.username}"):
        raise HTTPException(status_code=429, detail="Too many password change attempts. Please try again later.")
    
    # Find user
    user = await db.users.find_one({"username": request.username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.get('is_active'):
        raise HTTPException(status_code=400, detail="User account is disabled")
    
    # Verify OTP
    if not verify_totp(user['totp_secret'], request.otp_code):
        raise HTTPException(status_code=400, detail="Invalid OTP code")
    
    # Check OTP replay protection
    current_time = datetime.now(timezone.utc)
    last_otp = user.get('last_otp_used')
    last_time = user.get('last_otp_time')
    
    if last_otp == request.otp_code and last_time:
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 30:  # 30 second window to prevent replay
            raise HTTPException(status_code=400, detail="OTP code already used recently")
    
    # Validate new password
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    
    # Change Linux password
    success = await change_linux_password(request.username, request.new_password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to change system password")
    
    # Update user's last OTP info
    await db.users.update_one(
        {"username": request.username},
        {
            "$set": {
                "last_otp_used": request.otp_code,
                "last_otp_time": current_time
            }
        }
    )
    
    return {
        "status": "success",
        "message": "Password changed successfully",
        "timestamp": current_time.isoformat()
    }

@api_router.get("/user/{username}/qr-code", response_model=QRCodeResponse)
async def get_qr_code(username: str):
    """Get QR code for existing user (for re-setup)"""
    
    # Rate limiting
    if not check_rate_limit(f"qr_code_{username}"):
        raise HTTPException(status_code=429, detail="Too many QR code requests. Please try again later.")
    
    # Find user
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate QR code
    qr_code_base64 = generate_qr_code(username, user['totp_secret'])
    
    return QRCodeResponse(
        qr_code_base64=qr_code_base64,
        secret=user['totp_secret']
    )

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "otp-linux-password-system",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@api_router.get("/users", response_model=List[dict])
async def get_users():
    """Get all users (admin endpoint)"""
    users = await db.users.find().to_list(1000)
    # Remove sensitive information
    for user in users:
        user.pop('totp_secret', None)
        user.pop('last_otp_used', None)
    return users

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Create indexes on startup"""
    try:
        # Create unique indexes
        await db.users.create_index("username", unique=True)
        await db.users.create_index("email", unique=True)
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {str(e)}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()