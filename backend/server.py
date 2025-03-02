from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging
from dotenv import load_dotenv
from retrying import retry
import json
import networkx as nx
import numpy as np
from scipy.stats import norm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

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

STD_EMISSION_FACTORS = {
    "foot-walking": 0.00,       # No emissions, no uncertainty
    "cycling-regular": 0.00,    # No emissions, no uncertainty
    "driving-car": 0.02,        # Cars have variable fuel efficiency
    "publicTransport": 0.005    # Buses & trains have efficiency variations
}

# Thresholds for alternative transport modes
WALK_THRESHOLD = 2  # Max km for walking
BIKE_THRESHOLD = 5  # Max km for biking

# Retry decorator for handling network failures
@retry(stop_max_attempt_number=3, wait_fixed=2000)
def make_request(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

# Function to convert an address to latitude/longitude
def get_coordinates(address):
    url = f"https://api.openrouteservice.org/geocode/search?api_key={ORS_API_KEY}&text={address}"
    try:
        data = make_request(url)
        if "features" in data and len(data["features"]) > 0:
            lon, lat = data["features"][0]["geometry"]["coordinates"]
            return lat, lon  # Return (latitude, longitude)
    except requests.RequestException as e:
        logging.error(f"Failed to fetch coordinates for {address}: {e}")
    return None  # Address not found

# Function to compute 95% confidence interval
def compute_ci(mean, std_dev, n=30):  # Assume n=30 for estimation accuracy
    z_score = norm.ppf(0.975)  # 95% CI → z = 1.96
    margin_of_error = z_score * (std_dev / np.sqrt(n))
    return mean - margin_of_error, mean + margin_of_error

# Function to get a route and estimate CO₂ emissions
def get_route_and_emissions(origin, destination, mode="cycling-regular"):
    url = f"https://api.openrouteservice.org/v2/directions/{mode}?api_key={ORS_API_KEY}&start={origin[1]},{origin[0]}&end={destination[1]},{destination[0]}"
    
    try:
        route_data = make_request(url)

        # ✅ Check if a valid route exists
        if "features" not in route_data or not route_data["features"]:
            logging.warning(f"❌ No valid route found for mode: {mode}")
            return None, None, None, None

        # ✅ Extract total distance (meters)
        total_distance_m = route_data["features"][0]["properties"]["segments"][0]["distance"]
        total_distance_km = total_distance_m / 1000  # Convert to km

        # ✅ Estimate CO₂ emissions
        emissions = EMISSION_FACTORS.get(mode, 0) * total_distance_km

        # ✅ Compute 95% confidence interval
        std_dev = STD_EMISSION_FACTORS.get(mode, 0) * total_distance_km  # Scale std dev with distance
        ci_lower, ci_upper = compute_ci(emissions, std_dev)

        return total_distance_km, emissions, (ci_lower, ci_upper), route_data
    except requests.RequestException as e:
        logging.error(f"⚠ API Request failed for {mode}: {e}")
    return None, None, None, None

# Function to calculate logistic scaling factor for buses
def logistic_scaling_factor(distance_km):
    S = 0.3  # Maximum extra distance factor (e.g., 30% longer for buses)
    k = 0.1  # Steepness of transition
    d0 = 30  # Midpoint of transition (scaling stabilizes near 30 km)
    return 1 + (S / (1 + np.exp(-k * (distance_km - d0))))

# Function to approximate public transport route
def approximate_public_transport_route(origin, destination):
    drive_dist, _, _, drive_route = get_route_and_emissions(origin, destination, "driving-car")

    if drive_dist is None:
        logging.warning("❌ No valid public transport route found.")
        return None, None, (None, None), None

    # Estimate distance using scaling factors
    if drive_dist > 50:  
        estimated_transit_distance_km = drive_dist * 1.05  # Train routes ~5% longer
    else:
        scaling_factor = logistic_scaling_factor(drive_dist)
        estimated_transit_distance_km = drive_dist * scaling_factor

    # Compute emissions for public transport
    emissions = EMISSION_FACTORS["publicTransport"] * estimated_transit_distance_km
    ci_lower, ci_upper = compute_ci(emissions, STD_EMISSION_FACTORS["publicTransport"] * estimated_transit_distance_km)

    return estimated_transit_distance_km, emissions, (ci_lower, ci_upper), drive_route

# API Endpoint: Get the best eco-friendly route
@app.route('/get-eco-route', methods=['GET'])
@app.route('/get-eco-route', methods=['GET'])
def get_eco_route():
    origin_address = request.args.get('origin')
    destination_address = request.args.get('destination')

    if not origin_address or not destination_address:
        return jsonify({"error": "Missing origin or destination"}), 400

    # Convert addresses to coordinates
    origin_coords = get_coordinates(origin_address)
    destination_coords = get_coordinates(destination_address)

    if not origin_coords or not destination_coords:
        return jsonify({"error": "Invalid address"}), 400

    logging.info(f"🌍 Routing from {origin_address} → {destination_address}")

    # Get routes for all modes
    drive_dist, drive_emissions, drive_ci, drive_route = get_route_and_emissions(origin_coords, destination_coords, "driving-car")
    walk_dist, walk_emissions, walk_ci, walk_route = get_route_and_emissions(origin_coords, destination_coords, "foot-walking")
    bike_dist, bike_emissions, bike_ci, bike_route = get_route_and_emissions(origin_coords, destination_coords, "cycling-regular")
    transit_dist, transit_emissions, transit_ci, transit_route = approximate_public_transport_route(origin_coords, destination_coords)

    # Store valid routes
    routes = {
        "driving": {"distance": drive_dist, "emissions": drive_emissions, "ci": drive_ci, "route": drive_route},
        "walking": {"distance": walk_dist, "emissions": walk_emissions, "ci": walk_ci, "route": walk_route},
        "cycling": {"distance": bike_dist, "emissions": bike_emissions, "ci": bike_ci, "route": bike_route},
        "public_transport": {"distance": transit_dist, "emissions": transit_emissions, "ci": transit_ci, "route": transit_route}
    }

    # Filter out failed routes and enforce limits
    valid_routes = {mode: data for mode, data in routes.items() if data["distance"] is not None}
    valid_routes = {mode: data for mode, data in valid_routes.items() if not (
        (mode == "walking" and data["distance"] > WALK_THRESHOLD) or
        (mode == "cycling" and data["distance"] > BIKE_THRESHOLD)
    )}

    if not valid_routes:
        return jsonify({"error": "No valid routes found"}), 404

    # Find the lowest carbon route
    best_mode = min(valid_routes, key=lambda k: valid_routes[k]["emissions"])
    best_route = valid_routes[best_mode]

    # Compare against driving
    driving_comparison = {
        "co2_savings_kg": round(drive_emissions - best_route["emissions"], 3) if drive_emissions is not None else None,
        "distance_savings_km": round(drive_dist - best_route["distance"], 3) if drive_dist is not None else None,
        "percentage_co2_reduction": round(((drive_emissions - best_route["emissions"]) / drive_emissions) * 100, 2) if drive_emissions else None
    }

    return jsonify({
        "best_mode": best_mode,
        "distance_km": round(best_route["distance"], 3),
        "co2_emissions_kg": round(best_route["emissions"], 3),
        "confidence_interval": {
            "lower": round(best_route["ci"][0], 3),
            "upper": round(best_route["ci"][1], 3)
        },
        "compared_to_driving": driving_comparison
    })


# Run Flask app
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
