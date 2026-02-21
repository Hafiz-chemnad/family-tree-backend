from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import uuid
from pydantic import BaseModel

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
# 1. UPDATE REGISTER ROUTE (Accept New Fields)
# ==========================================
@app.post("/register")
async def register_user(
    fullName: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    mainFamily: str = Form(...),
    subFamily: str = Form(...),
    parent: str = Form(...),
    # --- NEW FIELDS ---
    jobType: str = Form(...),     # e.g., "Student" or "Job"
    jobDetails: str = Form(...),  # e.g., "Class 10" or "Engineer"
    talent: str = Form(...),      # e.g., "Drawing"
    photo: UploadFile = File(...)
):
    if users_collection.find_one({"phone": phone}):
        raise HTTPException(status_code=400, detail="Phone already registered")

    try:
        file_content = await photo.read()
        upload_result = cloudinary.uploader.upload(file_content, folder="family_tree_photos")
        photo_url = upload_result.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Image upload failed")

    new_user = {
        "name": fullName,
        "phone": phone,
        "password": password,
        "mainFamily": mainFamily,
        "subFamily": subFamily,
        "parent": parent,
        # --- SAVE NEW FIELDS ---
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
# 2. UPDATE TREE ROUTE (Send Data to Frontend)
# ==========================================


# --- ADMIN: GET PENDING REQUESTS ---
@app.get("/admin/pending")
def get_pending():
    users = []
    # Find everyone with status 'Pending'
    for user in users_collection.find({"status": "Pending"}):
        user["id"] = str(user["_id"]) # Convert DB ID to string
        del user["_id"]               # Remove the complex DB ID object
        users.append(user)
    return users

# --- ADMIN: APPROVE USER ---
@app.put("/admin/approve/{user_id}")
def approve_user(user_id: str):
    from bson.objectid import ObjectId
    try:
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)}, 
            {"$set": {"status": "Approved"}}
        )
        if result.modified_count == 1:
            return {"message": "User Approved"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

# --- ADMIN: REJECT USER ---
@app.delete("/admin/reject/{user_id}")
def reject_user(user_id: str):
    from bson.objectid import ObjectId
    result = users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 1:
        return {"message": "User Rejected"}
    raise HTTPException(status_code=404, detail="User not found")
# ==========================================
# ADD THIS TO backend/main.py
# ==========================================

from pydantic import BaseModel

# 1. Define what data we expect from the Login Page
class LoginRequest(BaseModel):
    phone: str
    password: str

# 2. The Login Route
@app.post("/login")
def login_user(request: LoginRequest):
    # A. Find user by phone
    user = users_collection.find_one({"phone": request.phone})
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found. Please register first.")
    
    # B. Check Password (In real life, we would hash this!)
    if user["password"] != request.password:
        raise HTTPException(status_code=400, detail="Wrong password.")
        
    # C. Check Approval Status
    if user["status"] != "Approved":
        raise HTTPException(status_code=403, detail="Your account is not approved yet. Ask Admin.")
        
    # D. Success! Return the user's name and photo
    return {
        "message": "Login Successful", 
        "name": user["name"],
        "photo": user["photo"],
        "isAdmin": user.get("isAdmin", False) # Send admin status if it exists
    }    
# ==========================================
# ADD THIS TO backend/main.py (At the bottom)
# ==========================================

@app.get("/tree")
def get_tree():
    users = []
    for user in users_collection.find({"status": "Approved"}):
        users.append({
            "name": user["name"],
            "photo": user["photo"],
            "mainFamily": user["mainFamily"],
            "subFamily": user.get("subFamily", ""),
            "parent": user["parent"],
            # --- SEND NEW FIELDS ---
            "jobType": user.get("jobType", "N/A"),
            "jobDetails": user.get("jobDetails", "N/A"),
            "talent": user.get("talent", "N/A")
        })
    return users
    # ==========================================
# EVENTS API LOGIC (Dynamic Highlights)
# ==========================================

class EventModel(BaseModel):
    title: str
    description: str
    date: str
    location: str
    image_url: str

@app.get("/events")
def get_events():
    # Fetch all events from database
    events = list(db.events.find({}, {"_id": 0}))
    return events

@app.post("/admin/events")
def create_event(event: EventModel):
    event_dict = event.dict()
    event_dict["id"] = str(uuid.uuid4()) # Generate unique ID
    db.events.insert_one(event_dict)
    return {"message": "Event created successfully"}

@app.put("/admin/events/{event_id}")
def update_event(event_id: str, event: EventModel):
    db.events.update_one({"id": event_id}, {"$set": event.dict()})
    return {"message": "Event updated successfully"}

@app.delete("/admin/events/{event_id}")
def delete_event(event_id: str):
    db.events.delete_one({"id": event_id})
    return {"message": "Event deleted successfully"}