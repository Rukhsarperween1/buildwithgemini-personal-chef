# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from google.cloud import firestore

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-a66c61c823be"
GCS_BUCKET_NAME = "personal-chef-media-qwiklabs-gcp-01-a66c61c823be"

# Read Agent Engine resource name from deployment_metadata.json if available
deployment_metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_resource_name = None
if deployment_metadata_path.exists():
    with open(deployment_metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        agent_engine_resource_name = meta.get("remote_agent_runtime_id")

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name,
    optimize_data_file=True,
)


def _get_db() -> firestore.Client:
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def list_recipes(cuisine: str = None, tag: str = None) -> list[dict]:
    """Lists recipes stored in the Firestore database. Can optionally filter by cuisine or tag.

    Args:
        cuisine: Optional filter for cuisine type (e.g. 'Italian', 'Thai', 'American').
        tag: Optional filter for diet or category tag (e.g. 'Gluten-Free', 'Vegan', 'Quick').

    Returns:
        A list of recipe dictionaries.
    """
    db = _get_db()
    query = db.collection("recipes")
    if cuisine:
        query = query.where("cuisine", "==", cuisine)
    docs = query.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if tag:
            tags = [t.lower() for t in data.get("tags", [])]
            if tag.lower() not in tags:
                continue
        results.append(data)
    return results


