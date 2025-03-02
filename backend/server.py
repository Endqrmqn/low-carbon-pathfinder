from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging
from dotenv import load_dotenv
from retrying import retry
import json
import networkx as nx

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

# Threshold for recommending walking (km)
WALK_THRESHOLD = 2

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
        logging.info(f"Geocode response: {data}")

        if "features" in data and len(data["features"]) > 0:
            lon, lat = data["features"][0]["geometry"]["coordinates"]
            return lat, lon  # Return (latitude, longitude)
    except requests.RequestException as e:
        logging.error(f"Failed to fetch coordinates for {address}: {e}")
    return None  # Address not found

def get_route_and_emissions(origin, destination, mode="cycling-regular"):
    url = f"https://api.openrouteservice.org/v2/directions/{mode}?api_key={ORS_API_KEY}&start={origin[1]},{origin[0]}&end={destination[1]},{destination[0]}"
    
    try:
        route_data = make_request(url)
        logging.info(f"ORS Response for {mode}: {json.dumps(route_data, indent=2)}")

        # ✅ Check if a valid route exists
        if "features" not in route_data or not route_data["features"]:
            logging.warning(f"❌ No valid route found for mode: {mode}")
            return None, None, None

        # ✅ Extract total distance (meters)
        total_distance_m = route_data["features"][0]["properties"]["segments"][0]["distance"]
        total_distance_km = total_distance_m / 1000  # Convert to km

        # ✅ Estimate CO₂ emissions
        emissions = EMISSION_FACTORS.get(mode, 0) * total_distance_km

        # ✅ Return full route data for response
        return total_distance_km, emissions, route_data
    except requests.RequestException as e:
        logging.error(f"Failed to fetch route: {e}")
    return None, None, None



# Function to check if walking should be recommended
def should_walk(distance_km, is_city=True):
    if distance_km < WALK_THRESHOLD and is_city:
        return True
    return False

# Function to create a graph for multi-modal route optimization
def create_graph():
    G = nx.Graph()

    # Example nodes and edges (replace with real data)
    G.add_edge("A", "B", weight=EMISSION_FACTORS["driving-car"] * 5, mode="car")
    G.add_edge("A", "C", weight=EMISSION_FACTORS["publicTransport"] * 5, mode="bus")
    G.add_edge("C", "B", weight=EMISSION_FACTORS["foot-walking"] * 2, mode="walk")

    return G

# Function to find the lowest-carbon path using Dijkstra's algorithm
def find_lowest_co2_path(G, start, end):
    try:
        path = nx.shortest_path(G, source=start, target=end, weight="weight")
        total_emissions = sum(G[u][v]["weight"] for u, v in zip(path[:-1], path[1:]))
        return path, total_emissions
    except nx.NetworkXNoPath:
        return None, None

# Bayesian update function to predict future CO₂ savings
def bayesian_update(prior_prob, co2_savings_if_follow, co2_savings_if_not):
    P_D_given_E = co2_savings_if_follow / (co2_savings_if_follow + co2_savings_if_not)
    P_D = 0.5  # Assume equal likelihood of user following or not

    updated_prob = (P_D_given_E * prior_prob) / P_D
    return updated_prob

# API Endpoint: Get the best eco-friendly route
@app.route('/get-eco-route', methods=['GET'])
def get_eco_route():
    origin_address = request.args.get('origin')
    destination_address = request.args.get('destination')

    logging.info(f"Received request: origin={origin_address}, destination={destination_address}")

    if not origin_address or not destination_address:
        return jsonify({"error": "Missing origin or destination"}), 400

    # Convert addresses to coordinates
    origin_coords = get_coordinates(origin_address)
    destination_coords = get_coordinates(destination_address)

    logging.info(f"Converted to coordinates: origin={origin_coords}, destination={destination_coords}")

    if not origin_coords or not destination_coords:
        return jsonify({"error": "Invalid address"}), 400

    # Get different transport modes
    drive_dist, drive_emissions, drive_route = get_route_and_emissions(origin_coords, destination_coords, "driving-car")
    walk_dist, walk_emissions, walk_route = get_route_and_emissions(origin_coords, destination_coords, "foot-walking")
    bike_dist, bike_emissions, bike_route = get_route_and_emissions(origin_coords, destination_coords, "cycling-regular")
    transit_dist, transit_emissions, transit_route = get_route_and_emissions(origin_coords, destination_coords, "publicTransport")

    routes = {
        "driving": {"distance": drive_dist, "emissions": drive_emissions, "route": drive_route},
        "walking": {"distance": walk_dist, "emissions": walk_emissions, "route": walk_route},
        "cycling": {"distance": bike_dist, "emissions": bike_emissions, "route": bike_route},
        "public_transport": {"distance": transit_dist, "emissions": transit_emissions, "route": transit_route}
    }

    # Filter out failed routes
    valid_routes = {mode: data for mode, data in routes.items() if data["distance"] is not None}

    # 🚨 Enforce walking limit (remove walking if distance > 2 km)
    if "walking" in valid_routes and valid_routes["walking"]["distance"] > WALK_THRESHOLD:
        logging.info("Walking route removed (exceeds 2 km limit).")
        del valid_routes["walking"]

    # 🚨 Enforce biking limit (remove biking if distance > 5 km)
    if "cycling" in valid_routes and valid_routes["cycling"]["distance"] > 5:
        logging.info("Biking route removed (exceeds 5 km limit).")
        del valid_routes["cycling"]

    # 🚨 Enforce public transport limit
    if "public_transport" in valid_routes:
        if valid_routes["public_transport"]["distance"] < 2:
            logging.info("Public transport removed (too short to justify).")
            del valid_routes["public_transport"]

    if not valid_routes:
        return jsonify({"error": "No valid routes found"}), 404

    # Find the lowest carbon route
    best_mode = min(valid_routes, key=lambda k: valid_routes[k]["emissions"])
    best_route = valid_routes[best_mode]

    logging.info(f"Selected best mode: {best_mode}, emissions: {best_route['emissions']}")

    return jsonify({
        "best_mode": best_mode,
        "route": best_route["route"],
        "co2_emissions_kg": round(best_route["emissions"], 3)
    })

# Run Flask app
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
