from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# OpenRouteService API key
ORS_API_KEY = os.getenv("ORS_API_KEY")

# Emission factors (kg CO₂ per km per person)
EMISSION_FACTORS = {
    "foot-walking": 0.00,
    "cycling-regular": 0.00,
    "driving-car": 0.192,  # Gasoline
    "publicTransport": 0.041  # Subway / train as default
}

# Function to convert an address to latitude/longitude
def get_coordinates(address):
    url = f"https://api.openrouteservice.org/geocode/search?api_key={ORS_API_KEY}&text={address}"
    response = requests.get(url)
    data = response.json()

    if "features" in data and len(data["features"]) > 0:
        lon, lat = data["features"][0]["geometry"]["coordinates"]
        return lat, lon  # Return (latitude, longitude)

    return None  # Address not found

# Function to get a route and estimate CO₂ emissions
def get_route_and_emissions(origin, destination, mode="cycling-regular"):
    url = f"https://api.openrouteservice.org/v2/directions/{mode}?api_key={ORS_API_KEY}&start={origin[1]},{origin[0]}&end={destination[1]},{destination[0]}"
    
    response = requests.get(url)
    route_data = response.json()

    if "routes" not in route_data:
        return None, None  # No route found

    # Extract total distance (meters) from route response
    total_distance_m = route_data["routes"][0]["summary"]["distance"]
    total_distance_km = total_distance_m / 1000  # Convert to km

    # Estimate CO₂ emissions
    emissions = EMISSION_FACTORS.get(mode, 0) * total_distance_km

    return route_data, emissions

# API Endpoint: Get the best eco-friendly route
@app.route('/get-route', methods=['GET'])
def get_route():
    origin_address = request.args.get('origin')
    destination_address = request.args.get('destination')
    mode = request.args.get('mode', "cycling-regular")  # Default: cycling

    if not origin_address or not destination_address:
        return jsonify({"error": "Missing origin or destination"}), 400

    # Convert addresses to coordinates
    origin_coords = get_coordinates(origin_address)
    destination_coords = get_coordinates(destination_address)

    if not origin_coords or not destination_coords:
        return jsonify({"error": "Invalid address"}), 400

    # Get route and CO₂ emissions
    route, emissions = get_route_and_emissions(origin_coords, destination_coords, mode)

    if not route:
        return jsonify({"error": "No route found"}), 404

    return jsonify({
        "route": route,
        "co2_emissions_kg": round(emissions, 3)
    })

# Run Flask app
if __name__ == '__main__':
    app.run(debug=True)