def get_recipe(recipe_id: str) -> dict:
    """Retrieves full details of a specific recipe by ID.

    Args:
        recipe_id: The unique document ID of the recipe (e.g. 'creamy-tuscan-chicken').

    Returns:
        A dictionary containing recipe details or an error message if not found.
    """
    db = _get_db()
    doc = db.collection("recipes").document(recipe_id).get()
    if not doc.exists:
        return {"error": f"Recipe with ID '{recipe_id}' not found."}
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def add_recipe(
    name: str,
    cuisine: str,
    prep_time_minutes: int,
    cook_time_minutes: int,
    servings: int,
    ingredients: list[str],
    instructions: list[str],
    tags: list[str] = None,
) -> dict:
    """Adds a new recipe to the Firestore database.

    Args:
        name: Name of the dish.
        cuisine: Cuisine style (e.g., Italian, Mexican, Asian, American).
        prep_time_minutes: Preparation time in minutes.
        cook_time_minutes: Cooking time in minutes.
        servings: Number of servings.
        ingredients: List of ingredients with quantities.
        instructions: Step-by-step cooking instructions.
        tags: Optional tags like 'Gluten-Free', 'Vegetarian', 'Quick'.

    Returns:
        A dictionary with the creation status and new recipe document.
    """
    db = _get_db()
    doc_id = name.lower().replace(" ", "-")
    recipe_data = {
        "name": name,
        "cuisine": cuisine,
        "prep_time_minutes": prep_time_minutes,
        "cook_time_minutes": cook_time_minutes,
        "servings": servings,
        "ingredients": ingredients,
        "instructions": instructions,
        "tags": tags or [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("recipes").document(doc_id).set(recipe_data)
    recipe_data["id"] = doc_id
    return {"status": "success", "recipe": recipe_data}


def scale_recipe_ingredients(recipe_id: str, target_servings: int) -> dict:
    """Scales a recipe's ingredient quantities based on a target number of servings.

    Args:
        recipe_id: The unique ID of the recipe (e.g. 'creamy-tuscan-chicken').
        target_servings: The target number of servings desired.

    Returns:
        A dictionary containing scaling details and updated ingredient quantities.
    """
    import re

    db = _get_db()
    doc = db.collection("recipes").document(recipe_id).get()
    if not doc.exists:
        return {"error": f"Recipe with ID '{recipe_id}' not found."}

    data = doc.to_dict()
    base_servings = data.get("servings", 1) or 1
    scale_factor = target_servings / base_servings

    scaled_ingredients = []
    for ingredient in data.get("ingredients", []):
        match = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+)\s*(.*)", ingredient.strip())
        if match:
            num_str, rest = match.groups()
            val = (
                float(num_str.split("/")[0]) / float(num_str.split("/")[1])
                if "/" in num_str
                else float(num_str)
            )
            scaled_val = val * scale_factor
            formatted_val = (
                str(int(scaled_val))
                if scaled_val.is_integer()
                else f"{scaled_val:.2f}".rstrip("0").rstrip(".")
            )
            scaled_ingredients.append(f"{formatted_val} {rest}")
        else:
            scaled_ingredients.append(
                f"{ingredient} (scale factor x{scale_factor:.2f})"
            )

    return {
        "recipe_id": recipe_id,
        "recipe_name": data.get("name") or data.get("title", recipe_id),
        "original_servings": base_servings,
        "target_servings": target_servings,
        "scale_factor": round(scale_factor, 2),
        "scaled_ingredients": scaled_ingredients,
    }


def search_online_recipes(query: str) -> list[dict]:
    """Searches the global TheMealDB API for real online recipe ideas, instructions, and images.

    Args:
        query: Name or keyword of a dish or ingredient to search for (e.g. 'pasta', 'chicken', 'tacos').

    Returns:
        A list of matching recipe summary dictionaries.
    """
    import json
    import urllib.parse
    import urllib.request

    encoded_query = urllib.parse.quote(query)
    url = f"https://www.themealdb.com/api/json/v1/1/search.php?s={encoded_query}"

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "PersonalChefAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            meals = data.get("meals")
            if not meals:
                return []

            results = []
            for meal in meals[:5]:
                ingredients = []
                for i in range(1, 21):
                    ing = meal.get(f"strIngredient{i}")
                    meas = meal.get(f"strMeasure{i}")
                    if ing and ing.strip():
                        ingredients.append(
                            f"{meas.strip() if meas else ''} {ing.strip()}".strip()
                        )

                results.append({
                    "id": meal.get("idMeal"),
                    "name": meal.get("strMeal"),
                    "category": meal.get("strCategory"),
                    "cuisine": meal.get("strArea"),
                    "instructions": meal.get("strInstructions"),
                    "image_url": meal.get("strMealThumb"),
                    "youtube_url": meal.get("strYoutube"),
                    "ingredients": ingredients,
                })
            return results
    except Exception as e:
        return [{"error": f"Failed to fetch recipes from online API: {str(e)}"}]


def geocode_address(address: str) -> dict:
    """Converts a physical address or location name into geographical coordinates (latitude and longitude) using the Google Maps Geocoding API.

    Args:
        address: The street address or city/place name (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A dictionary containing the formatted address and location coordinates ({'lat': ..., 'lng': ...}).
    """
    import json
    import os
    import urllib.parse
    import urllib.request

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {
            "error": "GOOGLE_MAPS_API_KEY is not configured in environment variables."
        }

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") != "OK" or not data.get("results"):
                return {
                    "error": f"Geocoding failed with status: {data.get('status')}",
                    "details": data.get("error_message"),
                }

            top_result = data["results"][0]
            return {
                "address": top_result.get("formatted_address"),
                "location": top_result.get("geometry", {}).get("location"),
            }
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "supermarket",
    radius_meters: float = 1000.0,
) -> list[dict]:
    """Finds nearby places of a specified type using the Google Maps Places API (New) searchNearby endpoint.

    Args:
        latitude: Latitude coordinate for the center of the search circle.
        longitude: Longitude coordinate for the center of the search circle.
        place_type: Type of place to search for (e.g. 'supermarket', 'grocery_store', 'restaurant', 'bakery').
        radius_meters: Search radius in meters (default 1000m).

    Returns:
        A list of place dictionaries containing key fields (name, address, location).
    """
    import json
    import os
    import urllib.request

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return [
            {
                "error": "GOOGLE_MAPS_API_KEY is not configured in environment variables."
            }
        ]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            places = data.get("places", [])
            results = []
            for place in places:
                display_name = place.get("displayName", {})
                name_text = (
                    display_name.get("text")
                    if isinstance(display_name, dict)
                    else str(display_name)
                )
                results.append({
                    "name": name_text,
                    "address": place.get("formattedAddress"),
                    "location": place.get("location"),
                })
            return results
    except Exception as e:
        return [{"error": f"Failed to call Places API (New): {str(e)}"}]


