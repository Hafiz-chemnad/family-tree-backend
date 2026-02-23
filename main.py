from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import uuid
from pydantic import BaseModel
from typing import Optional

# 1. Load Secrets
load_dotenv()

app = FastAPI()

# 2. Enable Frontend Connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows your website to talk to this server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Configure Cloudinary (Image Storage)
cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
    api_key = os.getenv("CLOUDINARY_API_KEY"), 
    api_secret = os.getenv("CLOUDINARY_API_SECRET") 
)

# 4. Connect to MongoDB (Database)
try:
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client['FamilyTreeDB']
    users_collection = db['users']
    print("✅ Connected to MongoDB!")
except Exception as e:
    print(f"❌ Database connection failed: {e}")

# ================= ROUTES ================= #

@app.get("/")
def home():
    return {"message": "Family Tree Backend is Running!"}

# ==========================================
# 1. REGISTER ROUTE
# ==========================================
@app.post("/register")
async def register_user(
    fullName: str = Form(...),
    gender: str = Form(...),            # <-- NEW
    memberType: str = Form(...),        # <-- NEW
    phone: str = Form(...),
    password: str = Form(...),
    mainFamily: str = Form(...),
    subFamily: str = Form(...),
    parent: str = Form(...),
    pincode: str = Form(...),
    address: str = Form(...),         # FIXED: Added Form(...) to prevent crashes
    jobType: str = Form(...),         
    jobDetails: str = Form(...),      
    talent: str = Form(...),          
    photo: Optional[UploadFile] = File(None)
):
    # Prevent Duplicate Phone Numbers
    if users_collection.find_one({"phone": phone}):
        raise HTTPException(status_code=400, detail="Phone already registered")

    photo_url = "https://via.placeholder.com/150" # Default placeholder avatar
    
    # Process the Optional Photo Upload
    if photo is not None and photo.filename != "":
        try:
            file_content = await photo.read()
            upload_result = cloudinary.uploader.upload(file_content, folder="family_tree_photos")
            photo_url = upload_result.get("secure_url")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Image upload failed")

    # Create the user profile payload
    new_user = {
        "name": fullName,
        "gender": gender,               # <-- NEW
        "memberType": memberType,
        "phone": phone,
        "password": password,
        "mainFamily": mainFamily,
        "subFamily": subFamily,
        "parent": parent,
        "pincode": pincode,
        "address": address,           # FIXED: Added pincode to Database
        "jobType": jobType,
        "jobDetails": jobDetails,
        "talent": talent,
        "photo": photo_url,
        "status": "Pending",
        "isAdmin": False
    }
    
    users_collection.insert_one(new_user)
    return {"message": "Registration Request Sent!"}

# ==========================================
# 2. ADMIN: PENDING / APPROVE / REJECT
# ==========================================
@app.get("/admin/pending")
def get_pending():
    users = []
    for user in users_collection.find({"status": "Pending"}):
        user["id"] = str(user["_id"]) # Convert DB ID to string for JS
        del user["_id"]               
        users.append(user)
    return users

@app.put("/admin/approve/{user_id}")
def approve_user(user_id: str):
    try:
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)}, 
            {"$set": {"status": "Approved"}}
        )
        if result.modified_count == 1:
            return {"message": "User Approved"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

@app.delete("/admin/reject/{user_id}")
def reject_user(user_id: str):
    try:
        result = users_collection.delete_one({"_id": ObjectId(user_id)})
        if result.deleted_count == 1:
            return {"message": "User Rejected"}
        raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

# ==========================================
# 3. ADMIN AUTHENTICATION LOGIC
# ==========================================
class LoginModel(BaseModel):
    username: str
    password: str

class PasswordChangeModel(BaseModel):
    new_password: str

@app.post("/login")
def login(data: LoginModel):
    # Fetch custom password from DB if it was changed
    admin_settings = db.settings.find_one({"type": "admin_credentials"})
    
    # Default Credentials
    admin_username = "KTMTFAMILY WEBSITE"
    admin_password = "KTMTPASSWORD"
    
    # If a new password was saved, use it
    if admin_settings:
        admin_password = admin_settings.get("password", "KTMTPASSWORD")

    if data.username == admin_username and data.password == admin_password:
        return {"message": "Login successful", "isAdmin": True, "name": "Admin"}
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")

@app.put("/admin/change-password")
def change_password(data: PasswordChangeModel):
    # Save the new password to the database
    db.settings.update_one(
        {"type": "admin_credentials"},
        {"$set": {"password": data.new_password, "type": "admin_credentials"}},
        upsert=True
    )
    return {"message": "Password updated successfully"}

# ==========================================
# 4. GET TREE ROUTE (Dynamic Members Load)
# ==========================================
@app.get("/tree")
def get_tree():
    users = []
    for user in users_collection.find({"status": "Approved"}):
        users.append({
            "_id": str(user["_id"]),          # Safely passes ID for Admin actions
            "name": user["name"],
            "gender": user.get("gender", "N/A"),               # <-- NEW
            "memberType": user.get("memberType", "Blood_Relative"),
            "photo": user["photo"],
            "phone": user.get("phone", ""),   # Passes phone for approval fixing
            "mainFamily": user["mainFamily"],
            "subFamily": user.get("subFamily", ""),
            "parent": user["parent"],
            "jobType": user.get("jobType", "N/A"),
            "jobDetails": user.get("jobDetails", "N/A"),
            "talent": user.get("talent", "N/A")
        })
    return users

# ==========================================
# 5. EVENTS API LOGIC (Dynamic Highlights)
# ==========================================
class EventModel(BaseModel):
    title: str
    description: str
    date: str
    location: str
    image_url: str
    registration_link: Optional[str] = ""

@app.get("/events")
def get_events():
    events = list(db.events.find({}, {"_id": 0}))
    return events

@app.post("/admin/events")
def create_event(event: EventModel):
    event_dict = event.model_dump() 
    event_dict["id"] = str(uuid.uuid4()) # Generate unique ID
    db.events.insert_one(event_dict)
    return {"message": "Event created successfully"}

@app.put("/admin/events/{event_id}")
def update_event(event_id: str, event: EventModel):
    db.events.update_one({"id": event_id}, {"$set": event.model_dump()})
    return {"message": "Event updated successfully"}

@app.delete("/admin/events/{event_id}")
def delete_event(event_id: str):
    db.events.delete_one({"id": event_id})
    return {"message": "Event deleted successfully"}