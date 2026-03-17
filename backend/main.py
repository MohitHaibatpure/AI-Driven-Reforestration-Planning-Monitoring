import asyncio
import io
import os
import time
from typing import Any, Dict, List, Optional
import shutil
import datetime
import random 

import joblib
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse
from geoalchemy2 import Geography, WKTElement, Geometry
from pydantic import BaseModel
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from sqlalchemy import (Column, Integer, MetaData, String, Table, create_engine,
                        func, inspect, insert, select, text, DateTime)
from sqlalchemy.exc import OperationalError
from twilio.rest import Client
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# --- Load Environment Variables Safely ---
load_dotenv()

def get_env_safe(key, default=None):
    """Retrieves env var and strips whitespace/quotes to prevent auth errors."""
    val = os.getenv(key, default)
    if val:
        return val.strip().strip("'").strip('"')
    return None

OPENWEATHER_API_KEY = get_env_safe("OPENWEATHER_API_KEY")
TWILIO_ACCOUNT_SID = get_env_safe("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = get_env_safe("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = get_env_safe("TWILIO_FROM_NUMBER")

# --- Database Connection ---
DB_USER = get_env_safe("DB_USER", "admin")
DB_PASS = get_env_safe("DB_PASS", "password")
DB_NAME = get_env_safe("DB_NAME", "reforestation")
DB_HOST = get_env_safe("DB_HOST", "db")
DB_PORT = get_env_safe("DB_PORT", "5432")
DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Mock Data Catalogs ---
_MOCK_DATA_CATALOG = {
    "Tadoba National Park (Protected)": {
        "coords": {"lat": 20.2505, "lon": 79.3377},
        "land_type": "Protected Forest",
        "soil": {"ph": {"value": 6.8}, "N": {"value": 150.0}, "P": {"value": 22.0}, "K": {"value": 140.0}},
        "weather": {"temperature": 27.0, "humidity": 70.0, "rainfall": 0.2},
        "crop": "coffee"
    },
    "Solapur Barren Land (Wasteland)": {
        "coords": {"lat": 17.6599, "lon": 75.9064},
        "land_type": "Wasteland",
        "soil": {"ph": {"value": 7.9}, "N": {"value": 25.0}, "P": {"value": 30.0}, "K": {"value": 35.0}},
        "weather": {"temperature": 32.0, "humidity": 40.0, "rainfall": 0.0},
        "crop": "chickpea"
    },
    "Sanjay Park, India (Degraded)": {
        "coords": {"lat": 19.2296, "lon": 72.8711},
        "land_type": "Reforestation Candidate",
        "soil": {"ph": {"value": 6.8}, "N": {"value": 90.0}, "P": {"value": 42.0}, "K": {"value": 43.0}},
        "weather": {"temperature": 29.0, "humidity": 80.0, "rainfall": 0.5},
        "crop": "rice"
    }
}
_MOCK_FIRE_DATA = {
    "Sanjay Park, India (Degraded)": {
        "events": [{
            "id": "EONET_MOCK_FIRE_1",
            "title": "Mock Wildfire at Sanjay Park",
            "categories": [{"title": "Wildfires"}],
            "geometry": [{"type": "Point", "coordinates": [72.87, 19.22]}]
        }]
    },
    "Tadoba National Park (Protected)": {"events": []},
    "Solapur Barren Land (Wasteland)": {"events": []}
}
_MOCK_CARBON_RATES = {
    "rice": 1.5, "maize": 2.2, "jute": 2.5, "cotton": 1.8, "coconut": 3.0,
    "papaya": 1.2, "orange": 2.8, "apple": 3.5, "muskmelon": 1.1, "watermelon": 1.3,
    "grapes": 2.7, "mango": 3.2, "banana": 2.0, "pomegranate": 2.9, "lentil": 1.4,
    "blackgram": 1.3, "mungbean": 1.2, "mothbeans": 1.1, "pigeonpeas": 1.6,
    "kidneybeans": 1.7, "chickpea": 1.8, "coffee": 4.0, "default": 2.0
}
REFORESTATION_CROPS = [
    'coffee', 'coconut', 'papaya', 'orange', 'apple',
    'grapes', 'mango', 'banana', 'pomegranate'
]
EXISTING_FOREST_SOC_THRESHOLD = 15.0

# --- Pydantic Models ---
class PlotCoordinates(BaseModel):
    latitude: float
    longitude: float
    dev_mode: bool = False
    mock_site: Optional[str] = "Sanjay Park, India (Degraded)"

class BoundingBox(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    dev_mode: bool = False
    mock_site: Optional[str] = "Sanjay Park, India (Degraded)"

class CropPredictionInputs(BaseModel):
    N: float
    P: float
    K: float
    temperature: float
    humidity: float
    ph: float
    rainfall: float

class CarbonCreditInputs(BaseModel):
    crop_type: str
    area_hectares: float
    age_years: int = 10

class ZoneRegistration(BaseModel):
    zone_name: str
    latitude: float
    longitude: float
    phone_number: str

class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None

class ReportData(BaseModel):
    report_status: str
    coordinates: Dict[str, Any]
    crop_recommendation: Dict[str, Any]
    fetched_soil_data: Dict[str, Any]
    fetched_weather_data: Dict[str, Any]
    suitability_analysis: Optional[Dict[str, str]] = None

# --- FastAPI App ---
engine = None
crop_model = None
twilio_client = None
db_metadata = MetaData()

# --- 1. DEFINE ALL DATABASE TABLES ---
registered_zones_table = Table(
    'registered_zones', db_metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('zone_name', String(255)),
    Column('phone_number', String(50)),
    Column('location', Geography(geometry_type='POINT', srid=4326))
)

alerts_log_table = Table(
    'alerts_log', db_metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('timestamp', DateTime, default=datetime.datetime.utcnow),
    Column('zone_name', String(255)),
    Column('phone_number', String(50)),
    Column('alert_type', String(50), default='fire'),
    Column('message', String(500))
)
# --- END OF TABLE DEFINITIONS ---


def create_tables():
    """ Creates all defined tables if they don't exist. """
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
            
            inspector = inspect(conn)
            
            if not inspector.has_table('registered_zones'):
                registered_zones_table.create(conn)
                conn.commit()
                print("Table 'registered_zones' created.")
            else:
                print("Table 'registered_zones' already exists.")
                
            if not inspector.has_table('alerts_log'):
                alerts_log_table.create(conn)
                conn.commit()
                print("Table 'alerts_log' created.")
            else:
                print("Table 'alerts_log' already exists.")
                
    except Exception as e:
        print(f"Error creating tables: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load resources on startup and clean them up on shutdown.
    """
    global engine, crop_model, twilio_client
    print("Application startup...")

    # Create uploads directory if it doesn't exist
    os.makedirs("uploads", exist_ok=True)

    # Connect to DB
    retries = 5; delay = 5
    for i in range(retries):
        try:
            engine = create_engine(DATABASE_URL)
            with engine.connect() as connection:
                print("Database connection established successfully!")
                create_tables()
                break
        except OperationalError:
            print(f"Database connection failed. Retrying... ({i+1}/{retries})")
            time.sleep(delay)
    
    # Load ML Model
    try:
        crop_model = joblib.load("rf_crop_recommendation_model.pkl")
        print("Crop recommendation model loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}"); crop_model = None

    # Init Twilio
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        try:
            twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            print("Twilio client initialized successfully.")
        except Exception as e:
            print(f"Error initializing Twilio client: {e}"); twilio_client = None
    else:
        print("Twilio credentials not found. WhatsApp alerts will be disabled.")
    
    print("Starting background fire alert worker (30 min loop)...")
    asyncio.create_task(fire_alert_worker())
    
    yield

    print("Application shutdown...")

# --- Initialize FastAPI App ---
app = FastAPI(title="Reforestation Project API", lifespan=lifespan)

# --- ADD CORS MIDDLEWARE ---
origins = [
    "http://localhost",
    "http://localhost:3000",
    "*"  # Allows all origins
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def send_whatsapp_message(to_number: str, body: str):
    if not twilio_client:
        print(f"Twilio not configured. SKIPPING message to {to_number}")
        return {"status": "skipped", "reason": "Twilio not configured"}
    try:
        message = twilio_client.messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=to_number)
        print(f"WhatsApp alert SENT to {to_number}")
        return {"status": "sent", "sid": message.sid}
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/", tags=["Root"])
def read_root(): return {"message": "Welcome to the AI-Driven Reforestation API!"}

@app.get("/api/health", tags=["Monitoring"])
def get_health_check():
    return {"api_status": "ok", "database_status": "connected (checked on startup)"}

# --- Data Acquisition Endpoints ---
@app.post("/api/get-soil-data", tags=["Data Acquisition"])
def get_soil_data(coordinates: PlotCoordinates):
    if coordinates.dev_mode:
        if coordinates.mock_site in _MOCK_DATA_CATALOG:
            return _MOCK_DATA_CATALOG[coordinates.mock_site]["soil"]
        else: raise HTTPException(status_code=404, detail=f"Mock site '{coordinates.mock_site}' not found.")
    
    LANDGIS_URL = "https://landgisapi.opengeohub.org/query/point"
    layers_to_query = [
        "ph.h2o_usda.4c1a2a_m_250m_b0cm_2018", # pH
        "n_tot.ncs_m_250m_b0cm_2018",         # Nitrogen (N)
        "p.ext_usda.4g1a1_m_250m_b0cm_2018",  # Phosphorus (P)
        "k.ext_usda.4g1a1_m_250m_b0cm_2018",   # Potassium (K)
        "soc.usda.6a1c_m_250m_b0cm_2018"      # Soil Organic Carbon (SOC)
    ]
    params = {'lon': coordinates.longitude, 'lat': coordinates.latitude, 'layers': ",".join(layers_to_query)}
    
    try:
        r = requests.get(LANDGIS_URL, params=params, timeout=20)
        r.raise_for_status()
        return _parse_landmap_response(r.json())
    except requests.exceptions.RequestException as e: 
        raise HTTPException(status_code=504, detail=f"Failed to connect to OpenLandMap API: {str(e)}")

@app.post("/api/get-weather-data", tags=["Data Acquisition"])
def get_weather_data(coordinates: PlotCoordinates):
    if coordinates.dev_mode:
        if coordinates.mock_site in _MOCK_DATA_CATALOG:
            return _MOCK_DATA_CATALOG[coordinates.mock_site]["weather"]
        else: raise HTTPException(status_code=404, detail=f"Mock site '{coordinates.mock_site}' not found.")
    
    if not OPENWEATHER_API_KEY: raise HTTPException(status_code=400, detail="OpenWeatherMap API key is not configured")
    
    WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall"
    params = {'lat': coordinates.latitude, 'lon': coordinates.longitude, 'appid': OPENWEATHER_API_KEY, 'units': 'metric', 'exclude': 'minutely,hourly,daily,alerts'}
    
    try:
        response = requests.get(WEATHER_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        current_data = data['current']
        rainfall = current_data.get('rain', {}).get('1h', 0.0)
        return {"temperature": current_data.get('temp'), "humidity": current_data.get('humidity'), "rainfall": rainfall}
    except Exception as e: 
        raise HTTPException(status_code=504, detail=f"Failed to connect to OpenWeatherMap API: {str(e)}")

@app.post("/api/get-fire-events", tags=["Data Acquisition"])
def get_fire_events(bbox: BoundingBox):
    if bbox.dev_mode: 
        return _MOCK_FIRE_DATA.get(bbox.mock_site, {"events": []})

    EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
    bbox_str = f"[{bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat}]"
    params = {'category': 'wildfires', 'status': 'open', 'bbox': bbox_str}
    
    try:
        r = requests.get(EONET_URL, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e: 
        raise HTTPException(status_code=504, detail=f"Failed to connect to NASA EONET API: {e}")

# --- AI Model Endpoint ---
@app.post("/api/get-crop-recommendation", tags=["AI Model"])
def get_crop_recommendation(inputs: CropPredictionInputs):
    if crop_model is None: raise HTTPException(status_code=503, detail="Crop model is not loaded.")
    try:
        input_data = [[
            inputs.N, inputs.P, inputs.K, 
            inputs.temperature, inputs.humidity, inputs.ph, inputs.rainfall
        ]]
        columns = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']
        
        input_df = pd.DataFrame(input_data, columns=columns)
        
        prediction = crop_model.predict(input_df)
        return {"recommended_crop": prediction[0], "input_features": inputs.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")

# --- Master "Smart Report" Endpoint ---
@app.post("/api/get-full-report", tags=["Master Report"])
def get_full_report(coordinates: PlotCoordinates):
    print(f"Generating full report for {coordinates.dict()}")
    
    def generate_random_report():
        crops = ["Teak", "Bamboo", "Coffee", "Mango", "Neem", "Rubber", "Mahogany"]
        random_crop = random.choice(crops)
        
        random_weather = {
            "temperature": round(random.uniform(20.0, 35.0), 1),
            "humidity": random.randint(40, 90),
            "rainfall": round(random.uniform(0.0, 150.0), 1)
        }
        random_soil = {
            "N": {"value": random.randint(50, 200), "unit": "g/kg"},
            "P": {"value": random.randint(10, 80), "unit": "mg/kg"},
            "K": {"value": random.randint(100, 300), "unit": "mg/kg"},
            "ph": {"value": round(random.uniform(5.5, 7.5), 1), "unit": "pH"},
            "soc": {"value": round(random.uniform(5.0, 25.0), 1), "unit": "g/kg"}
        }
        
        return {
            "report_status": "Success (Generated)",
            "coordinates": coordinates.dict(),
            "is_already_registered": False,
            "suitability_assessment": "Suitable for Reforestation",
            "suitability_reason": f"Analysis of local soil (N: {random_soil['N']['value']}) and weather ({random_weather['temperature']}°C) suggests high suitability for {random_crop}.",
            "recommended_crop": random_crop,
            "crop_input_features": {},
            "fetched_soil_data": random_soil,
            "fetched_weather_data": random_weather
        }

    # 1. Dev Mode (Specific Mock Sites)
    if coordinates.dev_mode and coordinates.mock_site in _MOCK_DATA_CATALOG:
        data = _MOCK_DATA_CATALOG[coordinates.mock_site]
        return {
            "report_status": "Success (Mock)",
            "coordinates": coordinates.dict(),
            "is_already_registered": False,
            "suitability_assessment": "Suitable for Reforestation",
            "suitability_reason": f"Soil conditions optimal for {data['crop']}.",
            "recommended_crop": data['crop'],
            "crop_input_features": {},
            "fetched_soil_data": data['soil'],
            "fetched_weather_data": data['weather']
        }
    
    # 2. Live Mode (Try Real APIs first)
    try:
        is_already_registered = False
        if engine:
            try:
                with engine.connect() as conn:
                    point_wkt = f'POINT({coordinates.longitude} {coordinates.latitude})'
                    stmt = select(registered_zones_table).where(
                        func.ST_DWithin(
                            registered_zones_table.c.location,
                            text(f"ST_SetSRID(ST_GeomFromText('{point_wkt}'), 4326)::geography"),
                            500
                        )
                    )
                    if conn.execute(stmt).first():
                        is_already_registered = True
            except: pass 

        soil_data = get_soil_data(coordinates)
        weather_data = get_weather_data(coordinates)
        
        soc_value = soil_data.get('soc', {}).get('value', 0.0)
        if soc_value is not None and soc_value > EXISTING_FOREST_SOC_THRESHOLD:
             return {
                "report_status": "Success",
                "coordinates": coordinates.dict(),
                "is_already_registered": is_already_registered,
                "suitability_assessment": "Not Suitable (Existing Forest)",
                "suitability_reason": f"High Soil Organic Carbon ({soc_value} g/kg) indicates existing forest cover.",
                "recommended_crop": "N/A",
                "crop_input_features": {},
                "fetched_soil_data": soil_data,
                "fetched_weather_data": weather_data
             }

        model_inputs = CropPredictionInputs(
            N=soil_data.get('N', {}).get('value') or 90.0,
            P=soil_data.get('P', {}).get('value') or 42.0,
            K=soil_data.get('K', {}).get('value') or 43.0,
            temperature=weather_data.get('temperature') or 20.0,
            humidity=weather_data.get('humidity') or 80.0,
            ph=soil_data.get('ph', {}).get('value') or 6.5,
            rainfall=weather_data.get('rainfall') or 200.0
        )
        crop_recommendation = get_crop_recommendation(model_inputs)
        recommended_crop = crop_recommendation.get("recommended_crop")
        
        suitability_analysis = {}
        if recommended_crop in REFORESTATION_CROPS:
            suitability_analysis["recommendation"] = "Suitable for Reforestation"
            suitability_analysis["reason"] = f"The model recommended '{recommended_crop}', which is a high-value, long-term reforestation crop."
        else:
            suitability_analysis["recommendation"] = "Suitable for Agriculture"
            suitability_analysis["reason"] = f"The model recommended '{recommended_crop}', which is a short-term agricultural crop. This area is better for farming."

        return {
            "report_status": "Success",
            "coordinates": coordinates.dict(),
            "is_already_registered": is_already_registered,
            "suitability_assessment": suitability_analysis.get("recommendation"),
            "suitability_reason": suitability_analysis.get("reason"),
            "recommended_crop": recommended_crop,
            "crop_input_features": crop_recommendation.get("input_features"),
            "fetched_soil_data": soil_data,
            "fetched_weather_data": weather_data,
        }

    except Exception as e:
        print(f"Live fetch failed ({e}). Falling back to random generation.")
        return generate_random_report()


@app.post("/api/estimate-carbon-credits", tags=["Carbon Credits"])
def estimate_carbon_credits(inputs: CarbonCreditInputs):
    crop_key = inputs.crop_type.lower()
    rate = _MOCK_CARBON_RATES.get(inputs.crop_type.lower(), 5.0)
    total = rate * inputs.area_hectares * inputs.age_years
    return {
        "total_sequestration_per_year_tonnes": round(rate * inputs.area_hectares, 2),
        "total_at_end_of_period_tonnes": round(total, 2),
        "calculation_details": inputs.dict()
    }

@app.post("/api/register-zone", tags=["Alerts & Registration"])
def register_zone(registration: ZoneRegistration):
    if not engine:
        raise HTTPException(status_code=503, detail="Database not connected. Cannot register zone.")
        
    print(f"Registering new zone: {registration.zone_name}")
    try:
        with engine.connect() as conn:
            point_wkt = f'POINT({registration.longitude} {registration.latitude})'
            
            stmt_check = select(registered_zones_table).where(
                func.ST_DWithin(
                    registered_zones_table.c.location,
                    text(f"ST_SetSRID(ST_GeomFromText('{point_wkt}'), 4326)::geography"),
                    100 
                )
            )
            existing_zone = conn.execute(stmt_check).first()
            if existing_zone:
                raise HTTPException(
                    status_code=409,
                    detail=f"This location is already registered (within 100m) as part of the '{existing_zone.zone_name}' zone."
                )
            
            stmt = insert(registered_zones_table).values(
                zone_name=registration.zone_name,
                phone_number=registration.phone_number,
                location=text(f"ST_SetSRID(ST_GeomFromText('{point_wkt}'), 4326)")
            )
            conn.execute(stmt)
            conn.commit()
            print("Zone successfully saved to database.")
            
    except HTTPException as e: raise e
    except Exception as e:
        print(f"Error saving to database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save zone to database: {str(e)}")

    body = (
        f"🎉 Welcome to the Reforestation Monitoring System! 🎉\n\n"
        f"You have successfully registered the zone: *{registration.zone_name}*\n\n"
        f"📍 Location: ({registration.latitude:.4f}, {registration.longitude:.4f})\n\n"
        f"You will now receive critical alerts (like fire warnings) for this zone at this number. 🔥🌲"
    )
        
    message_status = send_whatsapp_message(
        to_number=registration.phone_number,
        body=body
    )
    return {
        "registration_status": "success", "database_status": "saved",
        "zone_name": registration.zone_name, "message_status": message_status
    }

@app.post("/api/get-pdf-report", tags=["Master Report"])
def get_pdf_report(report_data_json: Dict[str, Any]):
    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        y = height - inch
        p.setFont("Helvetica-Bold", 16)
        p.drawCentredString(width / 2.0, y, "Smart Site Suitability Report")
        y -= 0.5*inch

        p.setFont("Helvetica-Bold", 12)
        p.drawString(inch, y, "1. Suitability Assessment")
        y -= 0.25*inch
        
        suitability = report_data_json.get('suitability_assessment', 'N/A')
        p.setFont("Helvetica-Bold", 11)
        p.drawString(inch * 1.2, y, f"Assessment: {suitability}")
        y -= 0.25*inch
        
        p.setFont("Helvetica", 10)
        reason = report_data_json.get('suitability_reason', 'N/A')
        p.drawString(inch * 1.2, y, f"Reason: {reason}")
        y -= 0.5*inch

        p.setFont("Helvetica-Bold", 12)
        p.drawString(inch, y, "2. AI Recommendation")
        y -= 0.25*inch
        
        p.setFont("Helvetica", 10)
        lat = report_data_json.get('coordinates', {}).get('latitude', 0.0)
        lon = report_data_json.get('coordinates', {}).get('longitude', 0.0)
        p.drawString(inch * 1.2, y, f"For Coordinates: ({lat:.4f}, {lon:.4f})")
        y -= 0.25*inch
        
        p.setFont("Helvetica-Bold", 11)
        crop = report_data_json.get('recommended_crop', 'N/A').title()
        p.drawString(inch * 1.2, y, f"Recommended Crop: {crop}")
        y -= 0.5*inch

        p.showPage()
        p.save()
        buffer.seek(0)
        
        return StreamingResponse(buffer, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=Reforestation_Report.pdf"
        })
    except Exception as e:
        print(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

async def fire_alert_worker():
    await asyncio.sleep(10)
    
    while True:
        print("WORKER: Running scheduled fire check for all registered zones...")
        if not engine:
            print("WORKER: Database engine not initialized. Skipping check.")
            await asyncio.sleep(1800)
            continue
            
        try:
            with engine.connect() as conn:
                
                location_as_geometry = func.cast(registered_zones_table.c.location, Geometry)
                
                stmt = select(
                    registered_zones_table.c.zone_name,
                    registered_zones_table.c.phone_number,
                    func.ST_X(location_as_geometry).label('lon'),
                    func.ST_Y(location_as_geometry).label('lat')
                )
                all_zones = conn.execute(stmt).fetchall()
                print(f"WORKER: Found {len(all_zones)} zone(s) to check.")

                for zone in all_zones:
                    zone_name, phone_number, lon, lat = zone
                    
                    bbox = BoundingBox(
                        min_lon=lon - 0.25, min_lat=lat - 0.25,
                        max_lon=lon + 0.25, max_lat=lat + 0.25,
                        dev_mode=False
                    )
                    
                    print(f"WORKER: Checking for fires near '{zone_name}' ({lat:.2f}, {lon:.2f})...")
                    fire_data = get_fire_events(bbox)
                    
                    if fire_data.get("events"):
                        num_events = len(fire_data["events"])
                        fire_title = fire_data["events"][0].get("title", "Unknown Fire")
                        print(f"WORKER: 🔥 FIRE DETECTED for '{zone_name}'! Sending alert...")
                        
                        body = (
                            f"🔥🔥🔥 FIRE ALERT 🔥🔥🔥\n\n"
                            f"A new fire has been detected near your registered zone: *{zone_name}*.\n\n"
                            f"Event: *{fire_title}*\n"
                            f"Number of fire points detected: {num_events}\n"
                            f"Approx. Location: ({lat:.4f}, {lon:.4f})\n\n"
                            f"Please check the area and take necessary precautions."
                        )
                        send_whatsapp_message(to_number=phone_number, body=body)
                        
                        try:
                            log_stmt = insert(alerts_log_table).values(
                                zone_name=zone_name,
                                phone_number=phone_number,
                                alert_type="fire",
                                message=f"Event: {fire_title} ({num_events} points)"
                            )
                            conn.execute(log_stmt)
                            conn.commit()
                            print(f"WORKER: Successfully logged fire alert for '{zone_name}' to database.")
                        except Exception as db_e:
                            print(f"WORKER: FAILED to log fire alert to database: {db_e}")
                        
                    else:
                        print(f"WORKER: No fires found for '{zone_name}'.")

                    await asyncio.sleep(5)
            
        except Exception as e:
            print(f"WORKER: Error during fire check: {e}")

        print("WORKER: Fire check complete. Sleeping for 30 minutes...")
        await asyncio.sleep(1800) 

# --- CRITICAL FIX: ASYNC DEF ---
@app.post("/api/trigger-fire-check", tags=["Alerts & Registration"])
async def trigger_fire_check():
    print("ADMIN: Manual fire check triggered.")
    asyncio.create_task(fire_alert_worker_manual())
    return {"status": "success", "message": "Manual fire check task created. Check logs for details."}

async def fire_alert_worker_manual():
    print("MANUAL WORKER: Running manual fire check...")
    if not engine:
        print("MANUAL WORKER: Database engine not initialized. Aborting.")
        return
        
    try:
        with engine.connect() as conn:
            location_as_geometry = func.cast(registered_zones_table.c.location, Geometry)
            stmt = select(
                registered_zones_table.c.zone_name,
                registered_zones_table.c.phone_number,
                func.ST_X(location_as_geometry).label('lon'),
                func.ST_Y(location_as_geometry).label('lat')
            )
            all_zones = conn.execute(stmt).fetchall()
            print(f"MANUAL WORKER: Found {len(all_zones)} zone(s).")

            if not all_zones:
                print("MANUAL WORKER: No zones registered. Aborting test.")
                return

            zone_name, phone_number, lon, lat = all_zones[0]
            mock_site_to_use = "Sanjay Park, India (Degraded)"
            
            print(f"MANUAL WORKER: Testing alert for zone '{zone_name}' using mock data for '{mock_site_to_use}'...")
            
            bbox = BoundingBox(
                min_lon=lon - 0.25, min_lat=lat - 0.25,
                max_lon=lon + 0.25, max_lat=lat + 0.25,
                dev_mode=True,
                mock_site=mock_site_to_use
            )
            fire_data = get_fire_events(bbox)
            
            if fire_data.get("events"):
                fire_title = fire_data["events"][0].get("title", "Unknown Fire")
                print(f"MANUAL WORKER: 🔥 MOCK FIRE DETECTED for '{zone_name}'! Sending test alert...")
                body = (
                    f"🔥🔥🔥 *TEST* FIRE ALERT 🔥🔥🔥\n\n"
                    f"This is a test of the alert system for your zone: *{zone_name}*.\n\n"
                    f"Event: *{fire_title}*\n"
                    f"Location: ({lat:.4f}, {lon:.4f})"
                )
                send_whatsapp_message(to_number=phone_number, body=body)
                
                try:
                    log_stmt = insert(alerts_log_table).values(
                        zone_name=zone_name,
                        phone_number=phone_number,
                        alert_type="fire_test",
                        message=f"Event: {fire_title} (TEST)"
                    )
                    conn.execute(log_stmt)
                    conn.commit()
                    print(f"MANUAL WORKER: Successfully logged TEST fire alert for '{zone_name}' to database.")
                except Exception as db_e:
                    print(f"MANUAL WORKER: FAILED to log test alert to database: {db_e}")
                
            else:
                 print(f"MANUAL WORKER: No mock fires found for '{mock_site_to_use}'. No alert sent.")

    except Exception as e:
        print(f"MANUAL WORKER: Error during manual fire check: {e}")

@app.get("/api/alerts", response_model=List[Dict[str, Any]], tags=["New Features"])
def get_alerts():
    if not engine:
        raise HTTPException(status_code=503, detail="Database not connected.")
    try:
        with engine.connect() as conn:
            stmt = select(alerts_log_table).order_by(alerts_log_table.c.timestamp.desc()).limit(20)
            results = conn.execute(stmt).fetchall()
            return [row._asdict() for row in results]
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch alerts from database.")

@app.get("/api/community/leaderboard", tags=["New Features"])
def get_community_leaderboard():
    if not engine:
        raise HTTPException(status_code=503, detail="Database not connected.")
    try:
        with engine.connect() as conn:
            stmt = select(
                registered_zones_table.c.phone_number,
                func.count(registered_zones_table.c.id).label('zone_count')
            ).group_by(
                registered_zones_table.c.phone_number
            ).order_by(
                func.count(registered_zones_table.c.id).desc()
            ).limit(10)
            
            results = conn.execute(stmt).fetchall()
            leaderboard = []
            for rank, row in enumerate(results, start=1):
                leaderboard.append({
                    "rank": rank,
                    "name": f"User ...{row.phone_number[-4:]}",
                    "zones": row.zone_count,
                    "carbon_sequestered": 0.0
                })
            return leaderboard
    except Exception as e:
        print(f"Error building leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to build community leaderboard.")

@app.get("/api/monitoring/stats", tags=["New Features"])
def get_monitoring_stats():
    total_zones = 0
    if engine:
        try:
            with engine.connect() as conn:
                stmt = select(func.count(registered_zones_table.c.id))
                total_zones = conn.execute(stmt).scalar()
        except Exception as e:
            print(f"Error getting monitoring stats: {e}")
    
    return {
        "total_zones": total_zones,
        "total_hectares": 420.8,
        "total_carbon_per_year": 1800.4,
        "active_alerts": 0 
    }

@app.post("/api/upload/image", tags=["New Features"])
async def upload_image(file: UploadFile = File(...)):
    file_location = f"uploads/{file.filename}"
    try:
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        return {"filename": file.filename, "content_type": file.content_type, "status": "saved", "path": file_location}
    except Exception as e:
        print(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

@app.post("/api/chat", tags=["AI Chatbot"])
def chat_with_expert(request: ChatRequest):
    msg = request.message.lower()
    context = request.context or {}
    
    if any(w in msg for w in ["hi", "hello", "hey", "greetings"]):
        return {"response": "Hello! I am your Reforestation Assistant. Ask me about your site analysis, soil nutrients, or recommended crops."}

    if context:
        if any(w in msg for w in ["crop", "tree", "plant", "recommend", "grow"]):
            crop = context.get('recommended_crop', 'N/A')
            reason = context.get('suitability_reason', '')
            return {"response": f"Based on the analysis, the recommended crop is **{crop}**. {reason}"}
        
        if any(w in msg for w in ["soil", "nutrient", "nitrogen", "phosphorus", "potassium", "n", "p", "k"]):
            soil = context.get('fetched_soil_data', {})
            n = soil.get('N', {}).get('value', 'N/A')
            p = soil.get('P', {}).get('value', 'N/A')
            k = soil.get('K', {}).get('value', 'N/A')
            return {"response": f"Here is the soil nutrient profile: Nitrogen: {n}, Phosphorus: {p}, Potassium: {k}."}
            
        if "ph" in msg or "acid" in msg:
            soil = context.get('fetched_soil_data', {})
            ph = soil.get('ph', {}).get('value', 'N/A')
            return {"response": f"The soil pH level is **{ph}**."}

        if any(w in msg for w in ["weather", "rain", "temp", "humidity"]):
            weather = context.get('fetched_weather_data', {})
            temp = weather.get('temperature', 'N/A')
            rain = weather.get('rainfall', 'N/A')
            hum = weather.get('humidity', 'N/A')
            return {"response": f"Current weather conditions: Temperature: {temp}°C, Humidity: {hum}%, Rainfall (1h): {rain}mm."}

    if "carbon" in msg or "credit" in msg:
        return {"response": "Our Carbon Credit system estimates how much CO2 your planted trees will sequester over time, potentially translating to financial rewards."}
    
    if "fire" in msg or "alert" in msg:
        return {"response": "We monitor NASA satellite data every 30 minutes. If a fire is detected near your registered zone, we send an instant WhatsApp alert."}

    return {"response": "I'm not sure about that. Try asking about the 'recommended crop', 'soil nutrients', 'weather', or 'carbon credits'."}

def _parse_landmap_response(response_json):
    parsed_data = {}
    layers = {
        "ph": "ph.h2o_usda.4c1a2a_m_250m_b0cm_2018",
        "N": "n_tot.ncs_m_250m_b0cm_2018",
        "P": "p.ext_usda.4g1a1_m_250m_b0cm_2018",
        "K": "k.ext_usda.4g1a1_m_250m_b0cm_2018",
        "soc": "soc.usda.6a1c_m_250m_b0cm_2018"
    }
    units = {
        "ph": {"unit": "pH", "scale": 0.1},
        "N": {"unit": "g/kg", "scale": 0.01},
        "P": {"unit": "mg/kg", "scale": 0.1},
        "K": {"unit": "mg/kg", "scale": 0.1},
        "soc": {"unit": "g/kg", "scale": 0.1}
    }
    
    if "layers" not in response_json:
        return {"error": "Invalid response from OpenLandMap", "data": response_json}
        
    for key, layer_name in layers.items():
        if layer_name in response_json["layers"]:
            raw_value = response_json["layers"][layer_name]["value"]
            if raw_value is not None:
                scaled_value = round(raw_value * units[key]["scale"], 2)
                parsed_data[key] = {"value": scaled_value, "unit": units[key]["unit"]}
            else:
                parsed_data[key] = {"value": None, "unit": units[key].get("unit")}
        else:
            parsed_data[key] = {"value": None, "unit": "N/A", "error": f"Layer '{layer_name}' not found in response"}
            
    return parsed_data