async def generate_dish_image(
    dish_name: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates an appetizing food photo for a dish using Gemini, saves it as a session artifact, and uploads it to Cloud Storage.

    Args:
        dish_name: Name or description of the dish to generate an image for (e.g. 'Creamy Tuscan Garlic Chicken').
        tool_context: Context provided by ADK framework to save session artifacts.

    Returns:
        A dictionary containing the image generation status, filename, and public GCS URL.
    """
    import uuid
    from google import genai
    from google.cloud import storage
    from google.genai import types

    genai_client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )
    prompt = f"A professional gourmet food photography shot of {dish_name}, appetizing, high resolution, beautifully plated"

    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    image_bytes = None
    mime_type = "image/jpeg"
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

    if not image_bytes:
        return {"error": f"Failed to generate image bytes for '{dish_name}'."}

    ext = "png" if "png" in mime_type else "jpg"
    safe_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())[:30]
    filename = f"{safe_name}_{uuid.uuid4().hex[:6]}.{ext}"

    # 1. Save artifact if tool_context is available
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload image bytes to public GCS bucket
    gcs_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = gcs_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "dish_name": dish_name,
        "filename": filename,
        "public_url": public_url,
    }


async def generate_dish_video(
    dish_name: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates a short video demonstration for a dish using Google's Omni model (gemini-omni-flash-preview), saves it as a session artifact, and uploads it to Cloud Storage.

    Args:
        dish_name: Name or description of the dish to generate a video for (e.g. 'Garlic Butter Shrimp').
        tool_context: Context provided by ADK framework to save session artifacts.

    Returns:
        A dictionary containing the video generation status, filename, and public GCS URL.
    """
    import base64
    import uuid
    from google import genai
    from google.cloud import storage
    from google.genai import types

    genai_client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )
    prompt = f"A short video of sizzling {dish_name} in a pan, close up culinary preparation."

    interaction = genai_client.interactions.create(
        model="gemini-omni-flash-preview",
        input=prompt,
    )

    video_bytes = None
    if hasattr(interaction, "output_video") and interaction.output_video:
        data = getattr(interaction.output_video, "data", None)
        if isinstance(data, str):
            video_bytes = base64.b64decode(data)
        elif isinstance(data, bytes):
            video_bytes = data

    if not video_bytes:
        return {"error": f"Failed to generate video bytes for '{dish_name}'."}

    safe_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())[:30]
    filename = f"{safe_name}_{uuid.uuid4().hex[:6]}.mp4"
    mime_type = "video/mp4"

    # 1. Save artifact if tool_context is available so it shows up in Playground's Artifacts panel
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload video bytes to public GCS bucket
    gcs_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = gcs_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "dish_name": dish_name,
        "filename": filename,
        "public_url": public_url,
    }


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_memories_callback(callback_context: CallbackContext):
    """Sends current session events to Vertex AI Memory Bank for long-term fact extraction."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        pass
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a personal chef and recipe assistant. You help users find, view, scale, and add "
        "recipes in your local Firestore database, search global online recipes, generate appetizing dish photos, "
        "or find nearby grocery stores and ingredients. You explicitly pay close attention to, remember, and "
        "strictly adhere to all user food allergies, dietary restrictions, and sensitivities (e.g., gluten, nuts, "
        "dairy, shellfish) mentioned in previous or current conversations. Always verify recipes against remembered "
        "user allergies and personalize your responses accordingly. You can also safely execute Python code using "
        "your code execution sandbox when calculation or code execution is needed."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        list_recipes,
        get_recipe,
        add_recipe,
        scale_recipe_ingredients,
        search_online_recipes,
        generate_dish_image,
        generate_dish_video,
        geocode_address,
        find_nearby_places,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

